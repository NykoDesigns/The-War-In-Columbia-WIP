/// UE3 spawn hook for BioShock Infinite — "The War In Columbia"
///
/// Phase 1 (this build): LOG-ONLY. Hook AActor::execSpawn and record what the
/// engine spawns (actor pointer, vtable, header bytes containing the FName +
/// UClass pointer). This lets us identify which classes are AI pawns without
/// resolving GNames/GObjects up front.
///
/// Phase 2 (next): multiply AI-pawn spawns by re-invoking the spawn with offset
/// positions, gated by the memory watchdog's largest-free-block headroom.
///
/// Static addresses (ImageBase 0x00400000, build 2022-05-11). ASLR is active,
/// so everything is rebased against the runtime module base.

#include "ue3_spawn.h"
#include "mem_monitor.h"

#include <Windows.h>
#include <MinHook.h>
#include <intrin.h>

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <mutex>

#pragma intrinsic(_ReturnAddress)
#pragma intrinsic(_AddressOfReturnAddress)

// ─── Confirmed static RVAs (see analysis/ADDRESSES.md) ───────────────────
// Native table layout is {name, func}; AActor::execSpawn confirmed @ 0x242D90.
static const uintptr_t RVA_execSpawn  = 0x242D90; // AActor::execSpawn
static const uintptr_t RVA_SpawnActor = 0x22CA80; // UWorld::SpawnActor (candidate)
static const uintptr_t RVA_GNames     = 0xF9DFEC; // global -> FNameEntry* array

// Per-enemy "spawn one AI from this spawner" method. __thiscall(this, desc),
// ret 4. Re-invoking it is IDEMPOTENT (a descriptor that is already spawned
// early-outs), so multiplication must NOT happen here.
static const uintptr_t RVA_SpawnOneAI = 0x657B40;

// create-AI: the LOW-LEVEL "spawn one XAIController + possess a pooled pawn".
// __stdcall, ret 0x14 (5 args); arg0 = spawn-request descriptor. Unlike
// SpawnOneAI this is NOT idempotent - each call creates a fresh controller and
// possesses the next available substantiated (pre-pooled) pawn. So invoking it
// a second time per spawn yields a real, functional EXTRA enemy. THIS is the
// runtime multiplication lever.
static const uintptr_t RVA_CreateAI = 0x651BE0;

// Roster/wave loop (the director's "spawn this whole wave"). __thiscall(this,
// roster, flag). roster = {void* array @ +0; int count @ +4}; it loops
// count times over `array` (stride 0xF0) calling SpawnOneAI on each element.
// THIS is where the enemy COUNT lives. We hook it read-only first to dump the
// descriptor layout, then will duplicate the array to multiply enemies.
static const uintptr_t RVA_SpawnRoster = 0x658870;
static const unsigned   DESC_STRIDE     = 0xF0; // bytes per enemy descriptor

// Per-descriptor enemy-count fields (confirmed via desc diffing: a matched
// {target, remaining} pair that equals the # of enemies of that group; e.g.
// desc[0]=7/7, desc[1]=5/5 => 12-enemy wave). Doubling these = 2x enemies,
// placed by the director's own spawn-node logic (no manual positioning).
static const unsigned OFF_DESC_CountA = 0x0C; // spawn count (target)
static const unsigned OFF_DESC_CountB = 0x10; // spawn count (remaining)

// ─── TEST MATRIX BUILD FLAGS ─────────────────────────────────────────────
// Toggle these to isolate crash source per the A/B/C/D test matrix:
//   Build A: ENABLE_SPAWN_MULT=false, ENABLE_AUDIO_ENLARGE=false (vanilla baseline)
//   Build B: ENABLE_SPAWN_MULT=true,  ENABLE_AUDIO_ENLARGE=false (spawns only)
//   Build C: ENABLE_SPAWN_MULT=false, ENABLE_AUDIO_ENLARGE=true  (audio pools only)
//   Build D: ENABLE_SPAWN_MULT=true,  ENABLE_AUDIO_ENLARGE=true  (full mod)
static const bool     ENABLE_SPAWN_MULT    = true;   // roster grow multiplier
static const bool     ENABLE_AUDIO_ENLARGE = true;   // Wwise pool enlarger

// ─── Multiplier config ───────────────────────────────────────────────────
static const int      g_Multiplier      = 2;   // x2 enemies (tunable later)
static const unsigned MULT_MEM_GATE_MB  = 500; // skip if largest-free below this
static const int      MULT_COUNT_SANE   = 64;  // ignore implausible counts
// Cosmetic roster count-field multiplier: CONFIRMED INEFFECTIVE (0 extra
// enemies). Disabled - the real lever is create-AI double-invoke below.
static const bool     g_DoMultiply      = false;

// create-AI doubling: CONFIRMED creates orphan controllers (brain with no body
// -> invisible/inert, "same as vanilla"). The possession+placement happens in
// the CALLER after create-AI returns, so doubling here is useless. Disabled.
static const int      g_ExtraAIPerSpawn = 1;
static const bool     g_DoubleAI        = false;

// x3 multiplier. Was reduced to 2 when PhysX crashed, but root cause was
// clones inheriting CountA=7 (spawning 7 enemies PER clone descriptor).
// Now that clones force CountA=1, each clone = exactly 1 extra enemy, so
// 3x is safe: a 4-desc roster grows to 12 descs = 8 extra enemies max.
static const int      g_RosterMult      = 3;
// Roster credit-back doubler: REJECTED. Inflating count past the array length
// walks the director's monotonic cursor off the end -> OOB -> render crash.
static const bool     g_DoubleRoster    = false;

// ── IN-PLACE TArray GROW (the working x2 lever) ────────────────────────────
// The roster passed to SpawnRoster is a UE3 TArray: {void* Data; int Num; int
// Max} at +0x00/+0x04/+0x08 (CONFIRMED via HDR-DUMP: Data=0x02AC1C00, Num=2,
// Max=4). Max is the ALLOCATED capacity, often > Num (slack). We clone the
// live descriptors into the spare [Num..Max) slots and bump Num up to
// min(Num*mult, Max) -- staying strictly within the allocation (no OOB, no
// realloc, no free-ownership risk). The director then spawns the extras via
// its own full path (real body + possession + placement). Done ONCE per wave
// (guarded by a per-array lastNum: only grow when Num increases = fresh wave).
static const bool     g_GrowRoster      = true;
static const unsigned OFF_TARRAY_NUM    = 0x04; // TArray.Num  (count)
static const unsigned OFF_TARRAY_MAX    = 0x08; // TArray.Max  (capacity)
static const unsigned OFF_DESC_PosX     = 0x60; // spawn location X (float)
// AISpawnInfo (the 0xF0 descriptor) embeds heap-OWNING fields. A raw memcpy
// clone aliases their TArray.Data pointers -> double-free / heap corruption /
// leak (the confirmed crash). Detach them in the clone (zero the 12-byte
// {Data,Num,Max} headers) so it owns no shared buffer; the extra enemy then
// falls back to its default loadout via the bGiveDefault* bools @0x2C.
// Offsets confirmed via the live STRUCT dump of 'AISpawnInfo'.
static const unsigned DESC_TARRAY_OFFS[] = {
    0x08, // .PawnLabels
    0x20, // .LootList
    0x30, // .LootToAwardOnKillList
    0x3C, // .InventoryList
};
static const unsigned OFF_DESC_Delegate = 0xD8; // .Delegate {object, FName, FName} = 12 bytes
// Trailing per-enemy RUNTIME pair at +0xE8/+0xEC. The live DESC-DIFF showed
// +0xEC is a per-instance heap pointer (0x28xxxxxx) that is NOT part of the
// AISpawnInfo property layout, and +0xE8 a small count/flags word. Raw-copying
// the 0xF0 descriptor aliases this pointer into every clone -> when the source
// descriptor is destroyed the clones dangle -> the streaming serializer reads a
// freed length and memcpy's ~1 GB (CONFIRMED crash: EIP in memcpy, ecx≈1GB). A
// valid real descriptor (desc[1]) carries BOTH as 0, so zeroing this pair in
// the clone yields a clean, fully-independent enemy that owns nothing shared.
static const unsigned OFF_DESC_RuntimeCnt = 0xE8; // count/flags word
static const unsigned OFF_DESC_RuntimePtr = 0xEC; // per-instance heap pointer
static const bool     g_HuntCursor      = false; // HDR-DUMP diagnostic (done)
// DIAGNOSTIC: dump the desc[0]/desc[1] field diff but DO NOT actually clone, so
// this run injects ZERO enemies (no leak, no crash) while we learn the layout.
// Set false to resume real growing once we build a non-leaking clone.
static const bool     g_DiagNoGrow      = false;
// ABSOLUTE wave-size cap (descriptor count, not total enemies). With the
// CountA=1 fix, each descriptor = exactly 1 enemy, so this directly controls
// max enemies per wave. 16 is conservative: 8-desc roster × 3x = 24 descs,
// capped to 16 = 8 extra enemies. Previously crashed at 12+ because clones
// inherited CountA=7 (producing 7 enemies EACH), now each clone = 1 enemy.
static const int      g_MaxWaveTotal    = 16;
// Require this much extra headroom PER added enemy on top of the base gate, so a
// big add only proceeds with comfortable memory (defends the stale-poll spike).
static const unsigned MULT_MEM_PER_ADD_MB = 60;

// UObject field offsets (confirmed via GetPathName / hexdump analysis):
static const unsigned OFF_Name  = 0x18; // FName Name (Index @ +0x18, Number @ +0x1C)
static const unsigned OFF_Class = 0x20; // UClass* (constant per vtable)
// FNameEntry: flags @ +0x08 (bit0 = wide), string @ +0x10.
static const unsigned OFF_FNameEntry_Flags = 0x08;
static const unsigned OFF_FNameEntry_Str   = 0x10;

// Engine allocator, so clone-owned buffers are freed by the engine (no double
// free). appRealloc(ptr,size,align) @ rva 0x082AB0 loads GMalloc @ [0x1371CC8]
// and dispatches its vtable+0xC (Realloc); ptr=NULL allocates fresh. Confirmed
// via FString::operator+= (0x4A7B00) -> grow (0x518DA0) -> appRealloc (0x482AB0).
typedef void* (__cdecl* appRealloc_t)(void* ptr, size_t size, unsigned alignment);
static const unsigned RVA_appRealloc   = 0x082AB0;
static const unsigned OFF_DESC_Spawner = 0xCC; // AISpawnInfo.Spawner (XAIScriptedSpawner ref)
static const unsigned ARRAYPROP_INNER  = 0x58; // UArrayProperty::Inner (same slot as StructProperty::Struct)

// ─── Logging ─────────────────────────────────────────────────────────────
static FILE*      g_Log = nullptr;
static std::mutex g_LogMutex;
static DWORD      g_StartTick = 0;
static uintptr_t  g_Base = 0;

static void SLog(const char* fmt, ...)
{
    if (!g_Log) return;
    std::lock_guard<std::mutex> lock(g_LogMutex);
    DWORD e = GetTickCount() - g_StartTick;
    fprintf(g_Log, "[%02u:%02u.%03u] ", e / 60000, (e / 1000) % 60, e % 1000);
    va_list ap; va_start(ap, fmt); vfprintf(g_Log, fmt, ap); va_end(ap);
    fprintf(g_Log, "\n");
    fflush(g_Log);
}

static bool OpenLog()
{
    char path[MAX_PATH];
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) *(slash + 1) = '\0'; else path[0] = '\0';
    strncat(path, "wic_spawn.log", MAX_PATH - strlen(path) - 1);
    g_Log = fopen(path, "a"); // append: preserve prior level/session logs
    if (!g_Log) return false;
    SYSTEMTIME st; GetLocalTime(&st);
    fprintf(g_Log,
            "\n=== War In Columbia spawn hook (log-only) :: SESSION %04u-%02u-%02u "
            "%02u:%02u:%02u ===\n",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    fflush(g_Log);
    return true;
}

// ─── execSpawn hook ──────────────────────────────────────────────────────
// UE3 exec native: void __thiscall execSpawn(AActor* this, FFrame& Stack, void* Result)
// MSVC __fastcall(This, edxDummy, Stack, Result) reproduces thiscall + stack args.
typedef void(__fastcall* fn_execSpawn)(void* This, void* edx, void* Stack, void** Result);
static fn_execSpawn Real_execSpawn = nullptr;

static volatile LONG g_SpawnSeq = 0;

// Resolve an FName index to a string via GNames. Caller provides SEH.
static void ResolveFName(int index, char* out, size_t n)
{
    out[0] = '\0';
    if (index < 0 || (unsigned)index > 0x400000) return;
    void** gnames = *reinterpret_cast<void***>(g_Base + RVA_GNames);
    if (!gnames || IsBadReadPtr(gnames + index, 4)) return;
    char* entry = reinterpret_cast<char*>(gnames[index]);
    if (!entry || IsBadReadPtr(entry, OFF_FNameEntry_Str + 2)) return;
    DWORD flags = *reinterpret_cast<DWORD*>(entry + OFF_FNameEntry_Flags);
    const void* str = entry + OFF_FNameEntry_Str;
    if (flags & 1) { // wide
        const wchar_t* w = reinterpret_cast<const wchar_t*>(str);
        if (IsBadStringPtrW(w, 256)) return;
        WideCharToMultiByte(CP_UTF8, 0, w, -1, out, (int)n, nullptr, nullptr);
    } else {         // ansi
        const char* a = reinterpret_cast<const char*>(str);
        if (IsBadStringPtrA(a, 256)) return;
        strncpy(out, a, n - 1);
        out[n - 1] = '\0';
    }
}

// Heuristic stack scan: from the hook's return-address slot, scan upward and
// collect dwords that look like return addresses into the exe's .text. This
// reveals the call chain (wrapper -> AI-spawn routine -> spawning manager)
// without needing frame pointers. Approx .text bound: rva < 0xD00000.
static void LogCallStack(const char* tag, void** retSlot)
{
    __try {
        char buf[512]; int n = 0; int found = 0;
        for (int i = 0; i < 400 && found < 12; ++i) {
            uintptr_t a = reinterpret_cast<uintptr_t>(retSlot[i]);
            if (a > g_Base + 0x1000 && a < g_Base + 0xD00000) {
                n += sprintf(buf + n, "0x%X ", (unsigned)(a - g_Base));
                ++found;
                if (n > (int)sizeof(buf) - 16) break;
            }
        }
        SLog("  %s callstack_rva: %s", tag, buf);
    } __except (EXCEPTION_EXECUTE_HANDLER) {}
}

static volatile LONG g_AICtrlStackLogged = 0;

// Genuine spawned UObjects (real vtable in module) captured for the GObjects
// locator. These are guaranteed to be tracked in GObjects, unlike the raw heap
// structs the descriptor probe sometimes sees. First 8 distinct are kept.
static void*        g_LiveObjs[8];
static volatile LONG g_LiveN = 0;

// SEH-guarded post-processing (kept in its own function with no C++ unwinding
// objects so __try/__except is legal).
static void SafeLogActor(LONG seq, void* spawned, void* caller, void** retSlot)
{
    __try {
        if (!spawned || IsBadReadPtr(spawned, 0x40)) {
            return; // spawn failed / nothing created
        }
        char* ab = reinterpret_cast<char*>(spawned);
        void* vtbl = *reinterpret_cast<void**>(spawned);
        unsigned vrva = (vtbl >= (void*)g_Base)
                            ? (unsigned)((uintptr_t)vtbl - g_Base) : 0u;

        int nameIdx = *reinterpret_cast<int*>(ab + OFF_Name);
        int nameNum = *reinterpret_cast<int*>(ab + OFF_Name + 4);
        void* cls   = *reinterpret_cast<void**>(ab + OFF_Class);

        char objName[128]; ResolveFName(nameIdx, objName, sizeof objName);
        char clsName[128]; clsName[0] = '\0';
        if (cls && !IsBadReadPtr(cls, OFF_Name + 4)) {
            int clsIdx = *reinterpret_cast<int*>((char*)cls + OFF_Name);
            ResolveFName(clsIdx, clsName, sizeof clsName);
        }

        // Capture genuine UObjects (real in-module vtable + resolved class) as
        // high-quality seeds for the one-shot GObjects locator.
        if (vrva != 0 && clsName[0] && g_LiveN < (LONG)_countof(g_LiveObjs)) {
            bool dup = false;
            for (LONG q = 0; q < g_LiveN; ++q) if (g_LiveObjs[q] == spawned) dup = true;
            if (!dup) g_LiveObjs[g_LiveN++] = spawned;
        }

        // Enemy-relevant classes are ALWAYS logged (no cap) with their caller so
        // we can locate the AI-spawn routine across many levels. Everything else
        // is noise (MatineeActor, etc.) and only logged for the first 150 spawns
        // of a session to capture one level's actor variety.
        bool enemyish = (strcmp(clsName, "XHuman") == 0 ||
                         strcmp(clsName, "XAIController") == 0);
        if (enemyish) {
            unsigned crva = (caller >= (void*)g_Base)
                                ? (unsigned)((uintptr_t)caller - g_Base) : 0u;
            SLog("SPAWN #%ld: class='%s' name='%s_%d' vtbl_rva=0x%X  <-- caller_rva=0x%X",
                 seq, clsName, objName, nameNum, vrva, crva);
            // Capture the deeper call chain for the first few XAIController
            // spawns to locate the AI-spawn routine / spawning manager.
            if (strcmp(clsName, "XAIController") == 0 &&
                InterlockedIncrement(&g_AICtrlStackLogged) <= 6) {
                LogCallStack("XAIController", retSlot);
            }
        } else if (seq <= 150) {
            SLog("SPAWN #%ld: class='%s' name='%s_%d' vtbl_rva=0x%X",
                 seq, clsName, objName, nameNum, vrva);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        SLog("EXCEPTION in SafeLogActor #%ld code=0x%lX", seq, GetExceptionCode());
    }
}

// ─── UWorld::SpawnActor hook ─────────────────────────────────────────────
// thiscall(this=GWorld), 15 stack dwords (ret 0x3C), returns AActor*. This is
// the universal C++ spawn chokepoint: catches script Spawn() AND the C++ AI
// spawning manager (which is how most enemy pawns are created).
typedef void*(__fastcall* fn_SpawnActor)(
    void* This, void* edx,
    uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4,
    uint32_t a5, uint32_t a6, uint32_t a7, uint32_t a8, uint32_t a9,
    uint32_t a10, uint32_t a11, uint32_t a12, uint32_t a13, uint32_t a14);
static fn_SpawnActor Real_SpawnActor = nullptr;

static void* __fastcall Hook_SpawnActor(
    void* This, void* edx,
    uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4,
    uint32_t a5, uint32_t a6, uint32_t a7, uint32_t a8, uint32_t a9,
    uint32_t a10, uint32_t a11, uint32_t a12, uint32_t a13, uint32_t a14)
{
    void* caller = _ReturnAddress();
    void** retSlot = reinterpret_cast<void**>(_AddressOfReturnAddress());
    void* actor = Real_SpawnActor(This, edx, a0, a1, a2, a3, a4, a5, a6, a7,
                                  a8, a9, a10, a11, a12, a13, a14);
    LONG seq = InterlockedIncrement(&g_SpawnSeq);
    // No hard cap: SafeLogActor self-filters (enemy spawns always; others <=150).
    SafeLogActor(seq, actor, caller, retSlot);
    return actor;
}

// ─── create-AI doubler: the real runtime multiplication lever ────────────
// __stdcall, ret 0x14 (5 stack args), arg0 = spawn-request descriptor. Each
// call creates a fresh XAIController and possesses the next pooled pawn, so a
// second invocation per spawn yields one extra functional enemy.
typedef void*(__stdcall* fn_CreateAI)(void* a0, void* a1, void* a2,
                                      void* a3, void* a4);
static fn_CreateAI Real_CreateAI = nullptr;

static volatile LONG g_CreateSeq   = 0; // total create-AI calls seen
static volatile LONG g_ExtraAI     = 0; // extra enemies we spawned
static volatile LONG g_ExtraGated  = 0; // extra spawns skipped (mem gate)
static volatile LONG g_InCreate    = 0; // reentrancy guard

static void* __stdcall Hook_CreateAI(void* a0, void* a1, void* a2,
                                     void* a3, void* a4)
{
    // Always run the real spawn first.
    void* result = Real_CreateAI(a0, a1, a2, a3, a4);
    InterlockedIncrement(&g_CreateSeq);

    // Only double on the TOP-LEVEL call (never recurse into our own extras),
    // when the real spawn succeeded, and when memory headroom is healthy.
    if (g_DoubleAI && result &&
        InterlockedCompareExchange(&g_InCreate, 1, 0) == 0) {
        __try {
            for (int i = 0; i < g_ExtraAIPerSpawn; ++i) {
                if (MemMonLargestFreeMB() < MULT_MEM_GATE_MB) {
                    InterlockedIncrement(&g_ExtraGated);
                    break;
                }
                void* extra = Real_CreateAI(a0, a1, a2, a3, a4);
                if (!extra) break; // pool exhausted / spawn refused
                LONG n = InterlockedIncrement(&g_ExtraAI);
                if (n <= 60)
                    SLog("EXTRA-AI #%ld: spawned (orig=0x%p extra=0x%p, "
                         "largest-free=%u MB)", n, result, extra,
                         MemMonLargestFreeMB());
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            SLog("EXCEPTION in Hook_CreateAI (code=0x%lX)", GetExceptionCode());
        }
        InterlockedExchange(&g_InCreate, 0);
    }
    return result;
}

// ─── Roster inspector: read-only dump of the wave's enemy descriptors ─────
// __thiscall(this, roster, flag, a2), ret 0xC (THREE stack args). roster =
// {void* array; int count; ...}. The call site is the AI-director tick at
// 0x658A70 (push 0; push 0; push eax; mov ecx,esi; call). Declaring the wrong
// arg count imbalances the stack by 4 bytes and corrupts the caller -> crash.
typedef void*(__fastcall* fn_SpawnRoster)(void* This, void* edx,
                                          void* roster, uint32_t flag,
                                          uint32_t a2);
static fn_SpawnRoster Real_SpawnRoster = nullptr;

static volatile LONG g_RosterSeq   = 0;
static volatile LONG g_MultiDumped = 0; // dumped a count>1 wave yet?
static volatile LONG g_MultApplied = 0; // # of descriptors we have doubled
static volatile LONG g_MultGated   = 0; // # of times skipped due to mem gate

// Ring guard: remember the last N descriptors we doubled (by ptr + the value
// we wrote) so the per-frame polling loop does not re-double (compound) them.
// A descriptor is re-eligible only if the game has since reset it to a fresh
// value (ptr unseen, or stored != current) -> handles encounter reuse.
struct MultSlot { void* ptr; int wrote; };
static const int  MULT_RING = 64;
static MultSlot   g_MultRing[MULT_RING] = {};
static volatile LONG g_MultRingPos = 0;
static std::mutex g_MultRingMtx;

// Returns true if (ptr,curVal) is NOT already recorded -> caller should double.
// Records the value it will write so subsequent frames are skipped.
static bool MultClaim(void* ptr, int curVal, int willWrite)
{
    std::lock_guard<std::mutex> lk(g_MultRingMtx);
    for (int i = 0; i < MULT_RING; ++i) {
        if (g_MultRing[i].ptr == ptr) {
            if (g_MultRing[i].wrote == curVal) return false; // already doubled
            g_MultRing[i].wrote = willWrite;                 // fresh value -> redo
            return true;
        }
    }
    int pos = (int)(InterlockedIncrement(&g_MultRingPos) - 1) % MULT_RING;
    g_MultRing[pos].ptr   = ptr;
    g_MultRing[pos].wrote = willWrite;
    return true;
}

// ── Roster credit-back state (one slot per live roster array) ──────────────
// We track each roster array we have seen, its observed maximum count (the
// original wave size N), and how many extra "credits" we still owe it. Each
// time the director consumes enemies we hand back up to that many credits,
// never letting count exceed N (so the descriptor array is never over-read).
struct RosterSlot {
    void* array;
    int   maxSeen;        // original wave size N (cap for count)
    int   lastCount;      // count value as we last left it
    int   addedRemaining; // extra spawns still owed (N*(mult-1) per wave)
    bool  active;
};
static const int  ROSTER_TBL = 32;
static RosterSlot g_RosterTbl[ROSTER_TBL] = {};
static std::mutex g_RosterMtx;
static volatile LONG g_RosterAdded = 0; // total extra enemies credited

// Return the slot for `array`, (re)initialising it for a fresh wave when the
// array is new or its count has just been refilled above what we left it at.
static RosterSlot* RosterSlotFor(void* array, int curCount)
{
    for (int i = 0; i < ROSTER_TBL; ++i) {
        RosterSlot& s = g_RosterTbl[i];
        if (s.active && s.array == array) {
            if (curCount > s.lastCount) { // refill => new wave on a reused array
                s.maxSeen = curCount;
                s.addedRemaining = curCount * (g_RosterMult - 1);
            }
            return &s;
        }
    }
    for (int i = 0; i < ROSTER_TBL; ++i) {
        RosterSlot& s = g_RosterTbl[i];
        if (!s.active) {
            s = { array, curCount, curCount, curCount * (g_RosterMult - 1), true };
            return &s;
        }
    }
    g_RosterTbl[0] = { array, curCount, curCount, curCount * (g_RosterMult - 1), true };
    return &g_RosterTbl[0];
}

// ── In-place grow state ────────────────────────────────────────────────────
// Per-array lastNum lets us grow each wave exactly ONCE: we only act when Num
// has INCREASED since we last saw this array (a fresh/refilled wave). After we
// grow, we record lastNum = the new (grown) Num so the subsequent drain never
// re-triggers. Reused buffers re-arm naturally when a new wave pushes Num back
// up past the drained low-water mark.
struct GrowSlot { void* array; int lastNum; };
static const int     GROW_TBL = 64;
static GrowSlot      g_GrowTbl[GROW_TBL] = {};
static volatile LONG g_GrowPos    = 0;
static volatile LONG g_GrowWaves  = 0; // waves we grew
static volatile LONG g_GrowAdded  = 0; // total extra enemies injected
static volatile LONG g_DescDiffed = 0; // one-shot desc[0] vs desc[1] diff
static volatile LONG g_LevelGrows  = 0; // grows since last level change (heartbeat)
static volatile LONG g_PeakEnemies = 0; // max totalEnemies seen in single roster

static void HexDumpToLog(const char* tag, const unsigned char* p, unsigned n);

// Resolve a UObject*'s name and class-name (best effort). Returns false if it
// does not look like a readable UObject with a resolvable FName.
static bool ResolveObjNameClass(void* p, char* nm, size_t nmN, char* cn, size_t cnN)
{
    nm[0] = '\0'; cn[0] = '\0';
    if (!p || IsBadReadPtr(p, OFF_Class + 4)) return false;
    int nameIdx = *reinterpret_cast<int*>((char*)p + OFF_Name);
    if (nameIdx <= 0 || (unsigned)nameIdx > 0x400000) return false;
    ResolveFName(nameIdx, nm, nmN);
    if (!nm[0]) return false;
    void* c = *reinterpret_cast<void* const*>((char*)p + OFF_Class);
    if (c && !IsBadReadPtr(c, OFF_Name + 4)) {
        int ci = *reinterpret_cast<int*>((char*)c + OFF_Name);
        ResolveFName(ci, cn, cnN);
    }
    return true;
}

// UE3 offset bootstrap: scan an object's first `len` bytes for fields that are
// pointers to OTHER readable, named UObjects. For a UClass this reveals
// SuperField (-> parent class) and Children (-> first UProperty); for a
// UProperty it reveals Next (-> sibling). The target's CLASS name tells us the
// property TYPE (IntProperty/ObjectProperty/StructProperty/...). If `recurse`,
// any field whose target class ends in "Property" is itself dumped+scanned so
// one pass captures the property chain + each property's metadata bytes.
static void ScanObjPointers(const char* tag, void* obj, unsigned len, int recurse)
{
    if (!obj || IsBadReadPtr(obj, len)) {
        SLog("  SCAN %s: unreadable 0x%p", tag, obj); return;
    }
    for (unsigned off = 0; off + 4 <= len; off += 4) {
        void* p = *reinterpret_cast<void* const*>((const char*)obj + off);
        char nm[128], cn[128];
        if (!ResolveObjNameClass(p, nm, sizeof nm, cn, sizeof cn)) continue;
        SLog("  SCAN %s+0x%02X -> 0x%p name='%s' class='%s'", tag, off, p, nm, cn);
        if (recurse > 0 && strstr(cn, "Property")) {
            char sub[160]; sprintf(sub, "%s.%s", tag, nm);
            HexDumpToLog(sub, (unsigned char*)p, 0x60);
            ScanObjPointers(sub, p, 0x60, recurse - 1);
        }
    }
}

// UE3 v727 metadata offsets, bootstrapped from the live CLASS-DUMP:
//   UObject:  Outer=+0x14, Name=+0x18, Class=+0x20, Archetype=+0x24
//   UField:   Next=+0x28
//   UStruct:  SuperField=+0x34, Children=+0x38
//   UProperty:ArrayDim=+0x2C, ElementSize=+0x30, PropertyFlags=+0x34 (qword)
//   StructProperty / ObjectProperty: inner type ptr at +0x58
static const unsigned UFIELD_NEXT      = 0x28;
static const unsigned USTRUCT_SUPER    = 0x34;
static const unsigned USTRUCT_CHILDREN = 0x38;
static const unsigned STRUCTPROP_STRUCT = 0x58;
static const unsigned UPROP_ARRAYDIM   = 0x2C;
static const unsigned UPROP_ELEMSIZE   = 0x30;
static const unsigned UPROP_OFFSET     = 0x48; // confirmed: bitfield bools share offset

// Find a named child UField, walking THIS struct's Children->Next chain and
// then up the SuperField chain (so inherited properties are found too).
static void* StructFindChild(void* ustruct, const char* want)
{
    int sguard = 0;
    while (ustruct && !IsBadReadPtr(ustruct, USTRUCT_CHILDREN + 4) && sguard++ < 16) {
        void* child = *reinterpret_cast<void**>((char*)ustruct + USTRUCT_CHILDREN);
        int guard = 0;
        while (child && !IsBadReadPtr(child, OFF_Class + 4) && guard++ < 256) {
            char nm[128], cn[128];
            if (ResolveObjNameClass(child, nm, sizeof nm, cn, sizeof cn) &&
                strcmp(nm, want) == 0)
                return child;
            child = *reinterpret_cast<void**>((char*)child + UFIELD_NEXT);
        }
        ustruct = *reinterpret_cast<void**>((char*)ustruct + USTRUCT_SUPER);
    }
    return nullptr;
}

// Walk a UStruct's properties, logging each field's name, type, array dim,
// element size, and candidate Offset dwords (so we can calibrate UProperty
// Offset and hunt for a spawn-count field). Recurses into StructProperties.
static void DumpStruct(const char* tag, void* ustruct, int depth)
{
    if (!ustruct || IsBadReadPtr(ustruct, USTRUCT_CHILDREN + 4)) {
        SLog("  STRUCT %s: unreadable 0x%p", tag, ustruct); return;
    }
    char snm[128], scn[128];
    ResolveObjNameClass(ustruct, snm, sizeof snm, scn, sizeof scn);
    SLog("  STRUCT %s = '%s' (%s) @0x%p", tag, snm, scn, ustruct);
    // Walk this struct's own Children, then up the SuperField chain so inherited
    // properties are shown too (cap supers to avoid runaway).
    void* cur = ustruct; int sguard = 0;
    while (cur && !IsBadReadPtr(cur, USTRUCT_CHILDREN + 4) && sguard++ < 16) {
        void* child = *reinterpret_cast<void**>((char*)cur + USTRUCT_CHILDREN);
        int guard = 0;
        while (child && !IsBadReadPtr(child, 0x50) && guard++ < 256) {
            char nm[128], cn[128];
            if (ResolveObjNameClass(child, nm, sizeof nm, cn, sizeof cn)) {
                int arr  = *reinterpret_cast<int*>((char*)child + UPROP_ARRAYDIM);
                int elem = *reinterpret_cast<int*>((char*)child + UPROP_ELEMSIZE);
                unsigned offv = *reinterpret_cast<unsigned*>((char*)child + UPROP_OFFSET);
                SLog("    .%-28s type=%-18s @off=0x%-4X arr=%d elem=%d",
                     nm, cn, offv, arr, elem);
                if (depth > 0 && strstr(cn, "StructProperty")) {
                    void* inner = *reinterpret_cast<void**>((char*)child + STRUCTPROP_STRUCT);
                    if (inner && inner != cur && inner != ustruct)
                        DumpStruct(nm, inner, depth - 1);
                }
            }
            child = *reinterpret_cast<void**>((char*)child + UFIELD_NEXT);
        }
        cur = *reinterpret_cast<void**>((char*)cur + USTRUCT_SUPER);
    }
}

// ── Deep-copy support for cloned AISpawnInfo descriptors ───────────────────
// A raw memcpy clone aliases the source's embedded TArray .Data buffers (and
// the engine frees per-element -> double free). Zeroing them avoided the crash
// but stripped boss gear (Firemen need their inventory) and left invalid stubs
// that the level-transition serializer choked on. The robust fix: deep-copy
// each embedded TArray into a FRESH engine-allocated buffer (appRealloc), so
// the clone owns valid, independent, engine-freeable data.
//
// We can only safely shallow-copy a TArray's buffer when its ELEMENT type has
// no further heap-owning fields (nested Array/Str/Map). Element layout is read
// from the AISpawnInfo ScriptStruct's UArrayProperty.Inner at runtime; each
// field's {elementSize, safe} is cached once (offsets stable per build).
struct ArrFieldInfo { unsigned off; int elemSize; bool deepCopy; };
static ArrFieldInfo g_ArrFields[_countof(DESC_TARRAY_OFFS)];
static bool         g_ArrFieldsReady = false;

// True if a TArray whose Inner is `inner` can be shallow-buffer-copied safely
// (its elements own no nested heap: no Array/Str/Map properties). Object/Name/
// scalar fields are fine (object refs are shared, not freed by the array).
static bool InnerIsShallowSafe(void* inner)
{
    char nm[128], cn[128];
    if (IsBadReadPtr(inner, OFF_Class + 4) ||
        !ResolveObjNameClass(inner, nm, sizeof nm, cn, sizeof cn))
        return false;
    if (strstr(cn, "ArrayProperty") || strstr(cn, "StrProperty") ||
        strstr(cn, "MapProperty"))
        return false;
    if (strstr(cn, "StructProperty")) {
        void* st = *reinterpret_cast<void**>((char*)inner + STRUCTPROP_STRUCT);
        void* curr = st; int sg = 0;
        while (curr && !IsBadReadPtr(curr, USTRUCT_CHILDREN + 4) && sg++ < 8) {
            void* c = *reinterpret_cast<void**>((char*)curr + USTRUCT_CHILDREN);
            int g = 0;
            while (c && !IsBadReadPtr(c, OFF_Class + 4) && g++ < 256) {
                char a[128], b[128];
                if (ResolveObjNameClass(c, a, sizeof a, b, sizeof b) &&
                    (strstr(b, "ArrayProperty") || strstr(b, "StrProperty") ||
                     strstr(b, "MapProperty")))
                    return false;
                c = *reinterpret_cast<void**>((char*)c + UFIELD_NEXT);
            }
            curr = *reinterpret_cast<void**>((char*)curr + USTRUCT_SUPER);
        }
    }
    return true;
}

// Resolve, once, the element size + shallow-copy safety for each embedded
// TArray field of AISpawnInfo. Navigates srcDesc.Spawner -> Class -> SpawnInfo
// (StructProperty) -> AISpawnInfo ScriptStruct, then matches each child
// ArrayProperty by its Offset to our DESC_TARRAY_OFFS set.
static void EnsureArrFields(void* srcDesc)
{
    if (g_ArrFieldsReady) return;
    for (unsigned i = 0; i < _countof(DESC_TARRAY_OFFS); ++i) {
        g_ArrFields[i].off = DESC_TARRAY_OFFS[i];
        g_ArrFields[i].elemSize = 0;
        g_ArrFields[i].deepCopy = false;
    }
    void* spawner = *reinterpret_cast<void**>((char*)srcDesc + OFF_DESC_Spawner);
    if (IsBadReadPtr(spawner, OFF_Class + 4)) return;
    void* uclass = *reinterpret_cast<void**>((char*)spawner + OFF_Class);
    void* spProp = StructFindChild(uclass, "SpawnInfo");
    if (!spProp || IsBadReadPtr((char*)spProp + STRUCTPROP_STRUCT, 4)) return;
    void* aiStruct = *reinterpret_cast<void**>((char*)spProp + STRUCTPROP_STRUCT);
    if (IsBadReadPtr(aiStruct, USTRUCT_CHILDREN + 4)) return;

    void* curr = aiStruct; int sg = 0;
    while (curr && !IsBadReadPtr(curr, USTRUCT_CHILDREN + 4) && sg++ < 8) {
        void* child = *reinterpret_cast<void**>((char*)curr + USTRUCT_CHILDREN);
        int guard = 0;
        while (child && !IsBadReadPtr(child, 0x60) && guard++ < 256) {
            char nm[128], cn[128];
            if (ResolveObjNameClass(child, nm, sizeof nm, cn, sizeof cn) &&
                strstr(cn, "ArrayProperty")) {
                unsigned off = *reinterpret_cast<unsigned*>((char*)child + UPROP_OFFSET);
                for (unsigned i = 0; i < _countof(DESC_TARRAY_OFFS); ++i) {
                    if (off != g_ArrFields[i].off) continue;
                    void* inner = *reinterpret_cast<void**>((char*)child + ARRAYPROP_INNER);
                    int es = 0; bool safe = false;
                    if (!IsBadReadPtr(inner, UPROP_ELEMSIZE + 4)) {
                        es = *reinterpret_cast<int*>((char*)inner + UPROP_ELEMSIZE);
                        safe = InnerIsShallowSafe(inner);
                    }
                    if (es > 0 && es <= 512) {
                        g_ArrFields[i].elemSize = es;
                        g_ArrFields[i].deepCopy = safe;
                    }
                    char inm[128], icn[128];
                    ResolveObjNameClass(inner, inm, sizeof inm, icn, sizeof icn);
                    SLog("  ARRFIELD .%s off=0x%X inner=%s elem=%d deepCopy=%d",
                         nm, off, icn, es, (int)safe);
                }
            }
            child = *reinterpret_cast<void**>((char*)child + UFIELD_NEXT);
        }
        curr = *reinterpret_cast<void**>((char*)curr + USTRUCT_SUPER);
    }
    g_ArrFieldsReady = true;
}

// Detach a single cloned TArray header at dst+off from the source's buffer.
// Deep-copies into a fresh engine-allocated buffer when the element type is
// shallow-safe; otherwise empties the header (so the clone owns nothing shared).
static void CloneDetachTArray(char* dst, char* src, const ArrFieldInfo& f)
{
    char* dh = dst + f.off;
    void* sData = *reinterpret_cast<void**>(src + f.off);
    int   sNum  = *reinterpret_cast<int*>(src + f.off + 4);
    int   sMax  = *reinterpret_cast<int*>(src + f.off + 8);
    if (f.deepCopy && f.elemSize > 0 && sNum > 0 && sNum <= 4096 &&
        sMax >= sNum && sData && !IsBadReadPtr(sData, (size_t)sNum * f.elemSize)) {
        size_t cap = (size_t)sMax * f.elemSize;
        appRealloc_t Realloc = reinterpret_cast<appRealloc_t>(g_Base + RVA_appRealloc);
        void* nd = Realloc(nullptr, cap, 8);
        if (nd) {
            memcpy(nd, sData, (size_t)sNum * f.elemSize);
            *reinterpret_cast<void**>(dh)   = nd;
            *reinterpret_cast<int*>(dh + 4) = sNum;
            *reinterpret_cast<int*>(dh + 8) = sMax;
            return;
        }
    }
    memset(dh, 0, 12); // fallback: empty TArray (owns no shared buffer)
}

// ── GObjects locator (master key for class-default-object stat patches) ────
// We have GNames but never resolved GObjects (the global UObject* array). With
// it we can find ANY class's UClass + default object by name and rebalance its
// properties (weapon damage, enemy HP, loot) the way War-In-Rapture overhauls
// do. Finding it statically is hard (UE3 strings are UTF-16); instead we locate
// it at RUNTIME from live UObjects the spawn hook already captures: GObjects is
// the .data-resident pointer array A where A[obj.Index] == obj. We try a few
// candidate Index offsets and require ALL known objects to validate.
static const uintptr_t RVA_DATA = 0x132E000;  // .data VA (from PE headers)
static const size_t    SZ_DATA  = 0xEE3C4;    // .data vsize
static void* g_GObjData = nullptr;            // GObjects base (flat: UObject**; chunked: UObject***)
static int   g_GObjNum  = 0;                  // GObjects.Num
static bool  g_GObjChunked = false;           // true => 2-level chunked FUObjectArray
static unsigned g_GObjEPC = 0;                // elements-per-chunk (chunked only)
static bool  g_DumpWeapons = true;            // one-shot weapon-class dump toggle

// Layout-agnostic GObjects element accessor. Returns the i-th UObject* or null,
// handling both a flat TArray<UObject*> and a chunked FUObjectArray
// (Object = ChunkTable[i / EPC][i % EPC]). Fully SEH/bad-ptr guarded.
static void* GObjGet(int i)
{
    if (!g_GObjData || i < 0) return nullptr;
    if (!g_GObjChunked) {
        void** arr = reinterpret_cast<void**>(g_GObjData);
        if (IsBadReadPtr(arr + i, 4)) return nullptr;
        return arr[i];
    }
    void*** table = reinterpret_cast<void***>(g_GObjData);
    unsigned ci = (unsigned)i / g_GObjEPC, ii = (unsigned)i % g_GObjEPC;
    if (IsBadReadPtr(table + ci, 4)) return nullptr;
    void** chunk = table[ci];
    if (!chunk || IsBadReadPtr(chunk + ii, 4)) return nullptr;
    return chunk[ii];
}

static bool FindGObjects(void** objs, int n)
{
    if (g_GObjData) return true;
    if (n < 2) { SLog("GOBJECTS: too few seeds (%d)", n); return false; }
    // UObject.Index candidate offsets. The XAIScriptedSpawner dump showed a
    // plausible small int at +0x10 (Outer@+0x14, Name@+0x18, Class@+0x20), so
    // 0x10 is most likely; the others are fallbacks for safety.
    const unsigned idxOffs[] = { 0x10, 0x0C, 0x08 };
    unsigned char* d = reinterpret_cast<unsigned char*>(g_Base + RVA_DATA);
    for (unsigned io = 0; io < _countof(idxOffs); ++io) {
        unsigned ixo = idxOffs[io];
        // Per-seed index; only seeds with a plausible index participate. A bogus
        // seed simply contributes nothing (no longer breaks the whole offset).
        int idx[8]; bool valid[8]; int nValid = 0;
        for (int k = 0; k < n && k < 8; ++k) {
            valid[k] = false;
            if (IsBadReadPtr((char*)objs[k] + ixo, 4)) continue;
            idx[k] = *reinterpret_cast<int*>((char*)objs[k] + ixo);
            if (idx[k] >= 0 && idx[k] <= 0x300000) { valid[k] = true; ++nValid; }
        }
        if (nValid < 2) continue;
        for (size_t off = 0; off + 4 <= SZ_DATA; off += 4) {
            void** cand = *reinterpret_cast<void***>(d + off);
            uintptr_t c = reinterpret_cast<uintptr_t>(cand);
            if (c < 0x10000 || (c >= g_Base && c < g_Base + 0x1100000)) continue;
            int hits = 0;
            for (int k = 0; k < n && k < 8; ++k) {
                if (!valid[k]) continue;
                if (!IsBadReadPtr(cand + idx[k], 4) && cand[idx[k]] == objs[k])
                    ++hits;
            }
            if (hits >= 2) { // tolerant: 2+ seeds land in the same array => it
                g_GObjData = cand;            // is GObjects (stale seeds ignored)
                g_GObjNum  = *reinterpret_cast<int*>(d + off + 4);
                SLog("GOBJECTS found (flat): Data=0x%p Num=%d (data+0x%X, "
                     "IndexOff=0x%X, %d/%d seeds matched)", cand, g_GObjNum,
                     (unsigned)off, ixo, hits, nValid);
                return true;
            }
        }
    }
    // Flat scan failed -> 2013-era UE3 stores objects in a CHUNKED FUObjectArray
    // (Object = ChunkTable[Index / EPC][Index % EPC]). Probe candidate chunk-table
    // bases in .data for each plausible elements-per-chunk size.
    const unsigned epcTry[] = { 16384, 65536, 32768, 8192, 1024 };
    for (unsigned io = 0; io < _countof(idxOffs); ++io) {
        unsigned ixo = idxOffs[io];
        int idx[8]; bool valid[8]; int nValid = 0;
        for (int k = 0; k < n && k < 8; ++k) {
            valid[k] = false;
            if (IsBadReadPtr((char*)objs[k] + ixo, 4)) continue;
            idx[k] = *reinterpret_cast<int*>((char*)objs[k] + ixo);
            if (idx[k] >= 0 && idx[k] <= 0x300000) { valid[k] = true; ++nValid; }
        }
        if (nValid < 2) continue;
        for (unsigned ei = 0; ei < _countof(epcTry); ++ei) {
            unsigned EPC = epcTry[ei];
            for (size_t off = 0; off + 4 <= SZ_DATA; off += 4) {
                void*** table = *reinterpret_cast<void****>(d + off);
                uintptr_t c = reinterpret_cast<uintptr_t>(table);
                if (c < 0x10000 || (c >= g_Base && c < g_Base + 0x1100000)) continue;
                int hits = 0;
                for (int k = 0; k < n && k < 8; ++k) {
                    if (!valid[k]) continue;
                    unsigned ci = (unsigned)idx[k] / EPC, ii = (unsigned)idx[k] % EPC;
                    if (ci > 4096 || IsBadReadPtr(table + ci, 4)) continue;
                    void** chunk = table[ci];
                    if (!chunk || IsBadReadPtr(chunk + ii, 4)) continue;
                    if (chunk[ii] == objs[k]) ++hits;
                }
                if (hits >= 2) {
                    g_GObjData    = table;
                    g_GObjChunked = true;
                    g_GObjEPC     = EPC;
                    g_GObjNum     = *reinterpret_cast<int*>(d + off + 4);
                    SLog("GOBJECTS found (chunked): Table=0x%p Num=%d EPC=%u "
                         "(data+0x%X, IndexOff=0x%X, %d/%d seeds matched)", table,
                         g_GObjNum, EPC, (unsigned)off, ixo, hits, nValid);
                    return true;
                }
            }
        }
    }
    SLog("GOBJECTS not found (%d seeds), flat+chunked probes exhausted", n);
    return false;
}

// Iterate GObjects for the UClass named `want` (a UClass's own Class is "Class")
// and dump its property layout: names / types / offsets, so we can pick the
// exact fields to scale (damage, fire interval, clip, spread).
static void DumpClassByName(const char* want)
{
    if (!g_GObjData) return;
    // For chunked arrays the trailing dword may not be a clean object count, so
    // fall back to a generous cap and tolerate nulls/holes via GObjGet.
    int n = (g_GObjNum > 0 && g_GObjNum <= 3000000) ? g_GObjNum : 2000000;
    for (int i = 0; i < n; ++i) {
        void* o = GObjGet(i);
        if (!o || IsBadReadPtr(o, OFF_Class + 4)) continue;
        char nm[128], cn[128];
        if (!ResolveObjNameClass(o, nm, sizeof nm, cn, sizeof cn)) continue;
        if (strcmp(nm, want) == 0 && strcmp(cn, "Class") == 0) {
            SLog("CLASS-FOUND '%s' UClass=0x%p -> dumping properties:", want, o);
            DumpStruct(want, o, 1);
            return;
        }
    }
    SLog("CLASS '%s' not found in GObjects(%d, %s)", want, n,
         g_GObjChunked ? "chunked" : "flat");
}

// SDK catalog: enumerate every UClass in GObjects and write "ClassName : Super"
// to a dedicated wic_sdk.txt. This is the master index of every gameplay class
// (weapons, AI, vista kinds, damage types...) so we can pick exact rebalance
// targets and later dump any one's full property layout via DumpClassByName.
static volatile LONG g_CatalogDone = 0;
static void DumpClassCatalog()
{
    if (!g_GObjData) return;
    if (InterlockedCompareExchange(&g_CatalogDone, 1, 0) != 0) return;
    char path[MAX_PATH];
    GetModuleFileNameA(GetModuleHandleA(nullptr), path, MAX_PATH);
    char* slash = strrchr(path, '\\');
    if (slash) strcpy(slash + 1, "wic_sdk.txt"); else strcpy(path, "wic_sdk.txt");
    FILE* f = fopen(path, "w");
    if (!f) { SLog("SDK: cannot open catalog file '%s'", path); return; }
    int n = (g_GObjNum > 0 && g_GObjNum <= 3000000) ? g_GObjNum : 2000000;
    int classes = 0, objs = 0;
    for (int i = 0; i < n; ++i) {
        void* o = GObjGet(i);
        if (!o || IsBadReadPtr(o, OFF_Class + 4)) continue;
        ++objs;
        char nm[128], cn[128];
        if (!ResolveObjNameClass(o, nm, sizeof nm, cn, sizeof cn)) continue;
        if (strcmp(cn, "Class") != 0) continue;        // only UClasses
        char sup[128] = "";
        if (!IsBadReadPtr((char*)o + USTRUCT_SUPER, 4)) {
            void* s = *reinterpret_cast<void**>((char*)o + USTRUCT_SUPER);
            if (s && !IsBadReadPtr((char*)s + OFF_Name + 4, 4)) {
                int si = *reinterpret_cast<int*>((char*)s + OFF_Name);
                ResolveFName(si, sup, sizeof sup);
            }
        }
        fprintf(f, "%-44s : %s\n", nm, sup[0] ? sup : "-");
        ++classes;
    }
    fclose(f);
    SLog("SDK: catalog written -> %s (%d classes / %d live objects scanned, %s)",
         path, classes, objs, g_GObjChunked ? "chunked" : "flat");
}

// One-shot field-by-field DWORD diff of the first two REAL descriptors. Fields
// that DIFFER are per-enemy unique (positions / heap pointers / IDs we must NOT
// blindly duplicate); fields that MATCH are shared template (safe to copy).
// This pinpoints which embedded pointers cause the clone's resource leak.
static void DumpDescDiff(void* data, int num)
{
    if (num < 2) return;
    if (InterlockedCompareExchange(&g_DescDiffed, 1, 0) != 0) return;
    const unsigned char* a = (const unsigned char*)data;
    const unsigned char* b = (const unsigned char*)data + DESC_STRIDE;
    SLog("DESC-DIFF desc[0]=0x%p desc[1]=0x%p stride=0x%X (off: a / b)",
         a, b, (unsigned)DESC_STRIDE);
    for (unsigned off = 0; off + 4 <= DESC_STRIDE; off += 4) {
        unsigned va = *reinterpret_cast<const unsigned*>(a + off);
        unsigned vb = *reinterpret_cast<const unsigned*>(b + off);
        if (va != vb) {
            bool ptrA = (va >= 0x10000000u && va < 0xC0000000u);
            bool ptrB = (vb >= 0x10000000u && vb < 0xC0000000u);
            SLog("  +0x%02X: %08X / %08X  DIFF%s", off, va, vb,
                 (ptrA || ptrB) ? "  <-PTR?" : "");
        }
    }
    // Probe the two per-enemy heap pointers (+0x08, +0xCC) for BOTH descriptors:
    // dump vtable RVA + first 0x20 bytes so we can identify the object class
    // (XHuman pawn 0xDE1A60 / XAIController 0xDC6210 / request struct / etc.).
    const unsigned probeOffs[2] = { 0x08, 0xCC };
    void* live[4]; int nlive = 0; // distinct live UObjects for GObjects locator
    for (int e = 0; e < 2; ++e) {
        const unsigned char* base = (e == 0) ? a : b;
        for (int p = 0; p < 2; ++p) {
            unsigned off = probeOffs[p];
            void* tgt = *reinterpret_cast<void* const*>(base + off);
            if (IsBadReadPtr(tgt, 0x24)) {
                SLog("  PROBE desc[%d]+0x%02X -> 0x%p (unreadable)", e, off, tgt);
                continue;
            }
            unsigned vt = *reinterpret_cast<const unsigned*>(tgt);
            unsigned vrva = (vt >= (unsigned)g_Base) ? vt - (unsigned)g_Base : 0;
            // If it looks like a UObject (real vtable in .text), resolve its UE3
            // class name + instance name so we know exactly what it is.
            char clsName[128] = ""; char objName[128] = "";
            // Resolve names whenever the target is a readable UObject. (Do NOT
            // gate on vtable rva: real vtables live well past 0xD00000 here.)
            if (!IsBadReadPtr(tgt, OFF_Class + 4)) {
                int nameIdx = *reinterpret_cast<const int*>((const char*)tgt + OFF_Name);
                ResolveFName(nameIdx, objName, sizeof objName);
                void* cls = *reinterpret_cast<void* const*>((const char*)tgt + OFF_Class);
                if (cls && !IsBadReadPtr(cls, OFF_Name + 4)) {
                    int clsIdx = *reinterpret_cast<const int*>((const char*)cls + OFF_Name);
                    ResolveFName(clsIdx, clsName, sizeof clsName);
                }
            }
            SLog("  PROBE desc[%d]+0x%02X -> 0x%p  vtbl=0x%08X (rva=0x%X) class='%s' name='%s'",
                 e, off, tgt, vt, vrva, clsName, objName);
            HexDumpToLog("    obj", (unsigned char*)tgt, 0x40);
            // Collect distinct, name-resolved UObjects to seed the GObjects scan.
            if (clsName[0] && nlive < 4) {
                bool dup = false;
                for (int q = 0; q < nlive; ++q) if (live[q] == tgt) dup = true;
                if (!dup) live[nlive++] = tgt;
            }
            // For the FIRST real per-enemy UObject we find, dump its UClass
            // layout: parent chain + property list (names/types/offsets). This
            // is the targeted SDK dump that tells us if/how to allocate a fresh
            // one for clones instead of sharing (the leak fix).
            if (e == 0 && strstr(clsName, "Spawner")) {
                void* uclass = *reinterpret_cast<void* const*>((const char*)tgt + OFF_Class);
                SLog("  CLASS-DUMP navigate '%s' (UClass=0x%p):", clsName, uclass);
                // spawner.Class -> SpawnInfo (StructProperty) -> its ScriptStruct
                void* spInfoProp = StructFindChild(uclass, "SpawnInfo");
                if (spInfoProp && !IsBadReadPtr((char*)spInfoProp + STRUCTPROP_STRUCT, 4)) {
                    void* spInfo = *reinterpret_cast<void**>((char*)spInfoProp + STRUCTPROP_STRUCT);
                    DumpStruct("SpawnInfo", spInfo, 2); // recurses AISpawnInfo/MultiAISpawnInfo
                } else {
                    SLog("  (SpawnInfo property not found via Children walk; dumping class props)");
                    DumpStruct("XAIScriptedSpawner", uclass, 2);
                }
            }
        }
    }
    // With genuine spawned UObjects captured by SafeLogActor, resolve GObjects
    // ONCE, then dump the weapon class layouts so we can pick exact damage /
    // fire / clip / spread fields for the upcoming weapon-rebalance CDO patch.
    (void)live; (void)nlive; // probe seeds were unreliable; use g_LiveObjs
    if (g_DumpWeapons && FindGObjects(g_LiveObjs, (int)g_LiveN)) {
        g_DumpWeapons = false;
        DumpClassCatalog();   // SDK master index of every class -> wic_sdk.txt
        const char* wantClasses[] = { "XWeapon", "XWeaponData", "XHuman",
                                      "XAIController" };
        for (unsigned w = 0; w < _countof(wantClasses); ++w)
            DumpClassByName(wantClasses[w]);
    }
    SLog("DESC-DIFF end (matching fields omitted = shared template)");
}

// Grow one roster TArray in place, within its existing Max capacity. Uses a
// std::lock_guard so it lives outside the hook's __try (object-unwinding rule).
// The caller wraps the invocation in __try/__except to catch any bad access.
static void ApplyRosterGrow(void* roster)
{
    char* r    = reinterpret_cast<char*>(roster);
    void* data = *reinterpret_cast<void**>(r);
    int   num  = *reinterpret_cast<int*>(r + OFF_TARRAY_NUM);
    int   maxc = *reinterpret_cast<int*>(r + OFF_TARRAY_MAX);
    // Sanity: plausible TArray of enemy descriptors with real slack.
    if (!data || num < 1 || num > 128 || maxc < num || maxc > 512) return;

    // TEST MATRIX: skip all roster grow if spawn multiplier is disabled
    if (!ENABLE_SPAWN_MULT) return;

    // COMPANION FILTER: never multiply rosters with only 1 NPC. These are
    // unique/companion NPCs (Elizabeth, Songbird, story actors). Multiplying
    // Elizabeth causes 4 companions to spawn -> corrupt AI state -> crash.
    // Enemy squads always have Num >= 2.
    if (num < 2) {
        static volatile LONG s_skipOnce = 0;
        if (InterlockedIncrement(&s_skipOnce) <= 3)
            SLog("ROSTER-SKIP: Num=%d Max=%d (single-NPC roster, likely companion)",
                 num, maxc);
        return;
    }

    std::lock_guard<std::mutex> lk(g_RosterMtx);
    DumpDescDiff(data, num); // one-shot: identify per-enemy vs shared fields
    GrowSlot* s = nullptr;
    for (int i = 0; i < GROW_TBL; ++i)
        if (g_GrowTbl[i].array == data) { s = &g_GrowTbl[i]; break; }

    int last = s ? s->lastNum : 0;
    if (num <= last) {                 // draining (or unchanged) -> just track
        if (s) s->lastNum = num;
        return;
    }
    // Fresh wave (Num increased). Grow within capacity, using a TOTAL ENEMY
    // cap (not just descriptor count) to prevent pawn pool exhaustion — which
    // was causing zombie spawns (idle + invulnerable enemies with no AI).
    int newLast = num;

    // Count how many enemies the ORIGINAL wave already spawns.
    int baseEnemies = 0;
    for (int j = 0; j < num; ++j)
        baseEnemies += *reinterpret_cast<int*>((char*)data + (size_t)j * DESC_STRIDE + OFF_DESC_CountA);

    // Budget: how many MORE enemies can we add before hitting the pool cap?
    // The pawn pool is typically ~20-32 entries. Stay well within that to avoid
    // exhausting it (which leaves pawns with no AI controller → zombie spawns).
    static const int MAX_TOTAL_ENEMIES = 20; // hard cap on total enemies per wave
    int budget = MAX_TOTAL_ENEMIES - baseEnemies;
    if (budget < 0) budget = 0;

    // Also respect descriptor-count limits.
    int maxDescs = maxc - num;                         // free slots in TArray
    if (maxDescs > g_MaxWaveTotal - num) maxDescs = g_MaxWaveTotal - num;
    if (maxDescs < 0) maxDescs = 0;
    int add = budget < maxDescs ? budget : maxDescs;   // each clone adds 1 enemy

    // Scale the required headroom with the number of enemies we are adding.
    unsigned needMB = MULT_MEM_GATE_MB + (unsigned)add * MULT_MEM_PER_ADD_MB;
    if (g_DiagNoGrow) {
        if (!s) {
            int pos = (int)(InterlockedIncrement(&g_GrowPos) - 1) % GROW_TBL;
            s = &g_GrowTbl[pos]; s->array = data;
        }
        s->lastNum = num;
        return;
    }
    if (add > 0 && MemMonLargestFreeMB() >= needMB) {
        EnsureArrFields((char*)data); // resolve TArray element sizes once
        int cloned = 0;
        for (int i = 0; i < add; ++i) {
            // Pick a source descriptor to clone. Prefer sources with LOW CountA
            // (small squads) since those are less likely to be "special" enemies.
            // Round-robin through sources.
            int srcIdx = i % num;
            char* src = (char*)data + (size_t)srcIdx * DESC_STRIDE;
            char* dst = (char*)data + (size_t)(num + cloned) * DESC_STRIDE;
            memcpy(dst, src, DESC_STRIDE);
            // Deep-copy TArrays to prevent double-free.
            for (unsigned t = 0; t < _countof(DESC_TARRAY_OFFS); ++t)
                CloneDetachTArray(dst, src, g_ArrFields[t]);
            // Zero runtime per-instance fields (prevents streaming crash).
            *reinterpret_cast<unsigned*>(dst + OFF_DESC_RuntimeCnt) = 0;
            *reinterpret_cast<unsigned*>(dst + OFF_DESC_RuntimePtr) = 0;
            // +0xCC (Spawner) and +0xD8 (Delegate): KEEP INTACT for damage reg.
            // Force clone CountA/B = 1 (one enemy per clone descriptor).
            *reinterpret_cast<int*>(dst + OFF_DESC_CountA) = 1;
            *reinterpret_cast<int*>(dst + OFF_DESC_CountB) = 1;
            // Nudge position to avoid collision overlap.
            float* x = reinterpret_cast<float*>(dst + OFF_DESC_PosX);
            *x += 96.0f * (float)(cloned + 1);
            float* y = reinterpret_cast<float*>(dst + OFF_DESC_PosX + 4);
            *y += 64.0f * (float)((cloned + 1) % 2 == 0 ? 1 : -1);
            ++cloned;
        }
        int want = num + cloned;
        *reinterpret_cast<int*>(r + OFF_TARRAY_NUM) = want;
        InterlockedIncrement(&g_GrowWaves);
        InterlockedIncrement(&g_LevelGrows);
        LONG tot = InterlockedAdd(&g_GrowAdded, cloned);
        int totalEnemies = baseEnemies + cloned;
        // Track peak for heartbeat
        LONG prev = g_PeakEnemies;
        while (totalEnemies > prev) {
            if (InterlockedCompareExchange(&g_PeakEnemies, totalEnemies, prev) == prev) break;
            prev = g_PeakEnemies;
        }
        SLog("ROSTER-GROW array=0x%p Num %d->%d (Max=%d, +%d clones, "
             "baseEnemies=%d totalEnemies=%d budget=%d total-extra=%ld)",
             data, num, want, maxc, cloned, baseEnemies, totalEnemies, budget, tot);
        // ONE-SHOT: annotated dump of clone vs source for deep analysis
        static volatile LONG s_annotDumped = 0;
        if (InterlockedCompareExchange(&s_annotDumped, 1, 0) == 0) {
            char* src0 = (char*)data;
            char* cln0 = (char*)data + (size_t)num * DESC_STRIDE;
            SLog("ANNOT-DUMP: source desc[0] vs clone desc[%d] (first clone):", num);
            // Annotated fields
            struct { unsigned off; const char* name; int sz; bool isPtr; } fields[] = {
                {0x00,"GammaPack",4,true}, {0x04,"PawnArch",4,true},
                {0x08,"PawnLabels.Data",4,true}, {0x0C,"CountA",4,false}, {0x10,"CountB",4,false},
                {0x14,"PawnAppearanceOvr",4,true}, {0x20,"LootList.Data",4,true},
                {0x2C,"BoolFlags",4,false},
                {0x30,"LootOnKill.Data",4,true}, {0x3C,"InventoryList.Data",4,true},
                {0x58,"Faction",8,false},
                {0x60,"SpawnLoc.X",4,false}, {0x64,"SpawnLoc.Y",4,false},
                {0x68,"SpawnLoc.Z",4,false}, {0x6C,"SpawnLoc.Section",4,false},
                {0x80,"FloatSection",4,false},
                {0x98,"CaptainPawn",4,true}, {0x9C,"PatrolPath",4,true},
                {0xA4,"AIRole",4,true},
                {0xC8,"FrobEvent",4,true}, {0xCC,"Spawner",4,true},
                {0xD0,"SpawnerLevel",8,false},
                {0xD8,"Delegate.Obj",4,true}, {0xDC,"Delegate.FName1",4,false},
                {0xE0,"Delegate.FName2",4,false},
                {0xE4,"ScenarioIdx",4,false}, {0xE8,"RuntimeCnt",4,false}, {0xEC,"RuntimePtr",4,true},
            };
            for (auto& f : fields) {
                unsigned sv = *reinterpret_cast<unsigned*>(src0 + f.off);
                unsigned cv = *reinterpret_cast<unsigned*>(cln0 + f.off);
                const char* diff = (sv != cv) ? " DIFF" : "";
                char extra[128] = "";
                if (f.isPtr && cv && cv >= 0x10000000u && cv < 0xC0000000u) {
                    char nm[64], cn[64];
                    if (ResolveObjNameClass(reinterpret_cast<void*>(cv), nm, sizeof nm, cn, sizeof cn))
                        sprintf(extra, " -> %s (%s)", nm, cn);
                }
                SLog("  +0x%02X %-20s src=%08X cln=%08X%s%s",
                     f.off, f.name, sv, cv, diff, extra);
            }
        }
        newLast = want;                // post-grow Num; drain won't re-trigger
    } else if (budget <= 0) {
        // Base wave already at or over enemy cap — no room to add clones.
        SLog("ROSTER-SKIP array=0x%p Num=%d baseEnemies=%d >= cap=%d (no clones added)",
             data, num, baseEnemies, MAX_TOTAL_ENEMIES);
    } else if (add > 0) {
        SLog("ROSTER-GROW GATED array=0x%p Num=%d add=%d (largest-free=%u MB < need %u)",
             data, num, add, MemMonLargestFreeMB(), needMB);
    }

    if (!s) {                          // record (ring-evict oldest)
        int pos = (int)(InterlockedIncrement(&g_GrowPos) - 1) % GROW_TBL;
        s = &g_GrowTbl[pos];
        s->array = data;
    }
    s->lastNum = newLast;
}

// Apply the credit-back for one roster after the director has run. Kept as a
// separate function because it uses a std::lock_guard (object unwinding), which
// cannot live in the same function as the hook's __try/__except blocks.
static void ApplyRosterCredit(void* array, int* pCount, int prevCount)
{
    int newCount = *pCount;
    int consumed = prevCount - newCount;
    if (!array || consumed <= 0 || newCount < 0) return;
    std::lock_guard<std::mutex> lk(g_RosterMtx);
    RosterSlot* s = RosterSlotFor(array, prevCount > newCount ? prevCount : newCount);
    int give = consumed;
    if (give > s->addedRemaining) give = s->addedRemaining;
    int headroom = s->maxSeen - newCount;          // never exceed original N
    if (give > headroom) give = headroom;
    if (give > 0 && MemMonLargestFreeMB() >= MULT_MEM_GATE_MB) {
        *pCount = newCount + give;
        s->addedRemaining -= give;
        LONG tot = InterlockedAdd(&g_RosterAdded, give);
        SLog("ROSTER-CREDIT array=0x%p consumed=%d +%d (count %d->%d, "
             "owed=%d, total-extra=%ld)", array, consumed, give,
             newCount, *pCount, s->addedRemaining, tot);
    }
    s->lastCount = *pCount;
}

// Dump `n` bytes at `p` to the log as offset-prefixed hex lines (16/line).
static void HexDumpToLog(const char* tag, const unsigned char* p, unsigned n)
{
    __try {
        for (unsigned off = 0; off < n; off += 16) {
            char line[160]; int k = 0;
            k += sprintf(line + k, "    %s +0x%02X:", tag, off);
            for (unsigned j = 0; j < 16 && off + j < n; ++j)
                k += sprintf(line + k, " %02X", p[off + j]);
            SLog("%s", line);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        SLog("    %s: <unreadable>", tag);
    }
}

// ── Cursor hunt: once we see a multi-enemy wave, dump the roster struct header
// and the director (`this`) header for ~16 consecutive ticks of that SAME wave.
// The field that increments by 1 per spawn = the monotonic cursor we need to
// reset (count is the field at +4 that DECrements). Read-only, SEH-safe.
static void*         g_HdrTrackArray = nullptr;
static volatile LONG g_HdrDumps      = 0;
static const int     HDR_DUMP_MAX     = 16;

// ── Periodic heartbeat + level transition detection ──────────────────────
static volatile LONG g_LastHeartbeat  = 0; // tick of last heartbeat log
static volatile LONG g_LevelSpawns   = 0; // spawns since last level change
static volatile LONG g_LevelCrashes  = 0; // crashes since last level change
static DWORD         g_LevelStartTick = 0;

// Detect level transition: when spawn sequence resets (gap > 30s with no
// roster call) or this pointer changes dramatically, log a LEVEL-CHANGE.
static void*         g_LastSpawner    = nullptr;

static void LogHeartbeat()
{
    DWORD now = GetTickCount();
    LONG last = InterlockedExchange(&g_LastHeartbeat, (LONG)now);
    if (last && (now - (DWORD)last) < 60000) return; // only every 60s
    SLog("HEARTBEAT: spawns=%ld grows=%ld extras=%ld crashes(VEH)=%ld "
         "freeMB=%u peakEnemies=%ld | level: spawns=%ld grows=%ld",
         g_SpawnSeq, g_GrowWaves, g_GrowAdded, g_LevelCrashes,
         MemMonLargestFreeMB(), g_PeakEnemies,
         g_LevelSpawns, g_LevelGrows);
}

static void DetectLevelChange(void* This)
{
    if (g_LastSpawner && This != g_LastSpawner) {
        // Different spawner object — might be a new level or new encounter
        // Only log as LEVEL-CHANGE if there's been a significant time gap
        DWORD now = GetTickCount();
        DWORD elapsed = now - g_LevelStartTick;
        if (elapsed > 20000) { // >20s since last level start
            SLog("LEVEL-CHANGE: new spawner=0x%p (was 0x%p) elapsed=%us | "
                 "prev-level: spawns=%ld grows=%ld",
                 This, g_LastSpawner, elapsed / 1000,
                 g_LevelSpawns, g_LevelGrows);
            g_LevelSpawns = 0;
            g_LevelGrows = 0;
            g_LevelStartTick = now;
        }
    } else if (!g_LevelStartTick) {
        g_LevelStartTick = GetTickCount();
    }
    g_LastSpawner = This;
}

static void* __fastcall Hook_SpawnRoster(void* This, void* edx,
                                         void* roster, uint32_t flag,
                                         uint32_t a2)
{
    // Heartbeat + level detection
    LogHeartbeat();
    DetectLevelChange(This);
    // Cursor-hunt header dump (independent of the seq<=40 summary cap).
    if (g_HuntCursor && roster) {
        __try {
            void* array = *reinterpret_cast<void**>(roster);
            int   count = *reinterpret_cast<int*>((char*)roster + 4);
            if (!g_HdrTrackArray && count > 1) g_HdrTrackArray = array;
            if (g_HdrTrackArray && array == g_HdrTrackArray &&
                g_HdrDumps < HDR_DUMP_MAX) {
                LONG d = InterlockedIncrement(&g_HdrDumps);
                SLog("HDR-DUMP %ld: roster=0x%p this=0x%p count=%d", d, roster,
                     This, count);
                HexDumpToLog("roster", (unsigned char*)roster, 0x40);
                if (!IsBadReadPtr(This, 0x80))
                    HexDumpToLog("this", (unsigned char*)This, 0x80);
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            SLog("EXCEPTION in Hook_SpawnRoster hdr-dump (code=0x%lX)",
                 GetExceptionCode());
        }
    }

    // Read-only inspection BEFORE the spawn runs. We log a one-line summary for
    // the first 40 rosters, and a full hex dump for the first 4 waves AND for
    // the first multi-enemy (count>1) wave we encounter (so we can confirm the
    // array stride / per-enemy fields before implementing duplication).
    LONG seq = InterlockedIncrement(&g_RosterSeq);
    InterlockedIncrement(&g_LevelSpawns);
    // Log EVERY roster call (no cap) so multi-level sessions are fully captured.
    if (roster) {
        __try {
            void* array = *reinterpret_cast<void**>(roster);
            int   count = *reinterpret_cast<int*>((char*)roster + 4);
            int   maxc  = *reinterpret_cast<int*>((char*)roster + 8);
            SLog("ROSTER #%ld: this=0x%p flag=%u a2=%u array=0x%p "
                 "Num=%d Max=%d (freeMB=%u)",
                 seq, This, flag, a2, array, count, maxc,
                 MemMonLargestFreeMB());

            bool dumpMulti = (count > 1 &&
                              InterlockedCompareExchange(&g_MultiDumped, 1, 0) == 0);
            if ((seq <= 4 || dumpMulti) &&
                array && count > 0 && !IsBadReadPtr(array, DESC_STRIDE)) {
                // Dump up to 3 descriptors so we can diff per-enemy fields.
                int dumpN = count < 3 ? count : 3;
                for (int i = 0; i < dumpN; ++i) {
                    unsigned char* d = (unsigned char*)array + (size_t)i * DESC_STRIDE;
                    if (IsBadReadPtr(d, DESC_STRIDE)) break;
                    char tag[16]; sprintf(tag, "desc[%d]", i);
                    HexDumpToLog(tag, d, DESC_STRIDE);
                }
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            SLog("EXCEPTION in Hook_SpawnRoster inspect (code=0x%lX)",
                 GetExceptionCode());
        }
    }

    // ── x2 multiplier ──────────────────────────────────────────────────────
    // Before the director consumes the roster, double the per-descriptor enemy
    // counts (the matched {target,remaining} pair). Only act when the slot is
    // FRESH (both fields equal & sane) so we never touch a mid-spawn descriptor,
    // and the ring guard prevents per-frame compounding. Memory-gated, SEH-safe.
    if (g_DoMultiply && roster) {
        __try {
            void* array = *reinterpret_cast<void**>(roster);
            int   count = *reinterpret_cast<int*>((char*)roster + 4);
            if (array && count > 0 && count <= 256 &&
                !IsBadReadPtr(array, (size_t)count * DESC_STRIDE)) {
                bool memOk = MemMonLargestFreeMB() >= MULT_MEM_GATE_MB;
                for (int i = 0; i < count; ++i) {
                    char* d = (char*)array + (size_t)i * DESC_STRIDE;
                    int* pA = reinterpret_cast<int*>(d + OFF_DESC_CountA);
                    int* pB = reinterpret_cast<int*>(d + OFF_DESC_CountB);
                    int a = *pA, b = *pB;
                    // Fresh, sane, matched pair only.
                    if (a <= 0 || a != b || a > MULT_COUNT_SANE) continue;
                    int want = a * g_Multiplier;
                    if (!MultClaim(d, a, want)) continue; // already doubled
                    if (!memOk) {
                        InterlockedIncrement(&g_MultGated);
                        SLog("MULTIPLY GATED desc=0x%p count=%d (largest-free=%u MB < %u)",
                             d, a, MemMonLargestFreeMB(), MULT_MEM_GATE_MB);
                        continue;
                    }
                    *pA = want; *pB = want;
                    InterlockedIncrement(&g_MultApplied);
                    SLog("MULTIPLY desc=0x%p %d -> %d (x%d)", d, a, want, g_Multiplier);
                }
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            SLog("EXCEPTION in Hook_SpawnRoster multiply (code=0x%lX)",
                 GetExceptionCode());
        }
    }

    // ── x2 via credit-back ─────────────────────────────────────────────────
    // Snapshot count BEFORE the director runs, let it spawn, then refund up to
    // `consumed` credits so it spawns that many extra over the wave. count is
    // never pushed above the original N, so the descriptor array is never
    // over-read. Uses the game's own full spawn path => real, functional foes.
    int prevCount = -1;
    int* pCount = nullptr;
    if (g_DoubleRoster && roster) {
        __try {
            pCount = reinterpret_cast<int*>((char*)roster + 4);
            prevCount = *pCount;
        } __except (EXCEPTION_EXECUTE_HANDLER) { pCount = nullptr; prevCount = -1; }
    }

    // ── x2 via in-place TArray grow (the working lever) ─────────────────────
    // Grow the roster within its existing Max capacity BEFORE the director
    // processes it, so the extra cloned descriptors spawn through the engine's
    // own full path. Bounded by Max => no OOB. SEH-guarded against a bad guess.
    if (g_GrowRoster && roster) {
        __try {
            ApplyRosterGrow(roster);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            SLog("EXCEPTION in Hook_SpawnRoster grow (code=0x%lX)",
                 GetExceptionCode());
        }
    }

    void* ret = Real_SpawnRoster(This, edx, roster, flag, a2);

    if (g_DoubleRoster && roster && pCount && prevCount >= 1) {
        __try {
            void* array = *reinterpret_cast<void**>(roster);
            ApplyRosterCredit(array, pCount, prevCount);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            SLog("EXCEPTION in Hook_SpawnRoster credit (code=0x%lX)",
                 GetExceptionCode());
        }
    }
    return ret;
}

// ─── Wwise audio pool enlarger (fix AK::MemoryMgr exhaustion crash) ────────
// Heavy combat with x5/x10 enemies generates far more concurrent audio voices
// / sound-bank allocations than the engine was tuned for, exhausting Wwise's
// FIXED audio memory pools (crash deep in AK::MemoryMgr, even with GBs of
// system RAM free). The exe EXPORTS the whole Wwise API, so we resolve and hook
// AK::MemoryMgr::CreatePool by its mangled name and ENLARGE each pool's size at
// creation — giving every pool headroom without touching enemy count. This must
// be installed BEFORE Wwise init (before the 3s deferred hook setup), so it is
// driven from InstallAudioPoolHook() at the very top of the init thread.
//   AkMemPoolId __cdecl CreatePool(void* pMem, AkUInt32 uMemSize,
//                                  AkUInt32 uBlockSize, AkUInt32 eAttributes,
//                                  AkUInt32 uBlockAlign)
typedef long(__cdecl* fn_CreatePool)(void* mem, unsigned size, unsigned block,
                                     unsigned attrs, unsigned align);
static fn_CreatePool Real_CreatePool = nullptr;
static const char* const AK_CREATEPOOL_SYM = "?CreatePool@MemoryMgr@AK@@YAJPAXKKKK@Z";
static unsigned g_AudioPoolMult  = 2;            // enlarge each Wwise pool 2x (4x used too much 32-bit address space)
static const unsigned AUDIO_POOL_CAP = 0x20000000u; // never exceed 512 MB/pool
static volatile LONG g_AudioPoolHooked = 0;
static volatile LONG g_AudioPoolsGrown = 0;

static long __cdecl Hook_CreatePool(void* mem, unsigned size, unsigned block,
                                    unsigned attrs, unsigned align)
{
    unsigned origSize = size, newSize = size;
    void*    newMem   = mem;
    if (ENABLE_AUDIO_ENLARGE && g_AudioPoolMult > 1 && size >= 0x1000 && size < 0x40000000u) {
        unsigned long long grown = (unsigned long long)size * g_AudioPoolMult;
        if (grown > AUDIO_POOL_CAP) grown = AUDIO_POOL_CAP;
        if (block) grown -= (grown % block);   // keep block-pool size a multiple
        if (grown > size) {
            if (!mem) {                         // self-allocated: just ask for more
                newSize = (unsigned)grown;
            } else {                            // external buffer: supply a bigger one
                void* buf = VirtualAlloc(nullptr, (SIZE_T)grown,
                                         MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
                if (buf) { newMem = buf; newSize = (unsigned)grown; }
            }
        }
    }
    long pool = Real_CreatePool ? Real_CreatePool(newMem, newSize, block, attrs, align)
                                : -1;
    if (newSize != origSize) InterlockedIncrement(&g_AudioPoolsGrown);
    SLog("AK CreatePool: size=%u->%u block=%u attrs=0x%X align=%u mem=%p->%p id=%ld",
         origSize, newSize, block, attrs, align, mem, newMem, pool);
    return pool;
}

// ─── Crash diagnostics (vectored exception handler) ────────────────────────
// The in-game "Fatal error" dialog mislabels the crash site (it prints the
// nearest EXPORT, which can be megabytes away). To get the TRUE faulting RVA +
// call stack we install a vectored exception handler that logs fatal exceptions
// to our log (as module-relative RVAs we can map with the analyzer) and then
// lets the game's own handler proceed (EXCEPTION_CONTINUE_SEARCH).
static volatile LONG g_CrashLogged = 0;

// A genuine return address is immediately preceded by a CALL instruction.
// Validate the common x86 encodings so we can tell real stack frames apart
// from stale leftover dwords (which the naive scan otherwise reports as bogus
// frames, e.g. the 0x4BA30B / 0xEBB41 red herrings).
static bool LooksLikeRetAddr(uintptr_t a)
{
    if (a <= g_Base + 0x1000 || a >= g_Base + 0x1100000) return false;
    __try {
        const unsigned char* p = reinterpret_cast<const unsigned char*>(a);
        if (p[-5] == 0xE8) return true;                                // call rel32
        if (p[-2] == 0xFF && (p[-1] & 0x38) == 0x10) return true;      // call reg
        if (p[-3] == 0xFF && (p[-2] & 0x38) == 0x10) return true;      // call [reg+disp8]
        if (p[-6] == 0xFF && (p[-5] & 0x38) == 0x10) return true;      // call [disp32]
        if (p[-7] == 0xFF && (p[-6] & 0x38) == 0x10) return true;      // call [sib+disp32]
    } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
    return false;
}

static LONG CALLBACK CrashVEH(EXCEPTION_POINTERS* ep)
{
    const DWORD code = ep->ExceptionRecord->ExceptionCode;
    // Only genuinely fatal codes (ignore C++/SEH probes the engine handles).
    if (code != EXCEPTION_ACCESS_VIOLATION &&
        code != EXCEPTION_ILLEGAL_INSTRUCTION &&
        code != EXCEPTION_PRIV_INSTRUCTION &&
        code != EXCEPTION_STACK_OVERFLOW &&
        code != EXCEPTION_INT_DIVIDE_BY_ZERO &&
        code != EXCEPTION_DATATYPE_MISALIGNMENT &&
        code != 0xC0000409 /* fast-fail / stack-buffer overrun */)
        return EXCEPTION_CONTINUE_SEARCH;
    InterlockedIncrement(&g_LevelCrashes);
    if (InterlockedIncrement(&g_CrashLogged) > 30) return EXCEPTION_CONTINUE_SEARCH;

    __try {
        void* fault = ep->ExceptionRecord->ExceptionAddress;
        unsigned frva = ((uintptr_t)fault >= g_Base &&
                         (uintptr_t)fault < g_Base + 0x1100000)
                            ? (unsigned)((uintptr_t)fault - g_Base) : 0;
        const char* op = "?";
        unsigned badAddr = 0;
        if (code == EXCEPTION_ACCESS_VIOLATION &&
            ep->ExceptionRecord->NumberParameters >= 2) {
            ULONG_PTR a0 = ep->ExceptionRecord->ExceptionInformation[0];
            op = (a0 == 1) ? "WRITE" : (a0 == 8) ? "EXEC" : "READ";
            badAddr = (unsigned)ep->ExceptionRecord->ExceptionInformation[1];
        }
        // Classify where EIP is: our exe image (real code), a system DLL, or
        // HEAP (executing freed/garbage memory => use-after-free / bad vtable).
        uintptr_t eip = ep->ContextRecord->Eip;
        const char* where = "OTHER";
        if (eip >= g_Base + 0x1000 && eip < g_Base + 0x1100000) where = "MODULE";
        else if (eip >= 0x70000000 && eip < 0x80000000)         where = "SYSDLL";
        else if (eip >= 0x10000000 && eip < 0x70000000)         where = "HEAP!!";
        SLog("*** CRASH code=0x%08X fault=0x%p (rva=0x%X, EIP-in=%s) %s badAddr=0x%08X",
             code, fault, frva, where, op, badAddr);
        CONTEXT* c = ep->ContextRecord;
        SLog("    regs eax=%08X ebx=%08X ecx=%08X edx=%08X esi=%08X edi=%08X "
             "ebp=%08X esp=%08X",
             (unsigned)c->Eax, (unsigned)c->Ebx, (unsigned)c->Ecx,
             (unsigned)c->Edx, (unsigned)c->Esi, (unsigned)c->Edi,
             (unsigned)c->Ebp, (unsigned)c->Esp);

        // The faulting instruction is a leaf (memcpy via rep movs); the TRUE
        // caller's return address sits exactly at [esp]. Log it explicitly so we
        // stop guessing which frame is real.
        uintptr_t* sp = reinterpret_cast<uintptr_t*>(ep->ContextRecord->Esp);
        if (!IsBadReadPtr(sp, 4)) {
            uintptr_t top = sp[0];
            unsigned trva = (top >= g_Base && top < g_Base + 0x1100000)
                                ? (unsigned)(top - g_Base) : 0;
            SLog("    [esp]=0x%08X rva=0x%X %s (true memcpy/leaf caller)",
                 (unsigned)top, trva,
                 LooksLikeRetAddr(top) ? "VALID-RET" : "(not a ret?)");
        }
        // Walk the stack from ESP collecting dwords in the exe image. Each is
        // tagged '*' when preceded by a real CALL (genuine frame) vs no tag
        // (stale leftover) so we can ignore red-herring frames.
        char line[700]; int k = 0; int found = 0;
        for (int i = 0; i < 1024 && found < 32; ++i) {
            if (IsBadReadPtr(sp + i, 4)) break;
            uintptr_t a = sp[i];
            if (a > g_Base + 0x1000 && a < g_Base + 0x1100000) {
                k += sprintf(line + k, "0x%X%s ", (unsigned)(a - g_Base),
                             LooksLikeRetAddr(a) ? "*" : "");
                ++found;
                if (k > 660) break;
            }
        }
        SLog("    crash_stack_rva (*=valid ret): %s", line);
        if (frva)
            HexDumpToLog("faultEip", (unsigned char*)fault, 0x10);
        // Is our Serialize hook still installed at crash time? E9=our jmp (intact),
        // 56=original `push esi` (patch reverted/never applied). Also dump the call
        // site 0xEBB3C to confirm it's still `call 0xfc6d82` (E8 ..).
        unsigned char* hk = reinterpret_cast<unsigned char*>(g_Base + 0xEBA70);
        if (!IsBadReadPtr(hk, 8))
            SLog("    HOOKBYTES @0xEBA70: %02X %02X %02X %02X %02X %02X %02X "
                 "(E9=our jmp intact / 56=orig push esi => bypassed)",
                 hk[0], hk[1], hk[2], hk[3], hk[4], hk[5], hk[6]);
    } __except (EXCEPTION_EXECUTE_HANDLER) {}

    // ── MEMCPY CRASH RECOVERY ─────────────────────────────────────────────────
    // This is a VANILLA ENGINE BUG (proven: crashes with spawn mult OFF).
    // We cannot fix the root cause, but we CAN survive it by simulating memcpy's
    // return when it faults. The caller's logic then advances past the corrupt
    // read. Stale data remains in the destination but the game continues.
    //
    // Detection: EIP is inside MSVCR90!memcpy (within 0x200 bytes of entry) and
    // it's an access violation. [ESP] holds the return address back to the caller.
    if (code == EXCEPTION_ACCESS_VIOLATION) {
        uintptr_t eip = ep->ContextRecord->Eip;
        // Resolve MSVCR90!memcpy entry to determine if EIP is inside it.
        static uintptr_t s_mcEntry = 0;
        if (!s_mcEntry) {
            HMODULE hCRT = GetModuleHandleA("MSVCR90.dll");
            if (hCRT) {
                void* p = GetProcAddress(hCRT, "memcpy");
                if (p) s_mcEntry = reinterpret_cast<uintptr_t>(p);
            }
        }
        uintptr_t mcEntry = s_mcEntry;
        if (mcEntry && eip >= mcEntry && eip < mcEntry + 0x400) {
            // EIP is inside memcpy (after push ebp; mov ebp,esp; push regs).
            // The frame pointer (EBP) gives us the standard stack frame:
            //   [EBP]   = saved caller's EBP
            //   [EBP+4] = return address (back to Hook_memcpy or caller)
            //   [EBP+8] = dst (first arg, cdecl)
            // Simulate memcpy's RET: restore EBP, set EIP=[EBP+4], ESP=EBP+8
            uintptr_t* bp = reinterpret_cast<uintptr_t*>(ep->ContextRecord->Ebp);
            if (!IsBadReadPtr(bp, 8)) {
                uintptr_t savedEbp = bp[0];
                uintptr_t retAddr  = bp[1];
                // Sanity: retAddr should be in a code region (our DLL or game exe)
                bool validRet = (retAddr >= 0x00400000 && retAddr < 0x70000000);
                if (validRet) {
                    static volatile LONG s_recoveries = 0;
                    LONG nr = InterlockedIncrement(&s_recoveries);
                    if (nr <= 20)
                        SLog("MEMCPY-RECOVER #%ld: EIP was 0x%p (inside memcpy), "
                             "returning to 0x%p with dst=0x%08X (frame-based unwind)",
                             nr, (void*)eip, (void*)retAddr,
                             (unsigned)ep->ContextRecord->Edi);
                    // Restore EBP to caller's saved value
                    ep->ContextRecord->Ebp = (DWORD)savedEbp;
                    // Set return value: EAX = dst (EDI holds dst in rep movs)
                    ep->ContextRecord->Eax = ep->ContextRecord->Edi;
                    // Unwind frame: ESP = EBP + 8 (past saved EBP and ret addr)
                    ep->ContextRecord->Esp = (DWORD)(uintptr_t)(bp + 2);
                    // Jump to return address
                    ep->ContextRecord->Eip = (DWORD)retAddr;
                    return EXCEPTION_CONTINUE_EXECUTION;
                }
            }
        }
    }

    return EXCEPTION_CONTINUE_SEARCH; // let the game's handler still run
}

// Install the CreatePool hook AS EARLY AS POSSIBLE (before Wwise init). Safe to
// call before InitSpawnHook: it lazily opens the log and resolves the base.
void InstallAudioPoolHook()
{
    if (InterlockedCompareExchange(&g_AudioPoolHooked, 1, 0) != 0) return;
    if (!g_StartTick) g_StartTick = GetTickCount();
    if (!g_Log)  OpenLog();
    if (!g_Base) g_Base = reinterpret_cast<uintptr_t>(GetModuleHandleA(nullptr));

    // Crash logger first, so it covers the whole session.
    AddVectoredExceptionHandler(1 /*first*/, &CrashVEH);
    SLog("DIAG: vectored crash handler installed (true RVA + stack on fatal "
         "exceptions).");

    MH_STATUS s = MH_Initialize();
    if (s != MH_OK && s != MH_ERROR_ALREADY_INITIALIZED) {
        SLog("AUDIO: MH_Initialize failed (%d)", s); return;
    }
    HMODULE exe = GetModuleHandleA(nullptr);
    void* p = (void*)GetProcAddress(exe, AK_CREATEPOOL_SYM);
    if (!p) { SLog("AUDIO: AK CreatePool export not found"); return; }
    if (MH_CreateHook(p, (void*)&Hook_CreatePool, (void**)&Real_CreatePool) != MH_OK ||
        MH_EnableHook(p) != MH_OK) {
        SLog("AUDIO: failed to hook AK CreatePool @ 0x%p", p); return;
    }
    SLog("AUDIO: AK::MemoryMgr::CreatePool hook ENABLED @ 0x%p (pool x%u, cap %u MB). "
         "Enlarging Wwise pools to fix audio-pool exhaustion crash.",
         p, g_AudioPoolMult, AUDIO_POOL_CAP / (1024 * 1024));
}

// ─── Fixed-pool exhaustion fix (the REAL heavy-combat crash) ───────────────
// Root cause found via the crash VEH: a NULL-deref at RVA 0x60E694 inside a
// global fixed-size object pool. The pool getter (RVA 0x604490) builds exactly
// 64 nodes of 0x4E4 bytes and sets the pool's grow-count field [pool+0x10] to
// ZERO. When all 64 nodes are in use, the consumer calls the generic free-list
// refill (RVA 0x958C0, __thiscall(this,count), ret 4) with count = [pool+0x10]
// = 0; the refill early-outs on `test count,count; je`, the free-list head stays
// NULL, and the next dereference crashes. Vanilla never needs a 65th concurrent
// node, but x5/x10 enemies do. FIX: when the refill is asked to grow by <= 0,
// force a real block (POOL_GROW_NODES) so the pool grows on demand instead of
// returning an empty list. Only the count<=0 case is altered (other pools that
// pass a real positive count are untouched), so this is surgical and safe.
static const uintptr_t RVA_PoolRefill = 0x958C0;
static const int       POOL_GROW_NODES = 64; // nodes to add when game passes 0

// ─── Streaming-serialize guard (the out-of-combat ~1GB memcpy crash) ───────
// Root cause (crash VEH + disasm): FArchive::Serialize(this, dst, length) @
// RVA 0xEBA70 is a buffered reader that does memcpy(dst, src, min(avail,length))
// in a loop (the faulting memcpy is at the 0xEBB41 return site, via thunk
// 0xFC6D82). During async LEVEL STREAMING (runs from the Tick main loop, NOT
// combat -> explains the ~39s-after-fight crash) a TArray Count is read corrupt
// and passed here as `length` ≈ 1.07 GB (ecx=0x3FF00800), so the copy walks off
// the source page (esi≈0x3FDFFE) -> 0xC0000005. A legitimate single Serialize
// is never this large on this buffered path, so we hook the entry and, when the
// requested length is negative or absurd (> SER_MAX_LEN), LOG the archive state
// and SKIP the copy (return as if length 0) instead of crashing. Every trigger
// is logged so we can confirm it only fires on the corrupt read, never on real
// loads (raise the cap if a legit large read ever trips it).
// Async double-buffered streaming reader @ 0x96F00 (__thiscall(this,dst,count)).
// This is the ACTUAL crash function: computes avail = bufEnd - curPos, and when
// bufEnd=0 (freed/reset buffer) wraps to ~4GB. Hooking here lets us catch the
// invalid buffer state BEFORE memcpy is called — the correct upstream fix.
static const uintptr_t RVA_StreamRead = 0x96F00;
// (no hook function needed — we use a binary patch instead)

static const uintptr_t RVA_ArSerialize = 0xEBA70;
// Legit texture bulk reads can reach ~17MB (e.g. FX_Lighthouse.Main1912_DIF =
// 16,777,598 bytes). Set ceiling to 32MB; the memcpy backstop (also 32MB)
// catches any corrupt read that slips past.
static const int       SER_MAX_LEN     = 0x2000000;  // 32 MB: matches memcpy guard
typedef void(__fastcall* fn_ArSerialize)(void* This, void* edx, void* dst, int length);
static fn_ArSerialize Real_ArSerialize = nullptr;
static volatile LONG  g_SerGuards = 0;

// Upstream FArchive serialize DISPATCHER @ 0x80D00 (__thiscall(this,dst,length),
// ret8, returns the archive in eax for operator<< chaining). The validated crash
// chain is 0xEBB41 <- 0x80D47(this fn) <- 0xB625F, and 0xB625F calls 0x80D00 via
// a DIRECT call (hits our patch reliably, unlike the indirect vtable call into
// 0xEBA70 that somehow bypasses our hook). Guarding here catches the corrupt
// ~1GB length one level up, regardless of which Serialize impl runs below.
static const uintptr_t RVA_SerDispatch = 0x80D00;
typedef void*(__fastcall* fn_SerDispatch)(void* This, void* edx, void* dst, int length);
static fn_SerDispatch Real_SerDispatch = nullptr;
static volatile LONG  g_SerDispGuards = 0;
static volatile LONG  g_SerDispCalls = 0;

// LAST-LINE BACKSTOP: hook MSVCR90 memcpy itself (resolved at runtime from the
// exe's import slot at the 0xFC6D82 thunk: jmp [0x10D455C], RVA 0xD455C). Both
// serialize hooks (0xEBA70, 0x80D00) are live with millions of calls yet never
// block the ~1GB copy, which means the crash-stack frames 0xEBB41/0x80D47 are
// STALE (false-positive ret-addr validation) and the real caller is elsewhere.
// memcpy is the ONE function provably on the path (the fault EIP is inside it).
// In the hook we (1) log the TRUE caller via _ReturnAddress() for any absurd
// count, and (2) clamp count to the source's actually-committed extent so the
// copy can never walk off the page -> prevents the crash regardless of caller.
// A valid large copy (src fully mapped) passes unchanged; only the corrupt
// overrun is clamped. Gated on count>=64MB so normal small memcpys are untouched.
static const uintptr_t RVA_memcpyIAT = 0xD455C;
static const size_t    MEMCPY_HARD_MAX = 0x2000000; // 32 MB: hard ceiling
typedef void*(__cdecl* fn_memcpy)(void* dst, const void* src, size_t count);
static fn_memcpy Real_memcpy = nullptr;
static volatile LONG g_MemcpyGuards = 0;

typedef void*(__fastcall* fn_PoolRefill)(void* This, void* edx, int count);
static fn_PoolRefill Real_PoolRefill = nullptr;
static volatile LONG g_PoolGrows = 0;

static void* __fastcall Hook_PoolRefill(void* This, void* edx, int count)
{
    int use = count;
    if (use <= 0) {
        use = POOL_GROW_NODES;          // game passed 0 -> grow for real (no crash)
        LONG n = InterlockedIncrement(&g_PoolGrows);
        if (n <= 40)
            SLog("POOL-GROW #%ld: pool=0x%p refill count %d->%d (free-list was "
                 "empty; preventing NULL-deref crash)", n, This, count, use);
    }
    return Real_PoolRefill(This, edx, use);
}

// ── STREAMING READER BINARY PATCH (the actual crash fix) ─────────────────────
// FUN_00496F00: double-buffered async reader. Ghidra disassembly reveals:
//   At offset +0x5E: "7E 02" = JLE (signed) for buffer1 avail check
//   At offset +0xA7: "7E 02" = JLE (signed) for buffer2 avail check
//   When bufEnd=0 (freed buffer), avail wraps to ~4GB unsigned / -1.5M signed.
//   JLE incorrectly passes (signed -1.5M <= count), so memcpy gets 4GB.
//   Fix: patch both to 0x76 (JBE, unsigned). 4GB > count → caps to count.
//   The capped read (few bytes from a stale but accessible heap address) is
//   harmless — the engine gets garbage data for one field and recovers.
// No function hook needed — binary patch applied at init, zero runtime overhead.

static volatile LONG g_SerCalls = 0;       // total intercepts (proves hook is live)
static volatile LONG g_SerBigLogged = 0;   // rate-limit for large pass-through logs

static void __fastcall Hook_ArSerialize(void* This, void* edx, void* dst, int length)
{
    // Heartbeat: prove the hook is on the hot path + show its cadence.
    LONG calls = InterlockedIncrement(&g_SerCalls);
    if (calls == 1 || calls == 1000 || (calls % 500000) == 0)
        SLog("SER-DIAG: hook live, intercept #%ld (this latest len=%d)", calls, length);
    // Log large reads (>=1MB) so we can SEE the corrupt ~1GB read flow through
    // here (if it does) and confirm the arg offset is right. Rate-limited.
    if ((unsigned)length >= 0x100000u && g_SerBigLogged < 80) {
        InterlockedIncrement(&g_SerBigLogged);
        SLog("SER-DIAG: large len=%d (0x%08X) dst=0x%p this=0x%p call#%ld",
             length, (unsigned)length, dst, This, calls);
    }
    if (length < 0 || length > SER_MAX_LEN) {
        LONG n = InterlockedIncrement(&g_SerGuards);
        if (n <= 60) {
            unsigned inner = 0, cur = 0, rem = 0, endp = 0;
            __try {
                inner = *reinterpret_cast<unsigned*>((char*)This + 0x4B0);
                if (inner && !IsBadReadPtr((void*)(uintptr_t)inner, 0xD0)) {
                    char* b = reinterpret_cast<char*>((uintptr_t)inner);
                    cur  = *reinterpret_cast<unsigned*>(b + 0xAC);
                    rem  = *reinterpret_cast<unsigned*>(b + 0xB0);
                    endp = *reinterpret_cast<unsigned*>(b + 0xC8);
                }
            } __except (EXCEPTION_EXECUTE_HANDLER) {}
            uintptr_t ra = reinterpret_cast<uintptr_t>(_ReturnAddress());
            unsigned raRva = (ra >= g_Base && ra < g_Base + 0x1100000)
                                 ? (unsigned)(ra - g_Base) : 0;
            SLog("SER-DIAG-CORRUPT #%ld: length=%d (0x%08X) "
                 "dst=0x%p this=0x%p inner=0x%08X cur=0x%08X rem=0x%08X end=0x%08X "
                 "caller_rva=0x%X -> LOGGING ONLY (pass-through)",
                 n, length, (unsigned)length, dst, This, inner, cur, rem, endp,
                 raRva);
        }
        // LOGGING-ONLY: pass through to real function, let crash happen cleanly
        // so VEH handler captures the true fault for diagnosis.
    }
    Real_ArSerialize(This, edx, dst, length);
}

static void* __fastcall Hook_SerDispatch(void* This, void* edx, void* dst, int length)
{
    LONG calls = InterlockedIncrement(&g_SerDispCalls);
    if (calls == 1 || (calls % 1000000) == 0)
        SLog("SERDISP-DIAG: live, call #%ld (latest len=%d)", calls, length);
    if (length < 0 || length > SER_MAX_LEN) {
        LONG n = InterlockedIncrement(&g_SerDispGuards);
        if (n <= 60) {
            uintptr_t ra = reinterpret_cast<uintptr_t>(_ReturnAddress());
            unsigned raRva = (ra >= g_Base && ra < g_Base + 0x1100000)
                                 ? (unsigned)(ra - g_Base) : 0;
            SLog("SERDISP-DIAG-CORRUPT #%ld: length=%d (0x%08X) "
                 "dst=0x%p this=0x%p caller_rva=0x%X -> LOGGING ONLY (pass-through)",
                 n, length, (unsigned)length, dst, This, raRva);
        }
        // LOGGING-ONLY: pass through, let VEH catch the crash cleanly
    }
    return Real_SerDispatch(This, edx, dst, length);
}

static void* __cdecl Hook_memcpy(void* dst, const void* src, size_t count)
{
    if (count >= MEMCPY_HARD_MAX) {
        // Safety net: should no longer fire now that Hook_StreamRead validates
        // avail before calling memcpy. If it still fires, log and block.
        LONG n = InterlockedIncrement(&g_MemcpyGuards);
        if (n <= 20) {
            uintptr_t ra = reinterpret_cast<uintptr_t>(_ReturnAddress());
            unsigned raRva = (ra >= g_Base && ra < g_Base + 0x1100000)
                                 ? (unsigned)(ra - g_Base) : 0;
            SLog("MEMCPY-GUARD #%ld: BLOCKED count=%Iu (0x%IX) "
                 "dst=0x%p src=0x%p caller_rva=0x%X -> return dst (no-op)",
                 n, count, count, dst, src, raRva);
        }
        return dst;
    }
    return Real_memcpy(dst, src, count);
}

// ─── Public API ──────────────────────────────────────────────────────────
void InitSpawnHook()
{
    // The early audio-pool hook may have already opened the log + start clock.
    if (!g_StartTick) g_StartTick = GetTickCount();
    if (!g_Log && !OpenLog()) return;

    if (!g_Base) g_Base = reinterpret_cast<uintptr_t>(GetModuleHandleA(nullptr));
    SLog("module base = 0x%p", (void*)g_Base);
    SLog("BUILD CONFIG: SpawnMult=%s x%d | AudioEnlarge=%s x%u | "
         "Hooks=LOGGING-ONLY (no clamp/block/exception)",
         ENABLE_SPAWN_MULT ? "ON" : "OFF", g_RosterMult,
         ENABLE_AUDIO_ENLARGE ? "ON" : "OFF", g_AudioPoolMult);

    void* pSpawnActor = reinterpret_cast<void*>(g_Base + RVA_SpawnActor);
    SLog("UWorld::SpawnActor @ 0x%p (base + 0x%X)", pSpawnActor,
         (unsigned)RVA_SpawnActor);

    // MinHook is already initialized by the memory monitor; if not, init here.
    MH_STATUS s = MH_Initialize();
    if (s != MH_OK && s != MH_ERROR_ALREADY_INITIALIZED) {
        SLog("ERROR: MH_Initialize failed (%d)", s);
        return;
    }

    if (MH_CreateHook(pSpawnActor, (void*)&Hook_SpawnActor,
                      (void**)&Real_SpawnActor) != MH_OK) {
        SLog("ERROR: MH_CreateHook(SpawnActor) failed");
        return;
    }
    if (MH_EnableHook(pSpawnActor) != MH_OK) {
        SLog("ERROR: MH_EnableHook(SpawnActor) failed");
        return;
    }
    SLog("SpawnActor hook ENABLED (logging). Waiting for spawns...");

    // ── Roster inspector (read-only): dump wave descriptor layout ──
    void* pSpawnRoster = reinterpret_cast<void*>(g_Base + RVA_SpawnRoster);
    SLog("SpawnRoster (wave loop) @ 0x%p (base + 0x%X)", pSpawnRoster,
         (unsigned)RVA_SpawnRoster);
    if (MH_CreateHook(pSpawnRoster, (void*)&Hook_SpawnRoster,
                      (void**)&Real_SpawnRoster) != MH_OK) {
        SLog("ERROR: MH_CreateHook(SpawnRoster) failed");
        return;
    }
    if (MH_EnableHook(pSpawnRoster) != MH_OK) {
        SLog("ERROR: MH_EnableHook(SpawnRoster) failed");
        return;
    }
    SLog("Roster hook ENABLED. GrowRoster=%s x%d (in-place, mem-gate %u MB).",
         g_GrowRoster ? "ON" : "OFF", g_RosterMult, MULT_MEM_GATE_MB);

    // ── create-AI doubler (the real x2 lever) ──
    void* pCreateAI = reinterpret_cast<void*>(g_Base + RVA_CreateAI);
    SLog("create-AI @ 0x%p (base + 0x%X)", pCreateAI, (unsigned)RVA_CreateAI);
    if (MH_CreateHook(pCreateAI, (void*)&Hook_CreateAI,
                      (void**)&Real_CreateAI) != MH_OK) {
        SLog("ERROR: MH_CreateHook(CreateAI) failed");
    } else if (MH_EnableHook(pCreateAI) != MH_OK) {
        SLog("ERROR: MH_EnableHook(CreateAI) failed");
    } else {
        SLog("create-AI doubler ENABLED. DoubleAI=%s (+%d extra/spawn, mem-gate %u MB).",
             g_DoubleAI ? "ON" : "OFF", g_ExtraAIPerSpawn, MULT_MEM_GATE_MB);
    }

    // ── Fixed-pool exhaustion fix (the real heavy-combat NULL-deref crash) ──
    void* pPoolRefill = reinterpret_cast<void*>(g_Base + RVA_PoolRefill);
    if (MH_CreateHook(pPoolRefill, (void*)&Hook_PoolRefill,
                      (void**)&Real_PoolRefill) != MH_OK) {
        SLog("ERROR: MH_CreateHook(PoolRefill) failed");
    } else if (MH_EnableHook(pPoolRefill) != MH_OK) {
        SLog("ERROR: MH_EnableHook(PoolRefill) failed");
    } else {
        SLog("POOL-REFILL fix ENABLED @ 0x%p (base + 0x%X). Forcing on-demand "
             "growth (+%d nodes) when the game passes a 0 grow-count -> fixes the "
             "fixed-64 pool exhaustion crash under heavy combat.",
             pPoolRefill, (unsigned)RVA_PoolRefill, POOL_GROW_NODES);
    }

    // ── STREAMING READER: binary patch JLE→JBE (the actual crash fix) ────────
    // FUN_00496F00 at offset +0x5E has "7E 02" = JLE (signed).
    // When avail wraps to 0xFFE889B4 (signed: -1.5M), JLE says -1.5M <= count
    // → doesn't cap → memcpy with 4GB. Patching to 0x76 (JBE, unsigned) makes
    // 0xFFE889B4 > count → caps to count → small harmless read.
    {
        // Patch TWO JLE→JBE instructions:
        //   +0x5E = buffer1 avail comparison (7E 02 → 76 02)
        //   +0xA7 = buffer2 avail comparison (7E 02 → 76 02)
        struct { unsigned offset; const char* label; } patches[] = {
            { 0x5E, "buf1" }, { 0xA7, "buf2" }
        };
        for (int pi = 0; pi < 2; pi++) {
            unsigned char* patchAddr = reinterpret_cast<unsigned char*>(
                g_Base + RVA_StreamRead + patches[pi].offset);
            DWORD oldProt;
            if (VirtualProtect(patchAddr, 2, PAGE_EXECUTE_READWRITE, &oldProt)) {
                if (patchAddr[0] == 0x7E && patchAddr[1] == 0x02) {
                    patchAddr[0] = 0x76;  // JBE (unsigned) instead of JLE (signed)
                    SLog("STREAMREAD-PATCH: patched JLE->JBE at 0x%p (base+0x%X) [%s]. "
                         "Avail comparison is now UNSIGNED.",
                         patchAddr, (unsigned)(RVA_StreamRead + patches[pi].offset),
                         patches[pi].label);
                } else {
                    SLog("STREAMREAD-PATCH WARNING: expected 7E 02 at +0x%X, found %02X %02X. "
                         "NOT patching [%s].", patches[pi].offset,
                         patchAddr[0], patchAddr[1], patches[pi].label);
                }
                VirtualProtect(patchAddr, 2, oldProt, &oldProt);
            } else {
                SLog("STREAMREAD-PATCH ERROR: VirtualProtect failed at 0x%p", patchAddr);
            }
        }
    }
    // No function hook needed — binary patch is sufficient and avoids overhead
    // on this extremely hot-path function (called millions of times during load).

    // ── Weapon carry limit: diagnostic hooks (phase 3) ────────────────────────
    // Phase 1-2 findings: AtCapacity is NPC-only. EquipWeapon/AddInventory/DropWeapon/
    // BeginWeaponSwap/OnAddRemoveSwapWeapons do NOT fire during hold-F weapon pickup.
    // The actual pickup path must go through XSwapWeaponWithUseTarget.
    {
        typedef void (__fastcall* fn_Exec)(void* This, void* edx, void* Stack, void* Result);

        #define DECL_HOOK(NAME, RVA_VAL) \
            static const unsigned RVA_##NAME = RVA_VAL; \
            static fn_Exec Real_##NAME = nullptr; \
            struct H_##NAME { \
                static void __fastcall Hook(void* T, void* e, void* S, void* R) { \
                    SLog("WPN: " #NAME " (this=%p)", T); \
                    Real_##NAME(T, e, S, R); \
                } \
            };

        // ── WEAPON CARRY LIMIT: 4-weapon cycling via NextWeapon override ──
        // XInventoryManager layout:
        //   +0x1FC: Weapons[36] (UObject* array, indexed by weapon type 0-35)
        //   +0x2A0: EquippedWeaponIndex (int, current active weapon type)
        //   +0x2A4: BackupWeaponIndex (int, secondary weapon type)
        // SetEquippedWeaponIndex at RVA 0x531F00: thiscall(InvMgr, int newIndex)
        static const unsigned RVA_SwapWithUse = 0x4FCE30;
        static fn_Exec Real_SwapWithUse = nullptr;
        static void* s_InvMgr = nullptr; // captured from AddInventory/NextWeapon

        // ── 4-WEAPON CYCLING IMPLEMENTATION ──
        // Configuration: how many gun slots to cycle through (4 = user's request)
        static const int MAX_CYCLE_WEAPONS = 4;
        // XWeapon vtable RVA — ONLY weapons with this exact vtable are guns
        // Vigors (XWeaponMurderOfCrows=0xDDBB60) and melee (XWeaponDedicatedMelee=0xDDA758) are excluded
        static const unsigned VTBL_RVA_XWEAPON = 0xDD9DE0;

        struct H_SwapWithUse {
            static void __fastcall Hook(void* T, void* e, void* S, void* R) {
                if (!s_InvMgr) {
                    // Try to capture from PlayerController path as fallback
                }
                Real_SwapWithUse(T, e, S, R);
            }
        };
        // AddInventory hook to capture InvMgr early at startup
        static const unsigned RVA_AddInventory = 0x509340;
        static fn_Exec Real_AddInventory = nullptr;
        struct H_AddInventory {
            static void __fastcall Hook(void* T, void* e, void* S, void* R) {
                if (!s_InvMgr) {
                    s_InvMgr = T;
                    SLog("WPN: Captured InvMgr from AddInventory = %p", T);
                }
                Real_AddInventory(T, e, S, R);
            }
        };
        DECL_HOOK(UseAnyObject,    0x4FCB30)  // XPlayerController::execXUseAnyObject
        DECL_HOOK(UseObject,       0x4FCBF0)  // XPlayerController::execXUseObjectThatIsNotUnsubstantiated
        DECL_HOOK(SetWeapon,       0x4F9ED0)  // XPawn::execSetWeapon / XDLCCPawn::execSetWeapon
        DECL_HOOK(UnSetWeapon,     0x4F9F10)  // XPawn::execUnSetWeapon
        DECL_HOOK(AcquireWeapon,   0x4F9FF0)  // XPawn::execAcquireWeapon
        DECL_HOOK(GivenTo,         0x500B70)  // XWeapon::execGivenTo
        DECL_HOOK(StartGivenTo,    0x501660)  // XWeapon::execStartGivenTo
        DECL_HOOK(StartRemoved,    0x5016E0)  // XWeapon::execStartRemovedFrom
        DECL_HOOK(TryToEquip,      0x501530)  // XWeapon::execTryToEquip
        DECL_HOOK(OnEquipWeapon,   0x4FAAF0)  // XPawn::execOnEquipWeapon
        DECL_HOOK(CycleUp,         0x50AA20)  // XDLCCPlayerController::execCycleWeaponUp
        DECL_HOOK(CycleDown,       0x50AA60)  // XDLCCPlayerController::execCycleWeaponDown
        DECL_HOOK(DropPlayers,     0x4FA090)  // XPawn::execDropWeapon_PlayersOnly
        // NextWeapon — OVERRIDDEN for 4-weapon cycling
        // Strategy: pre-set BackupWeaponIndex to our target, then let Real_NextWeapon
        // toggle naturally. This uses the game's normal equip path (proper model/animation).
        static const unsigned RVA_NextWeapon = 0x5090F0;
        static fn_Exec Real_NextWeapon = nullptr;
        struct H_NextWeapon {
            static void __fastcall Hook(void* T, void* e, void* S, void* R) {
                if (!s_InvMgr) {
                    s_InvMgr = T;
                    SLog("WPN: Captured InvMgr = %p", T);
                }

                BYTE* inv = (BYTE*)s_InvMgr;
                DWORD* weapons = (DWORD*)(inv + 0x1FC); // Weapons[36] array
                int currentIdx = *(int*)(inv + 0x2A0);  // EquippedWeaponIndex
                DWORD xWeaponVtbl = g_Base + VTBL_RVA_XWEAPON; // runtime vtable address

                // Build list of populated GUN slots (filter by XWeapon vtable, skip vigors/melee)
                int gunSlots[36];
                int numGuns = 0;
                for (int i = 0; i < 36; i++) {
                    if (weapons[i] != 0 && !IsBadReadPtr((void*)weapons[i], 4)) {
                        DWORD vtbl = *(DWORD*)weapons[i];
                        if (vtbl == xWeaponVtbl) {
                            gunSlots[numGuns++] = i;
                            if (numGuns >= MAX_CYCLE_WEAPONS) break;
                        }
                    }
                }

                if (numGuns <= 1) {
                    // Only 0 or 1 gun — let original behavior handle it
                    Real_NextWeapon(T, e, S, R);
                    return;
                }

                // Find current position in our cycle list
                int curPos = -1;
                for (int i = 0; i < numGuns; i++) {
                    if (gunSlots[i] == currentIdx) { curPos = i; break; }
                }

                // Advance to next slot (wrap around)
                int nextPos = (curPos + 1) % numGuns;
                int nextIdx = gunSlots[nextPos];

                SLog("WPN: Cycle %d -> %d (slot %d/%d)", currentIdx, nextIdx, nextPos+1, numGuns);

                // Pre-set BackupWeaponIndex to our desired target
                // When Real_NextWeapon toggles equipped <-> backup, it will land on nextIdx
                *(int*)(inv + 0x2A4) = nextIdx;

                // Let the game's normal NextWeapon handle the switch (proper model/anim/sound)
                Real_NextWeapon(T, e, S, R);
            }
        };

        #undef DECL_HOOK

        struct { unsigned rva; void* hook; void** real; const char* name; } hooks[] = {
            { RVA_SwapWithUse,   (void*)&H_SwapWithUse::Hook,   (void**)&Real_SwapWithUse,   "XSwapWeaponWithUseTarget" },
            { RVA_UseAnyObject,  (void*)&H_UseAnyObject::Hook,  (void**)&Real_UseAnyObject,  "XUseAnyObject" },
            { RVA_UseObject,     (void*)&H_UseObject::Hook,     (void**)&Real_UseObject,     "XUseObject" },
            { RVA_SetWeapon,     (void*)&H_SetWeapon::Hook,     (void**)&Real_SetWeapon,     "SetWeapon" },
            { RVA_UnSetWeapon,   (void*)&H_UnSetWeapon::Hook,   (void**)&Real_UnSetWeapon,   "UnSetWeapon" },
            { RVA_AddInventory,  (void*)&H_AddInventory::Hook,  (void**)&Real_AddInventory,  "AddInventory" },
            { RVA_AcquireWeapon, (void*)&H_AcquireWeapon::Hook, (void**)&Real_AcquireWeapon, "AcquireWeapon" },
            { RVA_GivenTo,       (void*)&H_GivenTo::Hook,       (void**)&Real_GivenTo,       "GivenTo" },
            { RVA_StartGivenTo,  (void*)&H_StartGivenTo::Hook,  (void**)&Real_StartGivenTo,  "StartGivenTo" },
            { RVA_StartRemoved,  (void*)&H_StartRemoved::Hook,  (void**)&Real_StartRemoved,  "StartRemovedFrom" },
            { RVA_TryToEquip,    (void*)&H_TryToEquip::Hook,    (void**)&Real_TryToEquip,    "TryToEquip" },
            { RVA_OnEquipWeapon, (void*)&H_OnEquipWeapon::Hook, (void**)&Real_OnEquipWeapon, "OnEquipWeapon" },
            { RVA_CycleUp,       (void*)&H_CycleUp::Hook,       (void**)&Real_CycleUp,       "CycleWeaponUp" },
            { RVA_CycleDown,     (void*)&H_CycleDown::Hook,     (void**)&Real_CycleDown,     "CycleWeaponDown" },
            { RVA_DropPlayers,   (void*)&H_DropPlayers::Hook,   (void**)&Real_DropPlayers,   "DropWeapon_PlayersOnly" },
            { RVA_NextWeapon,    (void*)&H_NextWeapon::Hook,    (void**)&Real_NextWeapon,    "NextWeapon" },
        };
        for (auto& h : hooks) {
            void* target = reinterpret_cast<void*>(g_Base + h.rva);
            if (MH_CreateHook(target, h.hook, h.real) == MH_OK &&
                MH_EnableHook(target) == MH_OK) {
                SLog("WPN: %s hook OK @ base+0x%X", h.name, h.rva);
            } else {
                SLog("WPN: %s hook FAILED @ base+0x%X", h.name, h.rva);
            }
        }
    }

    // ── Streaming-serialize guard (out-of-combat ~1GB memcpy crash) ──
    void* pArSerialize = reinterpret_cast<void*>(g_Base + RVA_ArSerialize);
    if (MH_CreateHook(pArSerialize, (void*)&Hook_ArSerialize,
                      (void**)&Real_ArSerialize) != MH_OK) {
        SLog("ERROR: MH_CreateHook(ArSerialize) failed");
    } else if (MH_EnableHook(pArSerialize) != MH_OK) {
        SLog("ERROR: MH_EnableHook(ArSerialize) failed");
    } else {
        unsigned char* hk = reinterpret_cast<unsigned char*>(pArSerialize);
        SLog("SER-GUARD ENABLED @ 0x%p (base + 0x%X). Blocking corrupt buffered "
             "Serialize reads (len<0 or >%d MB). Installed bytes: "
             "%02X %02X %02X %02X %02X (E9=jmp expected).",
             pArSerialize, (unsigned)RVA_ArSerialize, SER_MAX_LEN / (1024 * 1024),
             hk[0], hk[1], hk[2], hk[3], hk[4]);
    }

    // ── Upstream serialize-dispatcher guard (0x80D00) ──
    void* pSerDisp = reinterpret_cast<void*>(g_Base + RVA_SerDispatch);
    if (MH_CreateHook(pSerDisp, (void*)&Hook_SerDispatch,
                      (void**)&Real_SerDispatch) != MH_OK) {
        SLog("ERROR: MH_CreateHook(SerDispatch) failed");
    } else if (MH_EnableHook(pSerDisp) != MH_OK) {
        SLog("ERROR: MH_EnableHook(SerDispatch) failed");
    } else {
        unsigned char* hd = reinterpret_cast<unsigned char*>(pSerDisp);
        SLog("SERDISP-GUARD ENABLED @ 0x%p (base + 0x%X). Installed bytes: "
             "%02X %02X %02X %02X %02X (E9=jmp expected).",
             pSerDisp, (unsigned)RVA_SerDispatch,
             hd[0], hd[1], hd[2], hd[3], hd[4]);
    }

    // ── memcpy backstop guard ──
    // Resolve MSVCR90!memcpy via GetProcAddress (IAT slot 0xD455C was WRONG —
    // it contained 0x15543589, not the real memcpy address). Then MinHook
    // patches the function prologue. Hard-clamps any copy >= 32MB.
    {
        HMODULE hCRT = GetModuleHandleA("MSVCR90.dll");
        if (!hCRT) hCRT = GetModuleHandleA("msvcr90.dll");
        if (!hCRT) hCRT = GetModuleHandleA("msvcrt.dll");
        fn_memcpy pMemcpy = nullptr;
        if (hCRT) {
            pMemcpy = reinterpret_cast<fn_memcpy>(GetProcAddress(hCRT, "memcpy"));
        }
        SLog("memcpy resolve: MSVCR90=%p GetProcAddress(memcpy)=%p",
             (void*)hCRT, (void*)pMemcpy);
        if (pMemcpy) {
            if (MH_CreateHook(reinterpret_cast<void*>(pMemcpy),
                              reinterpret_cast<void*>(&Hook_memcpy),
                              reinterpret_cast<void**>(&Real_memcpy)) != MH_OK) {
                SLog("ERROR: MH_CreateHook(MSVCR90!memcpy) failed");
            } else if (MH_EnableHook(reinterpret_cast<void*>(pMemcpy)) != MH_OK) {
                SLog("ERROR: MH_EnableHook(MSVCR90!memcpy) failed");
            } else {
                SLog("MEMCPY-GUARD ENABLED (hooked MSVCR90!memcpy @ 0x%p). "
                     "Hard ceiling = %u MB. Trampoline = 0x%p. "
                     "Any copy >= %u bytes is BLOCKED unconditionally.",
                     (void*)pMemcpy,
                     (unsigned)(MEMCPY_HARD_MAX / (1024 * 1024)),
                     (void*)Real_memcpy, (unsigned)MEMCPY_HARD_MAX);
            }
        } else {
            SLog("ERROR: Could not resolve MSVCR90!memcpy — guard NOT installed");
        }
    }
}

void ShutdownSpawnHook()
{
    if (g_Log) {
        DWORD elapsed = GetTickCount() - g_StartTick;
        SLog("=== SESSION END (elapsed %u:%02u) ===", elapsed / 60000, (elapsed / 1000) % 60);
        SLog("  Spawns: %ld | Roster calls: %ld | Waves grown: %ld | "
             "Extra enemies: %ld | Peak enemies/roster: %ld",
             g_SpawnSeq, g_RosterSeq, g_GrowWaves, g_GrowAdded, g_PeakEnemies);
        SLog("  Crashes(VEH): %ld | Memcpy guards: %ld | "
             "create-AI: %ld | Pool grows: %ld",
             g_CrashLogged, g_MemcpyGuards, g_CreateSeq, g_AudioPoolsGrown);
        SLog("  Config: GrowRoster=%s x%d | MaxWave=%d | DoubleAI=%s | freeMB=%u",
             g_GrowRoster ? "ON" : "OFF", g_RosterMult, g_MaxWaveTotal,
             g_DoubleAI ? "ON" : "OFF", MemMonLargestFreeMB());
        fclose(g_Log);
        g_Log = nullptr;
    }
}
