# BioShock Infinite — SDK Data Map

*Auto-generated: 2026-06-08 20:37:23*

This file is a persistent knowledge base of game internals discovered
through reverse engineering. Updated by `tools/sdk_dump.py`.

---

## 1. Runtime Actor Census (from wic_spawn.log)

- **Total spawns logged**: 2756
- **AI Controllers**: 323
- **Roster grows**: 27
- **Crashes**: 24
- **Guard triggers**: memcpy=176, pool=8

### Patches Applied

- `[00:03.250] STREAMREAD-PATCH: patched JLE->JBE at 0x00496F5E (base+0x96F5E) [buf1]. Avail comparison is now UNSIGNED.`
- `[00:03.250] STREAMREAD-PATCH: patched JLE->JBE at 0x00496FA7 (base+0x96FA7) [buf2]. Avail comparison is now UNSIGNED.`
- `[00:03.328] STREAMREAD-PATCH: patched JLE->JBE at 0x00496F5E (base+0x96F5E) [buf1]. Avail comparison is now UNSIGNED.`
- `[00:03.328] STREAMREAD-PATCH: patched JLE->JBE at 0x00496FA7 (base+0x96FA7) [buf2]. Avail comparison is now UNSIGNED.`

### Actor Classes (top 20)

| Class | Count |
|-------|-------|
| MatineeActor | 1283 |
| XActorAttachment | 315 |
| XAIController | 266 |
| XInventoryManager | 109 |
| XWeapon | 79 |
| XHuman | 64 |
| XPlayerReplicationInfo | 61 |
| XWeaponModelFirstPerson | 58 |
| XPlayerController | 41 |
| DynamicCameraActor | 41 |
| XCamera | 41 |
| HUD | 41 |
| XLootContainerKAsset | 27 |
| DefaultPhysicsVolume | 23 |
| BroadcastHandler | 23 |
| XTrapBoltNetworkManager | 23 |
| XWeaponRollingThunderManager | 23 |
| XEffectObjectOverlayManager | 23 |
| XEmitterPool | 23 |
| XDecalManager | 23 |

### Recent Crashes
```
[00:53.156] *** CRASH code=0xC0000005 fault=0x74B7CA4E (rva=0x0, EIP-in=SYSDLL) READ badAddr=0x3FA00000
[00:03.344] *** CRASH code=0xC0000005 fault=0x00000000 (rva=0x0, EIP-in=OTHER) EXEC badAddr=0x00000000
[02:10.563] *** CRASH code=0xC0000005 fault=0x5849AEBA (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0017764C
[02:10.563] *** CRASH code=0xC0000005 fault=0x00496FC1 (rva=0x96FC1, EIP-in=MODULE) WRITE badAddr=0x001776F8
[05:02.437] *** CRASH code=0xC0000005 fault=0x5619E693 (rva=0x0, EIP-in=HEAP!!) READ badAddr=0x0000002C
```

---

## 2. Package Structures

### S_TWN_P

- Names: 12921, Imports: 1009, Exports: 33991

| Class | Export Count | Example |
|-------|-------------|---------|
| XAKAudioEventID | 1500 | PlayEventID |
| ParticleLODLevel | 1201 | ParticleLODLevel |
| XEffectParticle | 1037 | XEffectParticle |
| XEffectMultiple | 978 | XEffectMultiple |
| MaterialExpressionScalarParameter | 947 | MaterialExpressionScalarParameter |
| ParticleModuleSpawn | 930 | ParticleModuleSpawn |
| ParticleSpriteEmitter | 916 | ParticleSpriteEmitter |
| ParticleModuleSize | 911 | ParticleModuleSize |
| ParticleModuleRequired | 861 | ParticleModuleRequired |
| ParticleModuleLifetime | 855 | ParticleModuleLifetime |
| Package | 839 | AchievementQuest_Trash09242012 |
| DistributionFloatConstantCurve | 815 | DefaultMaxUseDistanceCurve |
| Texture2D | 813 | siren_NORM |
| XPatternPredicateObj_ArchIsA | 799 | XPatternPredicateObj_ArchIsA |
| MaterialExpressionStaticSwitchParameter | 743 | MaterialExpressionStaticSwitchParameter |

### S_TWN2_P

- Names: 17688, Imports: 1252, Exports: 45853

| Class | Export Count | Example |
|-------|-------------|---------|
| XAKAudioEventID | 1785 | PlayEventID |
| XAIBehaviorNodePriority | 1689 | XAIBehaviorNodePriority |
| ParticleLODLevel | 1405 | ParticleLODLevel |
| DistributionFloatConstantCurve | 1299 | DefaultMaxUseDistanceCurve |
| XEffectParticle | 1121 | XEffectParticle |
| ParticleSpriteEmitter | 1118 | ParticleSpriteEmitter |
| ParticleModuleSpawn | 1110 | ParticleModuleSpawn |
| ParticleModuleSize | 1083 | ParticleModuleSize |
| MaterialExpressionScalarParameter | 1056 | MaterialExpressionScalarParameter |
| XEffectMultiple | 1055 | XEffectMultiple |
| ParticleModuleRequired | 1031 | ParticleModuleRequired |
| ParticleModuleLifetime | 1020 | ParticleModuleLifetime |
| MorphemeAnimSequence | 1002 | MorphemeAnimSequence |
| Package | 986 | AchievementQuest_Trash09242012 |
| Texture2D | 981 | billyclub_DIFF |

### S_TWN3_P

- Names: 19648, Imports: 1376, Exports: 52927

| Class | Export Count | Example |
|-------|-------------|---------|
| XAKAudioEventID | 1926 | PlayEventID |
| DistributionFloatConstantCurve | 1839 | DefaultMaxUseDistanceCurve |
| ParticleLODLevel | 1766 | ParticleLODLevel |
| ParticleSpriteEmitter | 1401 | ParticleSpriteEmitter |
| Texture2D | 1393 | billyclub_DIFF |
| ParticleModuleSpawn | 1368 | ParticleModuleSpawn |
| ParticleModuleSize | 1363 | ParticleModuleSize |
| MaterialExpressionScalarParameter | 1361 | MaterialExpressionScalarParameter |
| ParticleModuleRequired | 1284 | ParticleModuleRequired |
| XEffectParticle | 1274 | XEffectParticle |
| ParticleModuleLifetime | 1272 | ParticleModuleLifetime |
| XEffectMultiple | 1234 | XEffectMultiple |
| XAIBehaviorNodePriority | 1200 | XAIBehaviorNodePriority |
| Package | 1190 | Achievements |
| MaterialExpressionStaticSwitchParameter | 1063 | MaterialExpressionStaticSwitchParameter |

### S_BW_P

- Names: 16991, Imports: 1285, Exports: 45507

| Class | Export Count | Example |
|-------|-------------|---------|
| XAKAudioEventID | 1827 | StopEventID |
| DistributionFloatConstantCurve | 1661 | DistributionFloatConstantCurve |
| ParticleLODLevel | 1630 | ParticleLODLevel |
| ParticleSpriteEmitter | 1263 | ParticleSpriteEmitter |
| XEffectParticle | 1255 | XEffectParticle |
| ParticleModuleSpawn | 1239 | ParticleModuleSpawn |
| ParticleModuleSize | 1233 | ParticleModuleSize |
| XEffectMultiple | 1178 | XEffectMultiple |
| ParticleModuleRequired | 1159 | ParticleModuleRequired |
| ParticleModuleLifetime | 1153 | ParticleModuleLifetime |
| MorphemeAnimSequence | 954 | MorphemeAnimSequence |
| XPatternPredicateObj_ArchIsA | 954 | XPatternPredicateObj_ArchIsA |
| XEffectSound | 877 | XEffectSound |
| Package | 852 | AchievementQuest_Trash09242012 |
| Texture2D | 821 | AlienMetal_cube_negx |

### S_BW2_P

- Names: 19302, Imports: 1453, Exports: 52085

| Class | Export Count | Example |
|-------|-------------|---------|
| XAKAudioEventID | 1939 | PlayEventID |
| DistributionFloatConstantCurve | 1835 | DistributionFloatConstantCurve |
| ParticleLODLevel | 1661 | ParticleLODLevel |
| XAIBehaviorNodePriority | 1470 | XAIBehaviorNodePriority |
| ParticleSpriteEmitter | 1296 | ParticleSpriteEmitter |
| ParticleModuleSize | 1268 | ParticleModuleSize |
| ParticleModuleSpawn | 1268 | ParticleModuleSpawn |
| XEffectParticle | 1267 | DevilsKiss_Grenade_Projectile_B |
| XEffectMultiple | 1233 | XEffectMultiple |
| MorphemeAnimSequence | 1196 | MorphemeAnimSequence |
| ParticleModuleRequired | 1188 | ParticleModuleRequired |
| ParticleModuleLifetime | 1183 | ParticleModuleLifetime |
| Package | 987 | AchievementQuest_Trash09242012 |
| XPatternPredicateObj_ArchIsA | 982 | XPatternPredicateObj_ArchIsA |
| MaterialExpressionScalarParameter | 960 | MaterialExpressionScalarParameter |

### S_BW3_P

- Names: 20409, Imports: 1468, Exports: 57482

| Class | Export Count | Example |
|-------|-------------|---------|
| DistributionFloatConstantCurve | 2139 | DistributionFloatConstantCurve |
| XAKAudioEventID | 2106 | PlayEventID |
| XAIBehaviorNodePriority | 2006 | XAIBehaviorNodePriority |
| ParticleLODLevel | 1730 | ParticleLODLevel |
| ParticleSpriteEmitter | 1362 | ParticleSpriteEmitter |
| MorphemeAnimSequence | 1356 | MorphemeAnimSequence |
| ParticleModuleSize | 1325 | ParticleModuleSize |
| ParticleModuleSpawn | 1323 | ParticleModuleSpawn |
| XEffectParticle | 1288 | XEffectParticle |
| XEffectMultiple | 1242 | XEffectMultiple |
| ParticleModuleRequired | 1241 | ParticleModuleRequired |
| ParticleModuleLifetime | 1235 | ParticleModuleLifetime |
| MaterialExpressionScalarParameter | 1163 | MaterialExpressionScalarParameter |
| Package | 1082 | AchievementQuest_Trash09242012 |
| Texture2D | 1050 | billyclub_DIFF |

---

## 3. Spawn System Exports

### S_TWN2_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIController | XAI_HumanBase_Controller | 96 | 0x396AFA |
| XAIController | XAI_GunnerBeta_Controller | 96 | 0x4376D34 |
| XAIController | XAI_MeleeBeta_Controller | 96 | 0x4376D94 |
| XAIController | XAI_PistolBeta_Controller | 96 | 0x4376DF4 |

### S_TWN3_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIController | XAI_HumanBase_Controller | 96 | 0x5881978 |
| XAIController | XAI_GunnerBeta_Controller | 96 | 0x58819E4 |
| XAIController | XAI_MeleeBeta_Controller | 96 | 0x5881A44 |

### S_BW_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x3C0BD28 |

### S_BW2_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIController | XAI_HumanBase_Controller | 96 | 0x48E5CF4 |
| XAIController | XAI_GunnerBeta_Controller | 96 | 0x48E5D60 |
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x48E6108 |

### S_BW3_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIController | XAI_HumanBase_Controller | 96 | 0x4A4C29 |
| XAIController | XAI_GunnerBeta_Controller | 96 | 0x4DA88AA |
| XAIController | XAI_MeleeBeta_Controller | 96 | 0x4DA890A |
| XAIController | MoCMan_Controller | 96 | 0x4DA896A |
| XAIController | XAI_ShotgunBeta_Controller | 96 | 0x4DA89CA |
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x4DA8D72 |

### S_Fink_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x4669E50 |

### S_Fink2_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x42E31A7 |

### S_Fink3_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x404E2A3 |

### S_Fink4_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIController | XAI_HumanBase_Controller | 96 | 0x414F31 |
| XAIController | XAI_GunnerBeta_Controller | 96 | 0x49F12C3 |
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x49F166B |

### S_EMP_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x3C7BF99 |

### S_EMP2_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIController | XAI_HumanBase_Controller | 96 | 0x46410B3 |
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x464145B |

### S_DCOM_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x44DF453 |

### S_CHU_P

| Class | Name | Size | Offset |
|-------|------|------|--------|
| XAIElizabethController | XAIElizabethController_Controller | 6607 | 0x3F629E9 |

---

## 4. Physics Actors

Total physics-related exports across combat maps: **1816**

### S_TWN_P (47 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKAsset | 25 |
| XLootContainerKActor | 22 |

### S_TWN2_P (59 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 34 |
| XLootContainerKAsset | 25 |

### S_TWN3_P (157 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 129 |
| XLootContainerKAsset | 28 |

### S_BW_P (135 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 109 |
| XLootContainerKAsset | 26 |

### S_BW2_P (137 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 110 |
| XLootContainerKAsset | 27 |

### S_BW3_P (145 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 118 |
| XLootContainerKAsset | 27 |

### S_Fink_P (177 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 151 |
| XLootContainerKAsset | 26 |

### S_Fink2_P (151 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 125 |
| XLootContainerKAsset | 26 |

### S_Fink3_P (149 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 123 |
| XLootContainerKAsset | 26 |

### S_Fink4_P (154 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 128 |
| XLootContainerKAsset | 26 |

### S_EMP_P (72 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 46 |
| XLootContainerKAsset | 26 |

### S_EMP2_P (86 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 60 |
| XLootContainerKAsset | 26 |

### S_DCOM_P (175 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 149 |
| XLootContainerKAsset | 26 |

### S_CHU_P (172 physics exports)

| Physics Class | Count |
|---------------|-------|
| XLootContainerKActor | 146 |
| XLootContainerKAsset | 26 |

---

## 5. Class Hierarchy (Spawn + Physics)

### Import Classes (Spawn/Physics related)

| Class | Packages | Source Module |
|-------|----------|---------------|
| Default__XAIController | S_BW2_P, S_BW3_P, S_EMP2_P | XCore |
| Default__XAIElizabethController | S_BW2_P, S_BW3_P, S_BW_P | XCore |
| Default__XLootContainerKActor | S_BW2_P, S_BW3_P, S_BW_P | XCore |
| Default__XLootContainerKAsset | S_BW2_P, S_BW3_P, S_BW_P | XCore |
| KAssetSkelMeshComponent | S_BW2_P, S_BW3_P, S_BW_P | XCore |
| XAIController | S_BW2_P, S_BW3_P, S_EMP2_P | Core |
| XAIElizabethController | S_BW2_P, S_BW3_P, S_BW_P | Core |
| XLootContainerKActor | S_BW2_P, S_BW3_P, S_BW_P | Core |
| XLootContainerKAsset | S_BW2_P, S_BW3_P, S_BW_P | Core |

---

## 6. Spawn Descriptor Layout

Descriptor objects found in packages (serial data preview):

- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 404 bytes @ 0x92E2F8
  ```
  572000006126000000000000a727000000000000bb0000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 404 bytes @ 0x92E48C
  ```
  582000006126000000000000a727000000000000bb0000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 404 bytes @ 0x92E620
  ```
  592000006126000000000000a727000000000000bb0000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 404 bytes @ 0x92E7B4
  ```
  5a2000006126000000000000a727000000000000bb0000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 265 bytes @ 0x92E948
  ```
  b30200006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 290 bytes @ 0x92EA51
  ```
  b40200006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92EB73
  ```
  6a1e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92EC9C
  ```
  6b1e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92EDC5
  ```
  6c1e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92EEEE
  ```
  6d1e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F017
  ```
  6e1e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F140
  ```
  6f1e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F269
  ```
  701e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F392
  ```
  711e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F4BB
  ```
  721e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F5E4
  ```
  731e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F70D
  ```
  741e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F836
  ```
  751e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92F95F
  ```
  761e00006126000000000000a727000000000000500000000000000034210000...
  ```
- **ParticleModuleEventReceiverSpawn** `ParticleModuleEventReceiverSpawn` — 297 bytes @ 0x92FA88
  ```
  771e00006126000000000000a727000000000000500000000000000034210000...
  ```

---

## 7. Known Runtime Offsets (from native hook)

### Spawn Descriptor (DESC_STRIDE bytes, cloned at runtime)

| Offset | Field | Notes |
|--------|-------|-------|
| +0x00..+0x?? | TArray fields | Multiple embedded TArrays (inventory, etc) |
| +0xCC | UObject* (Spawner) | Back-reference to XAIScriptedSpawner; zeroed in clones |
| +0xD8 | Delegate{Obj,FName,FName} | 12 bytes; object pointer to spawner; zeroed |
| +0xE8 | RuntimeCnt | Per-instance counter; zeroed in clones |
| +0xEC | RuntimePtr | Per-instance heap pointer; zeroed in clones |
| +OFF_DESC_PosX | float | Spawn X position; nudged +96 per clone |

### Stream Reader Object (FUN_00496F00 this-pointer)

| Offset | Field | Notes |
|--------|-------|-------|
| +0x00 | vtable* | Virtual table pointer |
| +0xAC | curPos (int) | Current read position in buffer |
| +0xB0 | remaining (int) | Bytes remaining before refill needed |
| +0xBC | buf1_base | Buffer 1 base address |
| +0xC0 | buf2_base | Buffer 2 base address |
| +0xC8 | buf1_end | Buffer 1 end address (0 when freed!) |
| +0xCC | buf2_end | Buffer 2 end address |
| +0xD4 | buf1_data | Buffer 1 current data pointer |
| +0xD8 | buf2_data | Buffer 2 current data pointer |
| vtable+0x3C | Refill vfunc | __thiscall(this, curPos, count) → int |

### Key RVAs (BioShockInfinite.exe, base 0x00400000)

| RVA | Symbol | Notes |
|-----|--------|-------|
| 0x22CA80 | SpawnActor | UWorld::SpawnActor |
| 0x658870 | SpawnRoster | Roster-based AI spawner |
| 0x96F00 | StreamRead (FUN_00496F00) | Double-buffered async reader (PATCHED) |
| 0x96F5E | StreamRead+0x5E | JLE→JBE patch site (buf1) |
| 0x96FA7 | StreamRead+0xA7 | JLE→JBE patch site (buf2) |
| 0x958C0 | PoolRefill | Object pool grow function |
| 0xEBA70 | ArSerialize | FArchive::Serialize |
| 0x80D00 | SerDispatch | Serialize dispatcher |
| 0x4D455C | memcpy IAT | Import Address Table slot |

---

## 8. Current Mod Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| g_RosterMult | 2 | Enemy wave multiplier |
| g_MaxWaveTotal | 8 | Max enemies per wave |
| MULT_MEM_GATE_MB | 500 | Min free memory to allow grow |
| MULT_MEM_PER_ADD_MB | 60 | Extra headroom per added enemy |
| ENABLE_SPAWN_MULT | true | Master spawn switch |
| ENABLE_AUDIO_ENLARGE | true | Wwise pool 2x enlarger |
| DESC_STRIDE | (from code) | Bytes per spawn descriptor |
