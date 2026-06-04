# BioShock Infinite — confirmed static addresses (ImageBase 0x00400000)

Build: PE link 2022-05-11 (SunBeam "revisited" 1.0.1643565).
`.text` is NOT encrypted (SteamStub only wraps entry point in `.bind`).
ASLR is active → DLL must rebase: `runtime = GetModuleHandle(NULL) + (staticVA - 0x400000)`.

| Symbol | Static VA | RVA | Notes |
|---|---|---|---|
| `AActor::execSpawn` | 0x00642D90 | 0x242D90 | UnrealScript Spawn() native (thiscall: this, FFrame& Stack, void* Result). Reads params via GNatives `[0x136DCB0]`. `*Result` = spawned AActor*. CONFIRMED in-game (calling convention validated). |
| `UWorld::SpawnActor` (candidate) | 0x0062CA80 | 0x22CA80 | The single direct call from execSpawn (at 0x642F6C). Real spawn function. |
| `GNatives` param-eval table | 0x0136DCB0 | 0xF6DCB0 | `GNatives[opcode]` used by exec functions to read script params. |

## Native function table
- Array of `{ char* asciiName; void* funcptr; }` (8-byte entries, NAME FIRST) in `.data`.
- Entry for execSpawn: name ptr @ VA 0x013317B8, func @ 0x013317BC. ~2699 entries.
- Lets us resolve ANY script native by name → address. See `ue3_analyze.py nativetable <filter>`.
- NOTE: earlier {func,name} assumption was WRONG; 0x6340C0 was a different (bool-returning) native. Scanner now fixed.

## Key AI-spawn classes/natives found
- `UXAISpawningManager` (execAddAIDiedDelegate 0x503640, execHandleAIStatusChanged 0x503600)
- `AXGameInfo::execInitSpawningManager` 0x50F760
- `UXSeqAct_SpawnAI` (execOnAISpawned 0x50BE60), `UXSeqAct_SpawnAIsWithinVolume`
- `AXSubstantiatableAISpawner`, `AXAISpawner`, `AXAIGammaSpawner/Volume`
- Despawn: `AXPawn::execOnDespawnAI` 0x4FA670 (Gamma despawning system — candidate lever to keep more AI alive)

## Name resolution (CONFIRMED via FName::ToString @ 0x4BD700)
- `GNames` array base pointer global: **base + 0xF9DFEC** (`mov ecx,[0x139DFEC]`). Simple `FNameEntry*` array (NOT chunked).
- Resolve: `entry = (*(void***)(base+0xF9DFEC))[FName.Index]`; flags byte @ `entry+0x08` (bit0 = wide), string @ `entry+0x10` (ANSI or UTF-16).
- Found via: `execPathName 0x4D9470` -> `GetPathName 0x4D0DA0` -> worker `0x4C5F30` -> `lea ecx,[obj+0x18]` (FName) -> `FName::ToString 0x4BD700`.

## UObject layout (32-bit)
- `+0x18` FName.Index, `+0x1C` FName.Number (object name)
- `+0x20` UClass* (confirmed constant per vtable in spawn logs)
- Class name = resolve FName at `(*(UClass**)(obj+0x20)) + 0x18`.

## UE3 v727 metadata offsets (bootstrapped via live CLASS-DUMP)
- `UObject`: Outer=+0x14, Name=+0x18, Class=+0x20, Archetype=+0x24
- `UField`: Next=+0x28
- `UStruct`: SuperField=+0x34, Children=+0x38
- `UProperty`: ArrayDim=+0x2C, ElementSize=+0x30, PropertyFlags=+0x34 (qword), **Offset=+0x48**
- `StructProperty`/`ObjectProperty`: inner type ptr at +0x58
- Walk a class: Children(+0x38) -> Next(+0x28) chain, then up SuperField(+0x34) for inherited.

## Spawn roster = `TArray<AISpawnInfo>` (CONFIRMED via STRUCT dump)
- The roster passed to `SpawnRoster` is `TArray{Data,Num,Max}`; each element is an
  `AISpawnInfo` struct, **stride 0xF0 (240 bytes)**. Growing Num within Max (cloning
  spare slots) makes the director spawn extra REAL enemies via its own path.
- `XAIScriptedSpawner` (extends `XAISpawner`) has a `SpawnInfo` property of type `AISpawnInfo`.
- `AISpawnInfo` is ONE pawn (no count field). Key offsets:
  - +0x04 `PawnArch` (ObjectProperty, archetype REF - safe to share)
  - +0x08 `PawnLabels` (TArray) — HEAP-OWNING
  - +0x20 `LootList` (TArray) — HEAP-OWNING
  - +0x2C bitfield bools: `bGiveDefaultLoot`, `bGiveDefaultInventory`, ... (all share +0x2C)
  - +0x30 `LootToAwardOnKillList` (TArray) — HEAP-OWNING
  - +0x3C `InventoryList` (TArray) — HEAP-OWNING
  - +0x60 `SpawnLocation` (XFloatingPosition -> Vector X/Y/Z @ +0x60/64/68, SectionIndex @ +0x6C)
  - +0x70 `SpawnRotation` (XFloatingRotator -> Rotator Pitch/Yaw/Roll)
  - +0xCC `Spawner` (ObjectProperty -> XAIScriptedSpawner back-REF)
  - +0xD8 `Delegate` (DelegateProperty, 12 bytes)
  - +0xE4 `ScenarioRestoreIndex` (int)
- **LEAK FIX**: a raw memcpy clone aliases the 4 TArray `.Data` pointers (+0x08,
  +0x20, +0x30, +0x3C) and the delegate (+0xD8) -> double-free/leak -> crash.
  Zero those headers in the clone so it owns no shared buffer (extra enemy uses
  default loadout via bGiveDefault* bools).

## RTTI: NOT available (compiled /GR-). Use GNames for class names.

## TODO
- Confirm AI-pawn class names from spawn log, build name/class filter.
- Confirm UWorld::SpawnActor signature for safe re-invocation (multiplication).
