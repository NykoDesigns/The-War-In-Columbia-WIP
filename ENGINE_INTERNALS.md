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

### Pool Exhaustion Behavior (confirmed Session #23)

The pool has a **fixed capacity** (~20-32 entries per encounter, varies by level).
When all entries are claimed:
- `PoolTakePawn` returns NULL
- `PlaceAndSpawn` still places a mesh body (the pawn actor exists in world)
- `BindPawnToController` is skipped → **no AI controller assigned**
- `BroadcastEvent` fires but the pawn has no damage receiver → **invulnerable**
- Result: enemy appears idle, does not attack, cannot be killed

Symptoms observed:
- Soldiers standing in idle pose, ignoring the player (screenshot confirmed)
- Specialized enemies (Firemen, Crows) missing entirely — their descriptors are processed
  later in the roster, after the pool is already exhausted by regular soldiers
- Consistent across multiple levels (not a one-off)

**Fix**: Budget-based cap limits total enemies per wave to MAX_TOTAL_ENEMIES=20, ensuring
pool never exhausts. Large waves that already exceed the cap get 0 clones added.

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

## 11. Runtime Statistics (Session #23 — latest clean session)

- **Duration**: 25m 57s
- **Total spawns**: 265
- **Roster grows**: 10 (39 total extra enemies across session)
- **Crashes**: **0** ✅
- **Peak totalEnemies per wave**: 41 (pre-fix — caused zombie spawns)
- **Memory (free)**: 1.2-1.4 GB throughout (never a bottleneck)
- **Level transitions**: 2 detected

### Roster Grow History (Session #23)
```
[04:38] ROSTER-GROW Num 2->4   (Max=4,  +2 clones, totalEnemies=14)
[05:00] ROSTER-GROW Num 2->4   (Max=4,  +2 clones, totalEnemies=10)
[06:30] ROSTER-GROW Num 6->16  (Max=22, +10 clones, totalEnemies=31) ⚠ HIGH
[08:27] ROSTER-GROW Num 8->16  (Max=22, +8 clones,  totalEnemies=41) ⚠ PEAK
[14:13] ROSTER-GROW Num 2->4   (Max=4,  +2 clones, totalEnemies=4)
[14:47] ROSTER-GROW Num 8->16  (Max=22, +8 clones,  totalEnemies=24) ⚠ HIGH
[18:17] ROSTER-GROW Num 2->4   (Max=4,  +2 clones, totalEnemies=12)
[20:54] ROSTER-GROW Num 2->4   (Max=4,  +2 clones, totalEnemies=6)
[22:02] ROSTER-GROW Num 2->4   (Max=4,  +2 clones, totalEnemies=11)
[23:11] ROSTER-GROW Num 3->4   (Max=4,  +1 clones, totalEnemies=8)
```

### Pawn Pool Exhaustion Discovery

The high-totalEnemies waves (31, 41, 24) caused **zombie spawns**:
- Pawn pool is fixed size (~20-32 entries per encounter)
- When all entries claimed: PoolTakePawn returns NULL
- PlaceAndSpawn still renders mesh body → visible idle enemy
- BindPawnToController skipped → no AI, no damage registration
- Later descriptors (Firemen, Crows) starved of pool entries → missing enemies

**Fix deployed**: Budget-based cap (MAX_TOTAL_ENEMIES=20) — awaiting verification.

### Historical Crash Summary (all resolved)

| Pattern | Count | Sessions | Fix |
|---------|:-----:|----------|-----|
| memcpy/streaming | 8 | 1-3 | JLE→JBE patch |
| 0xBFB573 use-after-free | 6 | 1-7 | Same patch (downstream) |
| System DLL (freed TArray) | 4 | 1-3 | Same patch |
| PhysX constraint | 1 | 21 | CountA=1 |
| Module WRITE (stream buf) | 1 | 21 | JLE→JBE patch |

## 12. Weapon Inventory System (Reverse-Engineered — COMPLETE)

### Architecture
- **XPlayerController** holds Pawn at offset +0x1FC
- **XInventoryManager** is a separate UObject; InvMgr+0xA0 = Pawn pointer
- Weapons stored in a **fixed 36-slot array** at InvMgr+0x1FC (indexed by weapon type ID)
- `EquippedWeaponIndex` (+0x2A0) and `BackupWeaponIndex` (+0x2A4) select active/backup
- **The 2-weapon limit is purely in the cycling logic** — the array keeps all owned weapons!
- Mouse wheel fires `NextWeapon` which only toggles between Equipped and Backup indices
- Burial at Sea DLC already has carry-all + weapon wheel using `CycleWeaponUp/Down`

### XInventoryManager Memory Layout (CONFIRMED)
```
+0x0A0: UObject* Pawn (owner)
+0x1FC: UObject* Weapons[36] — weapon object pointers indexed by type ID
         Slot[i] non-NULL = player owns weapon type i
         Observed: slots 0-8 populated (9 weapons), 9-35 = NULL
         Slots 0-3 = melee/vigors, Slots 4+ = standard guns
+0x28C: int PreviousEquippedIndex (-1 = none)
+0x290: int Previous of +0x2A8
+0x294: int Previous BackupWeaponIndex
+0x298: int Previous of +0x2AC
+0x29C: DWORD ChangeFlags
+0x2A0: int EquippedWeaponIndex (active weapon type, 0-35)
+0x2A4: int BackupWeaponIndex (secondary weapon type, 0-35)
+0x2A8: int AdditionalIndex (used in backup management)
+0x2AC: int AdditionalIndex (used in backup management)
```

### Key Insight: The 2-Weapon Limit
The game already stores ALL weapons the player picks up in the 36-slot array.
Nothing is ever removed during swaps. The limit is enforced only by:
- `NextWeapon` toggling between EquippedWeaponIndex and BackupWeaponIndex
- The HUD only showing 2 weapon slots

### Disassembled Functions
| Function | RVA | Signature | Purpose |
|----------|-----|-----------|---------|
| SetEquippedWeaponIndex | 0x531F00 | thiscall(InvMgr, int index) | Equips weapon at Weapons[index] |
| SetBackupWeaponIndex | 0x531FB0 | thiscall(InvMgr, int index) | Sets backup weapon |
| NextWeapon (exec) | 0x5090F0 | exec stub | Toggles equipped ↔ backup |
| ClientSetEquippedWeaponIndex (exec) | 0x509450 | exec stub | Network-safe wrapper |
| ClientSetBackupWeaponIndex (exec) | 0x5093F0 | exec stub | Network-safe wrapper |
| CycleWeaponUp/Down (exec) | 0x50AA20/60 | exec stub | DLC multi-weapon cycling |

### SetEquippedWeaponIndex Logic (0x531F00)
```
1. if (current == newIndex) return;
2. oldWeapon = Weapons[current]  // [this + current*4 + 0x1FC]
3. if (oldWeapon && current != BackupWeaponIndex)
      vtable[0xB4](oldWeapon)  // UnEquipWeapon
4. this->EquippedWeaponIndex = newIndex  // [this+0x2A0]
5. newWeapon = Weapons[newIndex]  // [this + newIndex*4 + 0x1FC]
6. if (newWeapon) EquipWeapon(newWeapon, true)
```

### Weapon Pickup Flow (Hold F)
1. `execXSwapWeaponWithUseTarget` (RVA 0x4FCE30) — async, starts animation
2. After animation completes: EquippedWeaponIndex changes
3. Old weapon stays in its array slot — never removed

### 4-Weapon Cycling Implementation
- Hook `NextWeapon` to scan Weapons[4..35] for non-NULL entries
- Cycle forward through populated gun slots (skip vigors at 0-3)
- Call `SetEquippedWeaponIndex(nextSlot)` directly at RVA 0x531F00

## 13. Function Database

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

## 14. XWeapon Runtime Stat Patching (CONFIRMED WORKING)

### Overview
The `WeaponStatPatchThread` in `ue3_spawn.cpp` dynamically modifies weapon properties at runtime by scanning all writable memory pages for XWeapon UObject instances and patching float/int values at known offsets.

### Discovery Process
1. Found XWeapon FName index via GNames table scan
2. Located XWeapon UClass by matching FName="XWeapon" + Class metaclass at +0x20
3. Walked UClass property chain (Children at +0x38, Next at +0x28)
4. **Key discovery**: `UProperty::Offset` is at **+0x48** on UProperty objects (NOT +0x5C)
5. Dumped `XAttributeModifiedValue` structs on live instances to map internal layout
6. Confirmed fire rate, ammo, and salt cost offsets via in-game behavior

### XWeapon Property Offsets (from object start)

| Offset | Property | Type | Notes |
|--------|----------|------|-------|
| +0x0240 | StandardFireDelay | float | Fire interval in seconds |
| +0x02BC | ShotCost (tap) | float | Vigor salt cost per tap |
| +0x039C | ShotCost (held) | float | Vigor salt cost for charged use |
| +0x03E1 | AmmoConsumptionPolicy | byte | Ammo consumption type |
| +0x03F4 | BoolFlags | bitfield | bHasInfiniteAmmoCount, bHasInfiniteSpareAmmoCount, etc. |
| +0x07B0 | ReloadAmmoCount | int | Rounds restored per reload |
| +0x07C0 | RoundsPerAmmoBunch | int | Rounds per pickup |
| +0x07C4 | **AmmoCount** | int | Current clip ammo |
| +0x07C8 | MaxAmmoCountAttrib | struct(36) | XAttributeModifiedValue for max clip |
| +0x07EC | **SpareAmmoCount** | int | Current reserve ammo |
| +0x07F0 | MaxSpareAmmoCountAttrib | struct(36) | XAttributeModifiedValue for max reserve |
| +0x0814 | LowSpareAmmoPercent | float | Low ammo warning threshold |
| +0x0818 | LowAmmoPercent | float | Low clip warning threshold |

### XAttributeModifiedValue Struct Layout (36 bytes)

```
+0x00: int/ptr  (usually 0; 0x7F7FFFFF = infinite flag)
+0x04: int      (usually 0)
+0x08: float    CurrentValue — the effective/computed max (game reads this)
+0x0C: float    BaseValue — original base (game recomputes CurrentValue from this)
+0x10-0x20: zeroes (modifier chain, usually empty for guns)
```

**CRITICAL**: Must patch BOTH `CurrentValue` (+0x08) AND `BaseValue` (+0x0C) within the struct.
The game recomputes CurrentValue from BaseValue + attribute modifiers every tick.
Patching only CurrentValue gets overwritten immediately.

### Current Patches Applied

| Target | Offset | Old Value | New Value | Status |
|--------|--------|-----------|-----------|--------|
| MachineGun FireInterval | +0x0240 | 0.075-0.170 | 0.03 | ✅ WORKING |
| MachineGun AmmoCount | +0x07C4 | 35-45 | 100 | ✅ WORKING |
| MachineGun MaxAmmo.Current | +0x07D0 | 25-45 | 100.0 | ✅ WORKING |
| MachineGun MaxAmmo.Base | +0x07D4 | 25-45 | 100.0 | ✅ WORKING |
| MachineGun SpareAmmo | +0x07EC | 75-215 | 900 | ✅ WORKING |
| MachineGun MaxSpare.Current | +0x07F8 | 75-215 | 900.0 | ✅ WORKING |
| MachineGun MaxSpare.Base | +0x07FC | 75-215 | 900.0 | ✅ WORKING |
| Vigor SaltCost (tap) | +0x02BC | varies | ×0.5 | ✅ WORKING |
| Vigor SaltCost (held) | +0x039C | varies | ×0.5 | ✅ WORKING |

### Two-Phase Patching Strategy

1. **Phase 1** — Collect archetype addresses: scan for XWeapon instances with FName containing "MachineGun" or "Gatling", store their addresses
2. **Phase 2** — Patch all instances: patch any XWeapon whose FName matches OR whose archetype pointer (+0x24) chains to a known archetype (catches live instances with FName "None")

### Thread Lifecycle
- Starts 30s after DLL load (game must be fully loaded)
- First 12 passes: every 10s (fast initial burst)
- After that: every 30s forever (catches level-change respawns)
- Idempotent for absolute patches (fire rate, ammo counts)
- Tracks patched addresses for multiplicative patches (salt cost halving)

### Known MaxAmmo Base Values (original)

| Weapon | MaxAmmo.Base (+0x07D4) | MaxSpare.Base (+0x07FC) |
|--------|------------------------|-------------------------|
| MachineGunBase | 45.0 | 215.0 |
| MachineGunFounder | 35.0 | 105.0 |
| MachineGunVP | 25.0 | 75.0 |
| PistolBase | 12.0 | 48.0 |
| ShotgunBase | 4.0 | 12.0 |
| CarbineBase | 12.0 | 48.0 |
| GatlingGun | 25.0 | 75.0 |
| Elizabeth's weapon | 9999.0 | 6.0 |

---

## 15. Vigor Combination System (Hell's Rodeo)

### Concept
Vigor combination fuses the effects of two vigors into one. The first implementation
combines **Bucking Bronco** (lift/levitate enemies) with **Devil's Kiss** (fire damage/burn)
to create **Hell's Rodeo** — enemies are lifted into the air AND set on fire simultaneously.

### Discovery: Bucking Bronco Is NOT XWeapon

Unlike other vigors (DevilsKiss, Enrage, VoltSwarm) which use the `XWeapon` class,
Bucking Bronco uses **`XWeaponRollingThunder`** — a subclass of XWeapon. This is why
the weapon stat patcher's XWeapon class-pointer scan never finds it.

| Vigor | Class | DamageType Class |
|-------|-------|------------------|
| Devil's Kiss | XWeapon | XDamageType |
| Enrage | XWeapon | XDamageType |
| VoltSwarm | XWeapon | XDamageType |
| **Bucking Bronco** | **XWeaponRollingThunder** | **XRollingThunderDamageType** |

### XWeapon DamageType Pointer Layout

All XWeapon (and subclass) instances store DamageType object pointers at:

| Offset | Purpose | Example (DevilsKiss) |
|--------|---------|---------------------|
| +0x0228 | Tap/primary DamageType* | `DevilsKiss_TapGrenade_Damage` (XDamageType) |
| +0x02EC | Tap/primary Projectile* | `DevilsKiss_TapGrenade_Projectile` (XProjectile) |
| +0x0308 | Hold/secondary DamageType* | `DevilsKiss_HoldGrenade_Damage` (XDamageType) |
| +0x03CC | Hold/secondary Projectile* | `DevilsKiss_HoldGrenade_Projectile` (XProximityGrenadeProjectile) |

### Bronco Instance Layout

| Instance | Address (runtime) | Class | Archetype |
|----------|-------------------|-------|-----------|
| Plasmid_BuckingBroncoBase | 0x36BDF000 | XWeaponRollingThunder | Default__XWeaponRollingThunder |
| Plasmid_BuckingBroncoFounder | 0x77492000 | XWeaponRollingThunder | Plasmid_BuckingBroncoBase |

Bronco DamageType instances:
- **Tap**: `BuckingBronco_Founders_Damage` (class: XRollingThunderDamageType)
- **Hold**: `BuckingBronco_Trap_Damage` (class: XRollingThunderDamageType)

### Combination Strategy: Data Copy with Header Preservation

The key insight: **lift behavior comes from the class vtable** (XRollingThunderDamageType code),
while **fire damage/effects come from the data fields** (inherited from base XDamageType).

By copying the DamageType DATA from DevilsKiss into Bronco's DamageType object while
**preserving the UObject header** (first 0x28 bytes), we get both effects:

```
┌──────────────────────────────────────────────────┐
│ UObject Header (0x00–0x27) — PRESERVED           │
│   +0x00: vtable → XRollingThunderDamageType      │  ← LIFT behavior
│   +0x04: HashNext                                │
│   +0x08: ObjectFlags                             │
│   +0x0C: HashBucket                              │
│   +0x10: StateFrame                              │
│   +0x14: Outer                                   │
│   +0x18: FName (BuckingBronco_Founders_Damage)   │
│   +0x20: UClass* (XRollingThunderDamageType)     │
│   +0x24: Archetype*                              │
├──────────────────────────────────────────────────┤
│ DamageType Data (0x28–0x128) — COPIED FROM DK   │
│   +0x28: bKillOnDeath flag                       │
│   +0x2C: DamageRadius (float) = 2000.0           │  ← DK fire values
│   +0x30: DamageOverTime (float) = 2000.0         │
│   +0x34: DamageImpulse (float) = 1000.0          │
│   +0x38: DamageMomentum (float) = 800.0          │
│   +0x3C: DamageKnockback (float) = -100.0        │
│   +0x40: DamageArea (float) = 2000.0             │
│   +0x44–0x80: Effect/status arrays (fire VFX)    │  ← FIRE visual effects
│   +0x88: XEffectSpeech reference                 │
│   +0x9C: DamageMultiplier table                  │
│   +0xF8: MaxRange (float) = 100.0                │
│   +0xFC: OptimalRange (float) = 250.0            │
└──────────────────────────────────────────────────┘
```

Result: XRollingThunderDamageType::ProcessDamage() applies lift (from vtable),
then base XDamageType fields apply fire damage/effects (from copied data).

### Implementation: VigorCombineThread

Located in `native/src/ue3_spawn.cpp`. Separate background thread (35s initial delay).

1. Resolves FName indices for `Plasmid_BuckingBroncoBase`, `Plasmid_BuckingBroncoFounder`, `Plasmid_DevilsKiss`
2. Scans all writable pages for UObject instances matching those FNames (by name index + number == 0)
3. Reads DamageType pointers at +0x0228 (tap) and +0x0308 (hold)
4. Copies 0x100 bytes from DK DamageType +0x28 into Bronco DamageType +0x28
5. Runs continuously (handles level transitions creating new instances)

### Rename: Bucking Bronco → Hell's Rodeo

Handled by `VigorRenamePatchThread` (same as other vigor renames):
- UPPERCASE UTF-16: `"BUCKING BRONCO"` → `"HELL'S RODEO"`
- Mixed-case UTF-16 + ASCII: `"Bucking Bronco"` → `"Hell's Rodeo"`
- Lowercase UTF-16: `"bucking bronco"` → `"hell's rodeo"`

Plus `UserInterface.int` localization file patched statically (6 entries).

### Future Vigor Combinations

This establishes the pattern for any future combinations:
1. Identify the two vigors' DamageType classes
2. Determine which provides the "primary effect" (keep its class/vtable)
3. Copy data fields from the "secondary effect" DamageType
4. Both effects stack via class polymorphism + inherited data fields

---

## 16. DLC Vigor Integration (In Progress)

### Goal

Bring the three DLC-exclusive vigors into the main campaign:
- **Old Man Winter** (XWeaponWinterbolt) — freeze enemies
- **Peeping Tom** (XWeaponChameleon) — invisibility
- **Ironsides** (XWeaponReturnToSender) — projectile shield / return

### DLC Vigor Classes (Loaded in Memory)

The UClasses and CDOs for DLC vigors exist in memory even during the main campaign
(they come from the base `XGame.xxx` script package):

| Vigor | UClass FName | CDO FName | Status |
|-------|-------------|-----------|--------|
| Old Man Winter | XWeaponWinterbolt | Default__XWeaponWinterbolt | Class loaded, CDO empty |
| Peeping Tom | XWeaponChameleon | Default__XWeaponChameleon | Class loaded, CDO empty |
| Ironsides | XWeaponReturnToSender | Default__XWeaponReturnToSender | Class loaded, CDO empty |

The CDOs are **empty shells** — all property data is zeroed. This means the C++ code/vtable
exists, but there are no configured damage types, projectiles, salt costs, or effects.
The actual configured archetypes (e.g., `Plasmid_WinterBolt`) live inside the DLC coalesced
packages on disk.

### DLC Package Locations

```
D:\SteamLibrary\steamapps\common\BioShock Infinite\DLC\
├── DLCB\CookedPCConsole_FR\    ← Burial at Sea Episode 1
│   ├── dlcb_CoalescedItems.xxx
│   └── ... (maps, textures, audio)
└── DLCC\CookedPCConsole_FR\    ← Burial at Sea Episode 2
    ├── dlcc_CoalescedItems.xxx
    └── ...
```

### Approach 1: Config-Based Package Loading (FAILED)

Added `SeekFreePackage=dlcb_CoalescedItems` and DLC `SeekFreePCPaths` to both
`DefaultEngine.ini` and user `XEngine.ini`. **Result: fatal crash on startup.**

- Error 1: `GetOutermost() Address = 0x4c6730` — package hierarchy failure
- Error 2: `I/O failure operating on 'Core'` — engine package system corrupted

The DLC coalesced packages have dependencies/structures incompatible with being
force-loaded as startup SeekFreePackages in the main campaign context.

**All config changes were reverted.**

### Approach 2: Dev Console Commands (BLOCKED)

Attempted to enable the in-game developer console:
- `[Engine.Console] ConsoleKey=Tilde` — already set, but `XCore.XConsole` overrides it
- Added `ConsoleKey=Tilde` to `[XCore.XConsole]` section in `XInput.ini`
- Removed conflicting Tilde → `WIDGETCOORDSYSTEMCYCLE` keybinding

**Result: Tilde key still does not open the console.** The shipping build of BioShock
Infinite likely has the console disabled at the code level (common for retail UE3 games).

### Approach 3: DLL-Based Engine Function Calls (CURRENT)

Call engine functions directly from our injected DLL to load packages and execute
commands at runtime. This requires finding function addresses via reverse engineering.

#### Engine Globals Found

| Symbol | RVA | Runtime Address | Notes |
|--------|-----|-----------------|-------|
| GNames | 0x00F9DFEC | base+0xF9DFEC | Global FName table pointer |
| GEngine | 0x00FAA024 | → XGameEngine obj | UGameEngine singleton |
| GWorld (class) | 0x01000468 | → XWorldInfo class | UClass, not instance |

#### Object Traversal Chain

```
GEngine (base+0x00FAA024)
└── XGameEngine @ 0x36C7EA00
    ├── +0x00B0: XGameViewportClient UClass
    ├── +0x01B0: TArray<ULocalPlayer*> [count=1, max=4]
    │   └── [0] XLocalPlayer @ 0x36B9C400
    │       ├── +0x002C: XPlayerController @ 0x65225400
    │       │   ├── vtable @ 0x011B2AC0
    │       │   ├── +0x0200: XPlayerReplicationInfo
    │       │   ├── +0x023C: XLocalPlayer (back-ref)
    │       │   ├── +0x0240: XCamera
    │       │   ├── +0x02B4: HUD
    │       │   ├── +0x033C: XCheatManager (UClass, no instance)
    │       │   ├── +0x0340: XPlayerInput
    │       │   └── +0x0674: XPlayerPawn @ 0x63386000
    │       │       ├── class = XHuman
    │       │       ├── +0x0310: XInventoryManager (UClass, no instance)
    │       │       └── +0x1DEC: SkyhookMelee (XWeaponDedicatedMelee)
    │       └── +0x0050: XGameViewportClient @ 0x36C3E000
    └── +0x01BC: XGameViewportClient @ 0x36C3E000
```

**Note**: Addresses like 0x65225400 are runtime heap allocations — they change every
session. The RVAs for globals and the traversal offsets (+0x01B0, +0x002C, etc.) are stable.

#### Key UFunction Addresses

Found by walking the `XPlayerController` class hierarchy's Children chain:

| Function | UFunction Address | Native Func VA | Native Func RVA | Notes |
|----------|-------------------|----------------|-----------------|-------|
| ConsoleCommand | 0x16824E0C | 0x00536070 | 0x00136070 | exec wrapper; params: FString Command, bool bWriteToLog → FString |
| ServerCauseEvent | 0x168322BC | 0x004CFD10 | 0x000CFD10 | Triggers Kismet `ce` events; params: FName EventName → int |

##### ConsoleCommand Parameter Layout (PropertySize = 25)

| Param | Type | Offset | Size |
|-------|------|--------|------|
| Command | StrProperty (FString) | 0x00 | 12 |
| bWriteToLog | BoolProperty | 0x0C | 1 |
| ReturnValue | StrProperty (FString) | 0x10 | 12 |

##### ServerCauseEvent Parameter Layout

| Param | Type | Offset | Size |
|-------|------|--------|------|
| EventName | NameProperty (FName) | 0x00 | 8 |
| EventTypesFound | IntProperty (out) | 0x08 | 4 |

#### Internal Call Targets (from exec wrappers)

**execConsoleCommand** (VA 0x00536070):
- +0x48: CALL 0x00513BE0 — FFrame parameter reader
- +0x5E: CALL [EAX+0x90] — **indirect vtable call** (the actual ConsoleCommand dispatch)
- +0x75: CALL 0x0049CB50 — FString::operator= (copies return value)
- RET at +0x8B

The key is the **indirect call at +0x5E**: `CALL [EAX+0x90]`. This reads the vtable from
the PlayerController and calls offset 0x90/4 = vtable index **36**. This is likely
`UObject::CallFunction` or `ProcessInternal`, which dispatches to the actual command
processing chain (ProcessConsoleExec → Exec → command handlers).

**execServerCauseEvent** (VA 0x004CFD10):
- +0x44: CALL 0x004CCFB0 — parameter parser (reads FName from stack)
- +0x80: CALL 0x004A10F0 — **actual CauseEvent implementation** (117 bytes)
  - Internally calls 0x00493B80 (Kismet sequence iteration)
- RET at +0xB1

#### LoadPackage-Related Functions

| Description | RVA | VA | Found via |
|-------------|-----|----|-----------|
| "Failed to load package header" handler | 0x000FB540 | 0x004FB540 | Unicode string xref |
| Caller of above (ULinkerLoad::Load?) | 0x0010AEE0 | 0x0050AEE0 | CALL xref; ~1017 bytes, 20 CALLs |
| "Failed to load package '%s'" handler A | 0x002002F0 | 0x006002F0 | Unicode string xref |
| "Failed to load package '%s'" handler B | 0x00202016 | 0x00602016 | Unicode string xref |
| Error formatting (appMsgf?) | 0x000A70F0 | 0x004A70F0 | Called by both handlers |

### Remaining Work

1. **Call ServerCauseEvent from DLL** — test with base-game cheats (e.g., `CheatShockJockey`)
   to verify the mechanism works before attempting DLC-specific calls
2. **Load DLC packages at runtime** — find and call `UObject::LoadPackage` or
   `StaticLoadObject` from the game thread (must not call from background thread)
3. **Instantiate DLC vigor archetypes** — once the package is loaded, the configured
   archetypes should appear in memory with populated data fields
4. **Add to player inventory** — find the weapon/vigor slot management system and
   insert the new vigor instances

### Base-Game Cheat FNames (for testing)

| FName | Purpose |
|-------|---------|
| CheatMurderOfCrows | Give Murder of Crows vigor |
| CheatShockJockey | Give Shock Jockey vigor |
| CheatDevilsKiss | Give Devil's Kiss vigor |
| CheatBuckingBronco | Give Bucking Bronco vigor |
| CheatPossession | Give Possession vigor |
| CheatReturnToSender | Give Return to Sender vigor |
| CheatUndertow | Give Undertow vigor |
| CheatChargeAttack | Give Charge vigor |

**No DLC vigor cheat events exist** (no CheatWinterBolt, etc.), confirming that the
Kismet-based cheat system only covers base-game vigors.

### Tool Chain for Package Extraction (WORKING)

1. **Decompress**: `Z:\UEdecompress\decompress.exe <package.xxx>` → outputs to `unpacked/`
2. **Parse**: UELib (`Z:\UEEXPLORER\Eliot.UELib.dll`) with `InitFlags.All`
3. **Dump**: `z:\TheWarInColumbia\native\tools\dlc_dumper\` C# project

### Extracted DLC Vigor Properties

#### Old Man Winter (XWeaponWinterbolt) — DLCB
- **Package**: `DLCB_Arc_XWinterBolt`
- **FireMode[0] (Tap — freeze bolt)**:
  - WeaponFireType = Projectile
  - DamageType = `XDLCBDamageType'Plasmid_WinterBolt_TapDamage'`
  - bUsesThreePartFire=true, bChanneledFire=true, bIsSingleShot=true
  - BeginFireTime=1.0, FireTime=2.0, EndFireTime=0.666, Cooldown=1.0
  - **ShotCost=33**, MinAmmoForAttack=33
  - ProjectileArchetype = `XActorSpawningProjectile'Plasmid_WinterBolt_TapProjectile'`
- **FireMode[1] (Hold — freeze trap)**:
  - DamageType = `XDamageType'WinterBolt_HoldGrenade_Damage'`
  - BeginFireTime=0.1, EndFireTime=0.6
  - **ShotCost=66**, MinAmmoForAttack=66
  - ProjectileArchetype = `XProximityGrenadeProjectile'WinterBolt_HoldGrenade_Projectile'`
- WeaponUnlockItemLookupID=965, WeaponConsumableItemLookupID=933
- MinDesiredPickupAmount=20, MaxDesiredPickupAmount=20

#### Peeping Tom (XDLCCWeaponChameleon) — DLCC
- **Package**: `DLCC_PreCoalescedItemAssets`
- **FireMode[0] (Activate invisibility)**:
  - bUsesThreePartFire=true, StandardFireDelay=0.5
  - BeginFireTime=0.5, FireTime=1.2, EndFireTime=0.4, Cooldown=3.0
  - **ShotCost=5**, MinAmmoForAttack=20
- **FireMode[1] (Channeled invisibility)**:
  - WeaponFireType = Custom, bChanneledFire=true, bIsSingleShot=true
  - Cooldown=1.0, MinAmmoForAttack=5
- ChameleonModEffect = `XEffectDynamicGameplayAttributeMod'FadeToBlackEffect'`
- HighlightEnemiesTime=-1.0 (disabled in DLCC; DLCB version doesn't have this)
- EnergyBurnRateVsSpeed: 0→0, 0.5→5.0, 0.8→10.0 (salt/sec vs movement speed)
- RoundsPerAmmoBunch=5
- WeaponUnlockItemLookupID=1155, WeaponConsumableItemLookupID=1170

#### Ironsides (XWeaponReturnToSender) — DLCC
- **Package**: `DLCC_PreCoalescedItemAssets`
- ShieldArchetype = `XDLCCReturnToSenderShield'DLCC_Plasmid_ReturnToSenderInsta_Shield'`
- ReturnToSenderTapShieldDuration.BaseValue=2.0
- ReturnToSenderShouldAbsorbAmmoAttrib.BaseValue=1.0
- ReturnToSenderMinShieldAbsorbDamageForTrapAttrib.BaseValue=0.0
- **FireMode[1]**:
  - DamageType = `XDamageType'Plasmid_ReturnToSenderCharge_Damage'`
  - BeginFireTime=0.5, FireTime=1.0, EndFireTime=0.3, Cooldown=1.0
  - ProjectileArchetype = `XReturnToSenderProxyGrenade'..._Upgrade_Projectile'`
- RoundsPerAmmoBunch=3, MaxAmmoCount.BaseValue=6.0
- WeaponUnlockItemLookupID=1169, WeaponConsumableItemLookupID=1208

### DLC-Specific Classes Discovered

| Class | Game | Purpose |
|-------|------|---------|
| XWeaponWinterbolt | DLCB/C | Old Man Winter vigor |
| XWeaponChameleon | DLCB | Peeping Tom (BaS Ep1 version) |
| XDLCCWeaponChameleon | DLCC | Peeping Tom (BaS Ep2 version, with upgrades) |
| XWeaponReturnToSender | DLCB/C | Return to Sender / Ironsides |
| XDLCBDamageType | DLCB | Freeze damage (extends XDamageType) |
| XDLCCDamageType | DLCC | DLCC-specific damage type |
| XDLCCReturnToSenderShield | DLCC | Ironsides shield object |
| XDLCCProximityGrenadeProjectile | DLCC | DLCC trap projectile |
| XDLC2Weapon | DLCC | DLCC generic weapon (Shock Jockey variant) |
