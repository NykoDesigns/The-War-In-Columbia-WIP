/// UE3 spawn hook for BioShock Infinite — "The War In Columbia"
///
/// Hooks AActor::execSpawn (the UnrealScript Spawn() native) to first OBSERVE
/// (log-only) what gets spawned, and later to MULTIPLY AI spawns.
#pragma once

void InitSpawnHook();
void ShutdownSpawnHook();

// Installs the Wwise AK::MemoryMgr::CreatePool hook that enlarges the audio
// memory pools (fixes the audio-pool exhaustion crash under heavy combat).
// MUST be called as early as possible — before the engine initializes Wwise.
void InstallAudioPoolHook();
