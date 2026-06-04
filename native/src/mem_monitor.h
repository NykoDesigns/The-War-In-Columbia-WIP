#pragma once

/// Initialize memory monitoring hooks (call from DllMain background thread).
/// Hooks VirtualAlloc/VirtualFree and starts a periodic stats logger.
void InitMemMonitor();

/// Shutdown memory monitoring (call from DLL_PROCESS_DETACH).
void ShutdownMemMonitor();

/// Largest contiguous free virtual-address block, in MB, as of the most recent
/// periodic measurement (updated ~every 5s; seeded at init). Used by the spawn
/// multiplier to gate extra spawns on available address space. Returns a large
/// value before the first measurement so early spawns are not blocked.
unsigned MemMonLargestFreeMB();
