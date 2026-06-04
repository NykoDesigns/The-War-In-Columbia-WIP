/// winmm.dll Proxy for War In Columbia Memory Monitor
///
/// This DLL masquerades as winmm.dll so it auto-loads into BioShock Infinite
/// (Windows loads DLLs from the app directory first). Every winmm export is a
/// PE *export forwarder* to "winmm_orig.dll" — a renamed copy of the real
/// 32-bit winmm.dll placed alongside this DLL (see winmm_proxy.def).
///
/// The Windows loader resolves forwarders natively during normal import
/// resolution, so NONE of our code runs when the game/binkw32/steamclient call
/// winmm functions. This completely avoids the loader-lock deadlock that the
/// previous trampoline + LoadLibrary approach caused.
///
/// DllMain only starts the deferred memory monitor on a background thread.

#include <Windows.h>

// PE export forwarders (winmm.* -> winmm_orig.*) via /EXPORT linker directives.
#include "winmm_forwards.h"

#ifdef WIC_ENABLE_MONITOR
#include "mem_monitor.h"
#include "ue3_spawn.h"

// ─── Background init thread ─────────────────────────────────────────────

static DWORD WINAPI InitThread(LPVOID)
{
    // Install the Wwise audio-pool hook FIRST, with no delay: AK::MemoryMgr
    // creates its fixed audio pools during early engine init (the main menu
    // already plays sound), so we must enlarge them BEFORE that happens to fix
    // the audio-pool exhaustion crash under heavy x5/x10 combat.
    InstallAudioPoolHook();

    // Wait for the game to finish early init before installing the rest.
    Sleep(3000);
    InitMemMonitor();
    InitSpawnHook();
    return 0;
}
#endif

// ─── DllMain ────────────────────────────────────────────────────────────

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    switch (reason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        // Defer ALL work off the loader lock. winmm exports are handled by
        // PE forwarders (winmm_orig.dll) — no code here touches them.
#ifdef WIC_ENABLE_MONITOR
        CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
#endif
        break;

    case DLL_PROCESS_DETACH:
#ifdef WIC_ENABLE_MONITOR
        ShutdownSpawnHook();
        ShutdownMemMonitor();
#endif
        break;
    }
    return TRUE;
}
