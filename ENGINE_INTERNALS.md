# BioShock Infinite — Engine Internals (Auto-Generated)

## 1. Spawn Pipeline Call Chain

```
AIDirectorTick (0x658A70) — per-frame, checks wave readiness
  └─ SpawnRoster (0x658250) — iterates TArray<AISpawnInfo> stride 0xF0
       ├─ PlaceAndSpawn (0x617360) — spatial: pool iteration + section matrix xform
       │    ├─ PoolTakePawn (0x61CAF0) — claims available substantiated pawn
       │    ├─ InitPhysics (0x80D220) — ragdoll/constraint setup
       │    └─ InitCollision (0x8C7D20) — collision channel registration
       ├─ BroadcastEvent (0x64B450) — post-spawn delegate fire
       └─ SpawnOneAI (0x657AB0) — per-descriptor wrapper
            └─ SpawnCore (0x654070) — gate checks then vtable+0xD0 dispatch
                 ├─ CheckPoolAvailable (0x6BAE00) — bSubstantiated at +0x204 bit6
                 ├─ CheckEncounterState (0x6343B0) — spawner state validation
                 └─ [vtable+0xD0] — actual spawn implementation (polymorphic)
                      └─ AllocPoolPawn (0x622150) — pool acquisition + bind
                           ├─ PoolTakePawn (0x61CAF0)
                           └─ BindPawnToController (0x6E7E60)
```

## 2. Pawn Pool System

BioShock Infinite pre-allocates a pool of invisible pawn actors at level load.

When an AI spawn is requested:

1. `CheckPoolAvailable` verifies pool has entries with `bSubstantiated` flag (bit 6 at +0x204)
2. `PlaceAndSpawn` iterates pool entries at `spawner+0x268` (array) with count at `spawner+0x26c`
3. For each pool entry, checks `entry[8] != 0` (active flag) and `entry[0]->vtable+0x18()` (not busy)
4. Computes world position via floating section matrix transform (section index → 4x4 matrix)
5. `PoolTakePawn` claims the pawn, marking it as in-use
6. `BindPawnToController` creates XAIController and possesses the claimed pawn
7. `BroadcastEvent` fires the Spawner's `__OnSpawnDelegate__` to register with damage system

**Critical insight**: Step 7 uses the descriptor's `Spawner` (+0xCC) and `Delegate` (+0xD8)
fields. Zeroing these in clones broke damage registration → invulnerable enemies.

## 3. SpawnCore Gate Conditions

```c
// FUN_00654070 — all must pass for spawn to proceed:
// 1. AI director state != 0x03 (normal) or != 0x01 (scripted)
// 2. Flag at spawner->field[0xB] + 0xE8, bit 1 set (encounter active)
// 3. CheckPoolAvailable() returns true
// 4. vtable+0x18 call returns 0 (not paused/blocked)
// 5. CheckEncounterState() returns true
// 6. Descriptor pointer (param_2) is non-null
// 7. If spawner flag bit 1: archetype vtable+0xDC must return true
// 8. Count check: field[0x1F]==0 OR field[0x1E] < field[0x1F]  (current < max)
// 9. Timing: float timing checks for spawn cooldown
```

## 4. AISpawnInfo Descriptor Layout (0xF0 bytes)

| Offset | Name | Type | Description |
|--------|------|------|-------------|
| +0x00 | GammaPack | ObjectProperty | Difficulty scaling pack |
| +0x04 | PawnArch | ObjectProperty | Pawn archetype (defines enemy type) |
| +0x08 | PawnLabels | TArray<FName> | Per-instance labels for pawn identification |
| +0x0C | CountA | int | Target spawn count (enemies from this descriptor) |
| +0x10 | CountB | int | Remaining spawn count (decremented as enemies spawn) |
| +0x14 | PawnAppearanceOverride | ObjectProperty | Visual override |
| +0x18 | VoiceTypeOverride | ObjectProperty | Voice type collection |
| +0x1C | SubtitleSpeakerOverride | ObjectProperty | Subtitle speaker |
| +0x20 | LootList | TArray<UObject*> | Loot drops on death |
| +0x2C | BoolFlags | bitfield | bGiveDefaultLoot, bDead, bCheckSpawnCollision, etc. |
| +0x30 | LootToAwardOnKillList | TArray<UObject*> | Loot awarded on kill |
| +0x3C | InventoryList | TArray<UObject*> | Weapons/items to equip |
| +0x48 | DeadPoseAnimSequence | ObjectProperty | Death pose animation |
| +0x4C | DeadPoseTime | float | Time in death pose |
| +0x50 | SirenPriority | float | Siren resurrection priority |
| +0x54 | MiniBuddyPriority | float | Handyman buddy priority |
| +0x58 | Faction | FName | Faction name (8 bytes) |
| +0x60 | SpawnLocation | XFloatingPosition | Local position + section index (16 bytes) |
| +0x70 | SpawnRotation | XFloatingRotator | Local rotation + section index (16 bytes) |
| +0x80 | SpawnFloatingSectionIndex | int | Floating section reference |
| +0x84 | AttachmentSetSeedOverride | int | Cosmetic attachment seed |
| +0x88 | MeshOverride | ObjectProperty | Mesh replacement |
| +0x8C | MaterialOverride | ObjectProperty | Material replacement |
| +0x90 | ThirdPersonWeaponModel | ObjectProperty | 3P weapon mesh |
| +0x94 | AttachmentSetOverride | ObjectProperty | Attachment override |
| +0x98 | CaptainPawn | ObjectProperty | Leader pawn reference |
| +0x9C | PatrolPath | ObjectProperty | AI patrol path |
| +0xA0 | SpatialRestrictions | ObjectProperty | Movement bounds |
| +0xA4 | AIRole | ObjectProperty | Behavior role assignment |
| +0xA8 | MinAILevel | int | Minimum difficulty level |
| +0xAC | MaxAILevel | int | Maximum difficulty level |
| +0xB0 | CullingPriority | int | Population management priority |
| +0xB4 | IdleRoleBehaviorTree | ObjectProperty | Idle behavior tree |
| +0xB8 | SirenResurrectionAnimSet | ObjectProperty | Siren rez anims |
| +0xBC | SmartTerrainScriptName | FName | Smart terrain ID (8 bytes) |
| +0xC4 | DistMoveFromSmartTerrain | float | Smart terrain offset distance |
| +0xC8 | FrobEvent | ObjectProperty | Interaction event handler |
| +0xCC | Spawner | ObjectProperty | Back-ref to XAIScriptedSpawner |
| +0xD0 | SpawnerLevelName | FName | Level name of spawner (8 bytes) |
| +0xD8 | Delegate | DelegateProperty | Post-spawn callback {Obj,FName,FName} 12 bytes |
| +0xE4 | ScenarioRestoreIndex | int | Save/load restore tracking |
| +0xE8 | RuntimeCnt | int (hidden) | Per-instance runtime counter/flags |
| +0xEC | RuntimePtr | void* (hidden) | Per-instance runtime heap pointer |

## 5. UObject Memory Layout (BioShock Infinite)

| Offset | Field |
|--------|-------|
| +0x00 | vtable* |
| +0x04 | HashNext |
| +0x08 | ObjectFlags (qword) |
| +0x10 | Index (int) — position in GObjects |
| +0x14 | Outer (UObject*) |
| +0x18 | Name (FName — Index @ +0x18, Number @ +0x1C) |
| +0x20 | Class (UClass*) |
| +0x24 | Archetype (UObject*) |

## 6. Key Spawner Object Layout (XAIScriptedSpawner)

| Offset | Field | Notes |
|--------|-------|-------|
| +0x84 | Flags (byte) | bit0=active, bit1=scripted, bit3=has_pool |
| +0x268 | PoolEntries (TArray) | Pre-allocated pawn pool entries |
| +0x26C | PoolCount (int) | Number of pool entries |
| +0x2C | EncounterState (ptr) | Points to encounter management data |
| +0x3C | PoolManager (ptr) | Pool availability checker |

## 7. Physics & Damage Registration

After a pawn is claimed from the pool and possessed by an AI controller:

1. **InitPhysics** (0x80D220) — sets up PhysX rigid body, creates ragdoll constraints
   - Constraint count ≈ 15 per humanoid pawn (each bone joint)
   - Uses PawnArch (+0x04) to determine skeleton/physics asset
2. **InitCollision** (0x8C7D20) — registers collision primitives
   - Sets collision channel (enemy = ECC_Pawn)
   - Enables trace responses for weapons
3. **BroadcastEvent** (0x64B450) — fires OnSpawn delegate
   - Delegate at descriptor +0xD8 references the Spawner (+0xCC)
   - Spawner notifies the damage system to register this pawn
   - Without this: pawn is visible, animated, has AI, but cannot receive damage

## 8. Clone Safety Rules (derived from analysis)

When cloning a descriptor for spawn multiplication:

| Field | Action | Reason |
|-------|--------|--------|
| TArrays (+0x08,+0x20,+0x30,+0x3C) | Deep-copy | Prevent double-free on engine GC |
| CountA/B (+0x0C,+0x10) | Force to 1 | Prevent count explosion (7→1 per clone) |
| SpawnLocation (+0x60) | Nudge X+96,Y±64 | Prevent collision overlap |
| RuntimeCnt/Ptr (+0xE8,+0xEC) | Zero | Per-instance; prevents serializer crash |
| Spawner (+0xCC) | KEEP | Required for post-spawn damage registration |
| Delegate (+0xD8) | KEEP | Required for OnSpawn callback fire |
| All other fields | Copy | Shared template data, safe to duplicate |

## 9. Floating Section System

Columbia's floating city uses a section-based coordinate system:

- Each floating island has a `SectionIndex` (int)
- Section transforms stored at `GWorld+0x200 + sectionIdx*0x40` (4x4 matrix)
- `SpawnLocation` stores LOCAL coordinates relative to a section
- `PlaceAndSpawn` transforms local→world via section matrix multiplication
- Descriptor `SpawnFloatingSectionIndex` (+0x80) indicates which section
- If clone and source have same section index, they spawn on same island (correct)

## 10. Decompilation Analysis (Key Findings)

### BroadcastEvent (0x64B450) — Delegate Delivery Mechanism
```c
// Iterates entries at this+0x4C (array, stride 0x30) with count at this+0x50
// Each entry has: [0]=chain_ptr, [4..5]=FName pair (event ID), [10]=flags
// When entry's FName matches param_2 (the event name):
//   - Iterates subscribed objects at entry[1] (array) with count at entry[2]
//   - Calls vtable+0x98 on each subscriber (the actual event handler)
// This is how OnSpawn notifications reach the damage system.
// If Delegate.ObjectPtr in descriptor is NULL → spawner's entry list is empty
// → no subscribers found → no vtable+0x98 call → no damage registration.
```

### PoolTakePawn (0x61CAF0) — Pool Acquisition Logic
```c
// 1. Early-out if *param_5 == 1 (already spawned)
// 2. If param_6 & 4 (spawn-from-pool): calls PlaceAndSpawn(0x617360)
// 3. PlaceAndSpawn returns 0 = success: allocates 0x4C-byte result,
//    copies 0x13 dwords (spawn transform data) into it
// 4. Else: falls through to vtable+0xB4 (alternative spawn path)
// 5. Calls FUN_007C49B0 to filter/sort candidates
// Key: the pool acquisition does NOT read Spawner/Delegate from the
// descriptor — those are used AFTER spawn by BroadcastEvent.
```

### SpawnCore Gate (0x654070) — 9 Conditions That Must Pass
```c
// All must be true for spawn to proceed:
// 1. AI director state != 0x03 (playing) or != 0x01 (scripted) based on flag
// 2. spawner->field[0xB]+0xE8 bit 1 set (encounter active)
// 3. CheckPoolAvailable() == true (pool has substantiated pawns)
// 4. vtable+0x18() == 0 (spawner not paused)
// 5. CheckEncounterState() == true
// 6. descriptor pointer != NULL
// 7. If spawner flag bit 1: archetype vtable+0xDC must return true
// 8. field[0x1F]==0 OR field[0x1E] < field[0x1F] (current < max)
// 9. Timing/cooldown check passes
// Then dispatches via vtable+0xD0(descriptor, archetype, param5, param6, 0)
```

### BindPawnToController (0x6E7E60) — Possession
```c
// 1. Checks param_1+0x30 (pawn reference) and param_1+0x2C (controller)
// 2. If neither exists: uses param_1+0x28 -> vtable+0xAC (create new controller)
// 3. Else: iterates pawn's component list via vtable+0x170 (count), +0x1C8 (get[i])
// 4. Calls vtable+0xAC on each component until one succeeds (possess)
// Key: This creates the XAIController and assigns it to the pooled pawn.
// The controller is what the game tracks for kill/damage events.
```

### Crash Pattern Analysis (from VEH logs)
```
EIP=0x5849AEBA (MSVCR90!memcpy+0x9A) badAddr=0x0017764C  ← streaming crash (FIXED by JLE→JBE)
EIP=0x00FFB573 (rva=0xBFB573)        badAddr=0x00000001  ← NULL deref in high module code
EIP=0x5619E693 (PhysX3_x86.dll)      badAddr=0x0000002C  ← PhysX constraint NULL (FIXED by CountA=1)
EIP=0x74B7CA4E (system DLL)          badAddr=0x0000F3F4  ← accessing freed TArray data
```

---

## 11. Runtime Statistics (from last session)

- **Total spawns logged**: 2756
- **Roster grows**: 27
- **Crashes detected**: 24
- **DESC-DIFF fields captured**: 67

### Roster Grow History (last 10)
  - `[01:15.484] ROSTER-GROW array=0x02156000 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[01:14.672] ROSTER-GROW array=0x98FF3000 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[00:54.000] ROSTER-GROW array=0x9AC94800 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[00:56.344] ROSTER-GROW array=0x597D6000 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[00:56.765] ROSTER-GROW array=0x96254800 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[00:53.156] ROSTER-GROW array=0x97B76000 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[01:11.234] ROSTER-GROW array=0x5F0EC000 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[01:09.062] ROSTER-GROW array=0x022F4800 Num 8->12 (Max=22, +4 extra, total-extra=4)`
  - `[04:13.547] ROSTER-GROW array=0x7F601800 Num 2->4 (Max=4, +2 extra, total-extra=6)`
  - `[04:42.890] ROSTER-GROW array=0x85B5D800 Num 8->12 (Max=22, +4 extra, total-extra=10)`

### Crash Events
  - `[02:20.953] *** CRASH code=0xC0000005 fault=0x5849AED8 (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x003EA000`
  - `[02:29.406] *** CRASH code=0xC0000005 fault=0x00FFB573 (rva=0xBFB573, EIP-in=MODULE) READ badAddr=0x00000001`
  - `[00:33.797] *** CRASH code=0xC0000005 fault=0x74B7CA4E (rva=0x0, EIP-in=SYSDLL) READ badAddr=0x0000F3F4`
  - `[02:11.625] *** CRASH code=0xC0000005 fault=0x5849AED8 (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x003C0000`
  - `[02:22.297] *** CRASH code=0xC0000005 fault=0x00FFB573 (rva=0xBFB573, EIP-in=MODULE) READ badAddr=0x00000001`
  - `[02:02.031] *** CRASH code=0xC0000005 fault=0x598AAEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x003B5243`
  - `[02:10.468] *** CRASH code=0xC0000005 fault=0x00FFB573 (rva=0xBFB573, EIP-in=MODULE) READ badAddr=0x00000001`
  - `[00:57.000] *** CRASH code=0xC0000005 fault=0x00FFB573 (rva=0xBFB573, EIP-in=MODULE) READ badAddr=0x00000001`
  - `[00:45.953] *** CRASH code=0xC0000005 fault=0x00FFB573 (rva=0xBFB573, EIP-in=MODULE) READ badAddr=0x00000001`
  - `[06:33.282] *** CRASH code=0xC0000005 fault=0x00FFB573 (rva=0xBFB573, EIP-in=MODULE) READ badAddr=0x00000001`
  - `[01:34.844] *** CRASH code=0xC0000005 fault=0x74B7CA4E (rva=0x0, EIP-in=SYSDLL) READ badAddr=0x0000F516`
  - `[02:17.375] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[02:10.625] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[01:30.828] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[00:54.000] *** CRASH code=0xC0000005 fault=0x74B7CA4E (rva=0x0, EIP-in=SYSDLL) READ badAddr=0x373A9090`
  - `[01:40.953] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[01:40.953] *** CRASH code=0xC0000005 fault=0xFFE889B4 (rva=0x0, EIP-in=OTHER) EXEC badAddr=0xFFE889B4`
  - `[01:19.844] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[02:05.140] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[00:53.156] *** CRASH code=0xC0000005 fault=0x74B7CA4E (rva=0x0, EIP-in=SYSDLL) READ badAddr=0x3FA00000`
  - `[00:03.344] *** CRASH code=0xC0000005 fault=0x00000000 (rva=0x0, EIP-in=OTHER) EXEC badAddr=0x00000000`
  - `[02:10.563] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C`
  - `[02:10.563] *** CRASH code=0xC0000005 fault=0x00496FC1 (rva=0x96FC1, EIP-in=MODULE) WRITE badAddr=0x001776F8`
  - `[05:02.437] *** CRASH code=0xC0000005 fault=0x5619E693 (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0000002C`

## 11. Function Database

Total functions decompiled: **23**

| Address | Name | Size | Calls | Callers | Role |
|---------|------|------|-------|---------|------|
| 0x00476780 | FUN_00476780 | 381 | 0 | 116 | WorldToLocal |
| 0x004787f0 | FUN_004787f0 | 76 | 0 | 10 | FindActor |
| 0x00482ab0 | FUN_00482ab0 | 44 | 1 | 2261 | appMalloc |
| 0x00482ae0 | FUN_00482ae0 | 34 | 1 | 4148 | appFree |
| 0x0048d890 | FUN_0048d890 | 61 | 1 | 39 |  |
| 0x00496f00 | FUN_00496f00 | 0 | 0 | 0 | StreamRead |
| 0x004c5e70 | FUN_004c5e70 | 33 | 1 | 324 | FindName |
| 0x00617360 | FUN_00617360 | 2860 | 2 | 3 | PlaceAndSpawn |
| 0x0061caf0 | FUN_0061caf0 | 615 | 5 | 7 | PoolTakePawn |
| 0x00622150 | FUN_00622150 | 302 | 3 | 37 | AllocPoolPawn |
| 0x00634320 | FUN_00634320 | 34 | 1 | 14 | ValidateSpawnSlot |
| 0x006343b0 | FUN_006343b0 | 0 | 0 | 0 | CheckEncounterState |
| 0x0064b450 | FUN_0064b450 | 621 | 4 | 38 | BroadcastEvent |
| 0x00651af0 | FUN_00651af0 | 0 | 0 | 0 |  |
| 0x00654070 | FUN_00654070 | 0 | 0 | 0 | SpawnCore |
| 0x00657ab0 | FUN_00657ab0 | 0 | 0 | 0 | SpawnOneAI |
| 0x00658250 | FUN_00658250 | 0 | 0 | 0 | SpawnRoster |
| 0x00658a30 | FUN_00658a30 | 644 | 4 | 0 |  |
| 0x006bae00 | FUN_006bae00 | 0 | 0 | 0 | CheckPoolAvailable |
| 0x006e7e60 | FUN_006e7e60 | 182 | 1 | 7 | BindPawnToController |
| 0x007c7c70 | FUN_007c7c70 | 22 | 2 | 39 | GetObjectRef |
| 0x0080d220 | FUN_0080d220 | 1762 | 10 | 1 | InitPhysics |
| 0x008c7d20 | FUN_008c7d20 | 121 | 1 | 7 | InitCollision |
