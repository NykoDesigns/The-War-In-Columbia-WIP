/// Memory Monitor for BioShock Infinite (32-bit address-space watchdog)
///
/// BioShock Infinite is a 32-bit process: it crashes from ADDRESS-SPACE
/// exhaustion, not physical RAM. The metric that predicts an out-of-memory
/// crash is the LARGEST CONTIGUOUS FREE BLOCK in the virtual address space —
/// when no free region is big enough for the next allocation, VirtualAlloc
/// fails and the game crashes.
///
/// Summing hooked VirtualAlloc/VirtualFree calls is unreliable (UE3 routes
/// most memory through HeapAlloc and its own pooled allocators, and pools
/// repeatedly commit/decommit the same regions). Instead, this monitor walks
/// the entire address space with VirtualQuery every few seconds to get an
/// accurate picture, and uses the VirtualAlloc hook ONLY to capture the exact
/// allocation that fails (the OOM smoking gun) with a caller stack trace.

#include "mem_monitor.h"

#include <Windows.h>
#include <Psapi.h>
#include <MinHook.h>

#include <cstdio>
#include <cstdint>
#include <atomic>
#include <mutex>

// ═══════════════════════════════════════════════════════════════════════════
//  Log File
// ═══════════════════════════════════════════════════════════════════════════

static FILE*       g_LogFile = nullptr;
static std::mutex  g_LogMutex;
static DWORD       g_StartTick = 0;

static void Log(const char* fmt, ...)
{
    if (!g_LogFile) return;
    std::lock_guard<std::mutex> lock(g_LogMutex);

    DWORD elapsed = GetTickCount() - g_StartTick;
    unsigned mn = (elapsed / 60000);
    unsigned sc = (elapsed / 1000) % 60;
    unsigned ms = elapsed % 1000;

    fprintf(g_LogFile, "[%02u:%02u.%03u] ", mn, sc, ms);

    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_LogFile, fmt, ap);
    va_end(ap);

    fprintf(g_LogFile, "\n");
    fflush(g_LogFile);
}

static bool OpenLogFile()
{
    char exePath[MAX_PATH];
    GetModuleFileNameA(nullptr, exePath, MAX_PATH);
    char* lastSlash = strrchr(exePath, '\\');
    if (lastSlash) *(lastSlash + 1) = '\0';
    else exePath[0] = '\0';

    char logPath[MAX_PATH];
    snprintf(logPath, MAX_PATH, "%swic_memmon.log", exePath);

    g_LogFile = fopen(logPath, "w");
    if (!g_LogFile) return false;

    fprintf(g_LogFile, "=== War In Columbia Memory Monitor (address-space watchdog) ===\n");
    fprintf(g_LogFile, "Log: %s\n\n", logPath);
    fflush(g_LogFile);
    return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Address-Space Walk (the accurate metric)
// ═══════════════════════════════════════════════════════════════════════════

struct AddrSpaceStats {
    uint64_t reservedBytes  = 0; // MEM_RESERVE (committed counts as reserved too)
    uint64_t committedBytes = 0; // MEM_COMMIT
    uint64_t freeBytes      = 0; // MEM_FREE
    uint64_t largestFree    = 0; // largest contiguous MEM_FREE region
    uint32_t regionCount    = 0;
};

static AddrSpaceStats WalkAddressSpace()
{
    AddrSpaceStats s;

    SYSTEM_INFO si{};
    GetSystemInfo(&si);

    uint8_t* addr  = (uint8_t*)si.lpMinimumApplicationAddress;
    uint8_t* maxAddr = (uint8_t*)si.lpMaximumApplicationAddress;

    MEMORY_BASIC_INFORMATION mbi{};
    while (addr < maxAddr) {
        if (VirtualQuery(addr, &mbi, sizeof(mbi)) == 0)
            break;

        s.regionCount++;

        if (mbi.State == MEM_FREE) {
            s.freeBytes += mbi.RegionSize;
            if (mbi.RegionSize > s.largestFree)
                s.largestFree = mbi.RegionSize;
        } else {
            // MEM_RESERVE or MEM_COMMIT — both consume address space
            s.reservedBytes += mbi.RegionSize;
            if (mbi.State == MEM_COMMIT)
                s.committedBytes += mbi.RegionSize;
        }

        addr += mbi.RegionSize;
        if (mbi.RegionSize == 0) break; // safety
    }

    return s;
}

// ═══════════════════════════════════════════════════════════════════════════
//  VirtualAlloc Hook — used ONLY to capture failures
// ═══════════════════════════════════════════════════════════════════════════

typedef LPVOID (WINAPI *fn_VirtualAlloc)(LPVOID, SIZE_T, DWORD, DWORD);
static fn_VirtualAlloc Real_VirtualAlloc = nullptr;

static std::atomic<uint32_t> g_FailCount{0};
static std::atomic<uint64_t> g_LargestReqBytes{0}; // largest size ever requested

// Cached largest-free-block (bytes), updated by the stats thread and seeded at
// init. Starts at max so the spawn multiplier isn't gated before first measure.
static std::atomic<uint64_t> g_LargestFreeCached{~0ull};

unsigned MemMonLargestFreeMB()
{
    return static_cast<unsigned>(g_LargestFreeCached.load(std::memory_order_relaxed)
                                 / (1024 * 1024));
}

static LPVOID WINAPI Hook_VirtualAlloc(
    LPVOID lpAddress, SIZE_T dwSize, DWORD flAllocationType, DWORD flProtect)
{
    LPVOID result = Real_VirtualAlloc(lpAddress, dwSize, flAllocationType, flProtect);

    // Track the largest single request we've seen (helps size the danger zone)
    uint64_t cur = g_LargestReqBytes.load(std::memory_order_relaxed);
    while (dwSize > cur) {
        if (g_LargestReqBytes.compare_exchange_weak(cur, dwSize)) break;
    }

    // The smoking gun: a reserve/commit that failed.
    if (!result && (flAllocationType & (MEM_RESERVE | MEM_COMMIT))) {
        g_FailCount.fetch_add(1, std::memory_order_relaxed);

        DWORD err = GetLastError();
        Log("** VirtualAlloc FAILED: size=%zu KB (%.2f MB), type=0x%X, protect=0x%X, err=%lu",
            dwSize / 1024, dwSize / (1024.0 * 1024.0),
            flAllocationType, flProtect, err);

        // Snapshot address space at the moment of failure
        AddrSpaceStats s = WalkAddressSpace();
        Log("   addr-space at failure: committed=%llu MB, reserved=%llu MB, "
            "free=%llu MB, largest-free-block=%llu KB",
            s.committedBytes / (1024*1024),
            s.reservedBytes / (1024*1024),
            s.freeBytes / (1024*1024),
            s.largestFree / 1024);

        // Caller stack
        void* callers[12];
        USHORT frames = CaptureStackBackTrace(1, 12, callers, nullptr);
        HMODULE hExe = GetModuleHandleA(nullptr);
        for (USHORT i = 0; i < frames && i < 6; i++) {
            uintptr_t a = (uintptr_t)callers[i];
            Log("   caller[%d]: 0x%08X (exe+0x%X)",
                i, (uint32_t)a, (uint32_t)(a - (uintptr_t)hExe));
        }
    }

    return result;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Periodic Watchdog Thread
// ═══════════════════════════════════════════════════════════════════════════

static HANDLE g_StatsThread = nullptr;
static volatile bool g_Running = false;

// Warn when the largest free block falls below this (allocations bigger than
// this will start failing). 128 MB is a reasonable early-warning threshold.
static const uint64_t kLargestFreeWarnBytes = 128ULL * 1024 * 1024;

static DWORD WINAPI StatsThread(LPVOID)
{
    uint64_t minLargestFreeSeen = UINT64_MAX;

    while (g_Running) {
        for (int i = 0; i < 50 && g_Running; i++) Sleep(100); // ~5s, responsive to shutdown
        if (!g_Running) break;

        AddrSpaceStats s = WalkAddressSpace();

        PROCESS_MEMORY_COUNTERS pmc{};
        pmc.cb = sizeof(pmc);
        GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc));

        if (s.largestFree < minLargestFreeSeen)
            minLargestFreeSeen = s.largestFree;

        g_LargestFreeCached.store(s.largestFree, std::memory_order_relaxed);

        Log("STATS: committed=%llu MB | reserved=%llu MB | free=%llu MB | "
            "largest-free=%llu MB (min seen %llu MB) | workset=%zu MB | regions=%u | fails=%u",
            s.committedBytes / (1024*1024),
            s.reservedBytes  / (1024*1024),
            s.freeBytes      / (1024*1024),
            s.largestFree    / (1024*1024),
            minLargestFreeSeen / (1024*1024),
            pmc.WorkingSetSize / (1024*1024),
            s.regionCount,
            g_FailCount.load());

        if (s.largestFree < kLargestFreeWarnBytes) {
            Log("** WARNING: largest free block down to %llu MB — "
                "address space is fragmenting/exhausting. OOM risk HIGH.",
                s.largestFree / (1024*1024));
        }
    }
    return 0;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Public API
// ═══════════════════════════════════════════════════════════════════════════

void InitMemMonitor()
{
    g_StartTick = GetTickCount();

    if (!OpenLogFile()) {
        OutputDebugStringA("[WIC MemMon] Failed to open log file\n");
        return;
    }

    Log("Initializing address-space watchdog...");

    // Baseline snapshot
    AddrSpaceStats s = WalkAddressSpace();
    g_LargestFreeCached.store(s.largestFree, std::memory_order_relaxed);
    Log("Baseline: committed=%llu MB, reserved=%llu MB, free=%llu MB, "
        "largest-free=%llu MB, regions=%u",
        s.committedBytes / (1024*1024),
        s.reservedBytes  / (1024*1024),
        s.freeBytes      / (1024*1024),
        s.largestFree    / (1024*1024),
        s.regionCount);

    if (MH_Initialize() != MH_OK) {
        Log("ERROR: MH_Initialize failed (continuing with periodic stats only)");
    } else {
        HMODULE hKernel = GetModuleHandleA("kernel32.dll");
        void* pVirtualAlloc = (void*)GetProcAddress(hKernel, "VirtualAlloc");

        if (MH_CreateHook(pVirtualAlloc, (void*)&Hook_VirtualAlloc,
                           (void**)&Real_VirtualAlloc) == MH_OK &&
            MH_EnableHook(pVirtualAlloc) == MH_OK) {
            Log("VirtualAlloc failure-hook installed");
        } else {
            Log("WARNING: failed to hook VirtualAlloc (periodic stats still active)");
        }
    }

    g_Running = true;
    g_StatsThread = CreateThread(nullptr, 0, StatsThread, nullptr, 0, nullptr);

    Log("Watchdog active. Reporting address-space stats every ~5s; logging any "
        "VirtualAlloc failures with stack traces.");
}

void ShutdownMemMonitor()
{
    g_Running = false;
    if (g_StatsThread) {
        WaitForSingleObject(g_StatsThread, 2000);
        CloseHandle(g_StatsThread);
        g_StatsThread = nullptr;
    }

    MH_DisableHook(MH_ALL_HOOKS);
    MH_Uninitialize();

    if (g_LogFile) {
        AddrSpaceStats s = WalkAddressSpace();
        Log("Shutdown. Final: committed=%llu MB, reserved=%llu MB, "
            "largest-free=%llu MB. Largest single request seen: %llu MB. Failures: %u",
            s.committedBytes / (1024*1024),
            s.reservedBytes  / (1024*1024),
            s.largestFree    / (1024*1024),
            g_LargestReqBytes.load() / (1024*1024),
            g_FailCount.load());
        fclose(g_LogFile);
        g_LogFile = nullptr;
    }
}
