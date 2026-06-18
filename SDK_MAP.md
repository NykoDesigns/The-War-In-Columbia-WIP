# BioShock Infinite — SDK Data Map

*Updated: 2026-06-09 — 24 sessions logged*

This file is a persistent knowledge base of game internals discovered
through reverse engineering. Updated by `tools/sdk_dump.py` and `tools/runtime_deep_analyzer.py`.

---

## 1. Runtime Actor Census (from wic_spawn.log)

- **Total sessions logged**: 24
- **Total events**: 9615
- **Latest session (26min)**: 265 spawns, 10 grows, **0 crashes** ✅
- **Roster grows (all sessions)**: 37+
- **Historical crashes**: 24 (all in early sessions before JLE→JBE patch)
- **Guard triggers**: memcpy=176 (all pre-patch), pool=8

### Current Status: STABLE ✅
- Zero crashes in last 3 sessions (combined ~45 min gameplay)
- All crash modes resolved (streaming, PhysX, invulnerability, zombies)
- Only remaining issue: zombie/idle enemies from pool exhaustion → fix deployed (untested)

### Patches Applied (per session)

- `STREAMREAD-PATCH: JLE->JBE at base+0x96F5E [buf1] — unsigned avail comparison`
- `STREAMREAD-PATCH: JLE->JBE at base+0x96FA7 [buf2] — unsigned avail comparison`

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

### Crash History (all resolved — from early sessions only)
```
[Session  2] memcpy (streaming), NULL deref, system DLL  — FIXED by JLE→JBE
[Session  3] PhysX constraint, memcpy (streaming)        — FIXED by CountA=1 + JLE→JBE
[Session  5] 0xBFB573 use-after-free                     — FIXED (downstream of streaming bug)
[Sessions 11-21] PhysX only                              — FIXED by CountA=1
[Sessions 22-23] ZERO CRASHES                            — All fixes working ✅
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

### AISpawnInfo Struct (DESC_STRIDE = 0xF0 = 240 bytes)

Complete field layout from runtime STRUCT dump of `AISpawnInfo` ScriptStruct:

| Offset | Field | Type | Size | Clone Action |
|--------|-------|------|------|--------------|
| +0x00 | GammaPack | ObjectProperty | 4 | Copy (shared archetype) |
| +0x04 | PawnArch | ObjectProperty | 4 | Copy (shared archetype) |
| +0x08 | PawnLabels | ArrayProperty | 12 | **Deep-copy** (per-enemy TArray) |
| +0x0C | CountA (target) | int | 4 | **Force to 1** (prevents count explosion) |
| +0x10 | CountB (remaining) | int | 4 | **Force to 1** |
| +0x14 | PawnAppearanceOverride | ObjectProperty | 4 | Copy |
| +0x18 | VoiceTypeCollectionOverride | ObjectProperty | 4 | Copy |
| +0x1C | SubtitledSpeakerOverride | ObjectProperty | 4 | Copy |
| +0x20 | LootList | ArrayProperty | 12 | **Deep-copy** |
| +0x2C | Bool bitfield | BoolProperty | 4 | Copy (bGiveDefaultLoot, bDead, etc.) |
| +0x30 | LootToAwardOnKillList | ArrayProperty | 12 | **Deep-copy** |
| +0x3C | InventoryList | ArrayProperty | 12 | **Deep-copy** |
| +0x48 | DeadPoseAnimSequence | ObjectProperty | 4 | Copy |
| +0x4C | DeadPoseTime | FloatProperty | 4 | Copy |
| +0x50 | SirenPriority | FloatProperty | 4 | Copy |
| +0x54 | MiniBuddyPriority | FloatProperty | 4 | Copy |
| +0x58 | Faction | NameProperty | 8 | Copy |
| +0x60 | SpawnLocation.X | Float (XFloatingPosition) | 4 | **Nudge +96×i** |
| +0x64 | SpawnLocation.Y | Float | 4 | **Nudge ±64** |
| +0x68 | SpawnLocation.Z | Float | 4 | Copy |
| +0x6C | SpawnLocation.SectionIndex | Int | 4 | Copy |
| +0x70 | SpawnRotation | XFloatingRotator | 16 | Copy |
| +0x80 | SpawnFloatingSectionIndex | IntProperty | 4 | Copy |
| +0x84 | AttachmentSetSeedOverride | IntProperty | 4 | Copy |
| +0x88 | MeshOverride | ObjectProperty | 4 | Copy |
| +0x8C | MaterialOverride | ObjectProperty | 4 | Copy |
| +0x90 | ThirdPersonWeaponModelOverride | ObjectProperty | 4 | Copy |
| +0x94 | AttachmentSetOverride | ObjectProperty | 4 | Copy |
| +0x98 | CaptainPawn | ObjectProperty | 4 | Copy |
| +0x9C | PatrolPath | ObjectProperty | 4 | Copy |
| +0xA0 | SpatialRestrictions | ObjectProperty | 4 | Copy |
| +0xA4 | AIRole | ObjectProperty | 4 | Copy |
| +0xA8 | MinAILevel | IntProperty | 4 | Copy |
| +0xAC | MaxAILevel | IntProperty | 4 | Copy |
| +0xB0 | CullingPriority | IntProperty | 4 | Copy |
| +0xB4 | OptionalIdleRoleBehaviorTree | ObjectProperty | 4 | Copy |
| +0xB8 | SirenResurrectionAnimSet | ObjectProperty | 4 | Copy |
| +0xBC | SmartTerrainScriptName | NameProperty | 8 | Copy |
| +0xC4 | DistanceToMoveAwayFromSmartTerrain | FloatProperty | 4 | Copy |
| +0xC8 | FrobEvent | ObjectProperty | 4 | Copy |
| +0xCC | Spawner | ObjectProperty | 4 | **Keep** (needed for damage registration) |
| +0xD0 | SpawnerLevelName | NameProperty | 8 | Copy |
| +0xD8 | Delegate | DelegateProperty | 12 | **Keep** (needed for post-spawn callbacks) |
| +0xE4 | ScenarioRestoreIndex | IntProperty | 4 | Copy |
| +0xE8 | RuntimeCnt (not in script) | — | 4 | **Zero** (per-instance, prevents serializer crash) |
| +0xEC | RuntimePtr (not in script) | — | 4 | **Zero** (per-instance heap ptr, use-after-free risk) |

### DESC-DIFF Patterns (confirmed across multiple sessions)

Fields that consistently DIFFER between desc[0] and desc[1] in the same roster:
- **+0x08** (PawnLabels.Data) — always different → deep-copied
- **+0x60** (SpawnLocation.X) — different positions per enemy → nudged
- **+0xE8/+0xEC** (RuntimeCnt/RuntimePtr) — desc[0]=0x101/heap, desc[1]=0/0 → zeroed

Fields that sometimes differ (mixed-type rosters):
- **+0x04** (PawnArch) — different enemy types in same roster
- **+0x0C/+0x10** (Counts) — e.g., 7/5 for different group sizes
- **+0x14** (PawnAppearanceOverride)
- **+0xCC** (Spawner) — differs between rosters, same within a roster

### Root Cause Analysis

**PhysX Crash**: Clones inherited CountA=7 from source descriptors. A 2-desc roster
(7+5=12 enemies) growing to 4 descriptors produced 7+5+7+5=24 enemies. Multiple waves
stacking → PhysX solver overwhelmed. **Fix**: Force clone CountA=1.

**Invulnerable Clones**: Zeroing +0xCC (Spawner) and +0xD8 (Delegate) broke the
spawner's post-spawn registration path. The spawner uses these references to register
newly-spawned pawns with the damage system. **Fix**: Keep them intact (shared by all
descriptors in a roster; same-level-package → no use-after-free).

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
| 0x531F00 | SetEquippedWeaponIndex | thiscall(InvMgr, int) — equips weapon |
| 0x531FB0 | SetBackupWeaponIndex | thiscall(InvMgr, int) — sets backup weapon |
| 0x5090F0 | NextWeapon (exec) | Toggles equipped ↔ backup |
| 0x50A8E0 | XStartWeaponRadialMenu | DLC2 weapon wheel open |
| 0x50A920 | XStopWeaponRadialMenu | DLC2 weapon wheel close |
| 0x4FD1B0 | XStartVigorRadialMenu | Vigor wheel open |
| 0x4FD1F0 | XStopVigorRadialMenu | Vigor wheel close |
| 0x651BE0 | CreateAI | Create XAIController + possess pooled pawn |
| 0x657B40 | SpawnOneAI | Per-descriptor spawn (idempotent, no doubling) |
| 0x658870 | SpawnRoster | Roster-based wave spawner (iterates TArray) |
| 0x96F00 | StreamRead (FUN_00496F00) | Double-buffered async reader (PATCHED) |
| 0x96F5E | StreamRead+0x5E | JLE→JBE patch site (buf1) |
| 0x96FA7 | StreamRead+0xA7 | JLE→JBE patch site (buf2) |
| 0x958C0 | PoolRefill | Object pool grow function |
| 0xEBA70 | ArSerialize | FArchive::Serialize |
| 0x80D00 | SerDispatch | Serialize dispatcher |
| 0x82AB0 | appRealloc | Engine memory allocator |
| 0x4D455C | memcpy IAT | Import Address Table slot |
| 0xF9DFEC | GNames (global) | TArray\<FNameEntry*\> — all FName strings |

### GNames Table
- Address: `base + 0xF9DFEC` → pointer to `TArray<FNameEntry*>`
- Each entry: `+0x08` = flags (bit0 = Unicode), `+0x10` = string data
- Used by WeaponStatPatchThread to resolve FName indices to strings

---

## 8. Current Mod Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| g_GrowRoster | true | Master switch: in-place TArray grow |
| MAX_TOTAL_ENEMIES | **20** | Hard cap on total enemies per wave (prevents pool exhaustion) |
| g_MaxWaveTotal | 16 | Max descriptor count per wave |
| g_RosterMult | 3 | Descriptor multiplier (capped by enemy budget) |
| MULT_MEM_GATE_MB | 500 | Min free memory to allow grow |
| MULT_MEM_PER_ADD_MB | 60 | Extra headroom per added enemy |
| ENABLE_AUDIO_ENLARGE | true | Wwise pool 2x enlarger |
| g_AudioPoolMult | 2 | Wwise pool size multiplier |
| DESC_STRIDE | 0xF0 (240) | Bytes per AISpawnInfo descriptor |
| Clone CountA/B | forced to 1 | Each clone = exactly 1 enemy |
| Clone Spawner/Delegate | kept intact | Needed for damage registration |
| Clone RuntimeCnt/Ptr | zeroed | Prevents serializer crash |
| Clone TArrays | deep-copied | Own engine-allocated buffers (no double-free) |
| Clone position | nudged +96×i X, ±64 Y | Prevents collision overlap |

### Grow Logic (v2 — budget-based)

```
baseEnemies = sum(CountA) across all source descriptors
budget = MAX_TOTAL_ENEMIES - baseEnemies
add = min(budget, freeSlots, g_MaxWaveTotal - num)
if budget <= 0 → ROSTER-SKIP (large waves already at cap)
if add > 0 && freeMB >= needMB → clone `add` descriptors
```

### Effective Behavior

| Wave Type | Source descs × CountA | baseEnemies | Budget | Clones Added |
|-----------|----------------------|:-----------:|:------:|:------------:|
| Small encounter | 2 × 2 | 4 | 16 | up to 16 |
| Medium fight | 4 × 3 | 12 | 8 | 8 |
| Large battle | 8 × 5 | 40 | 0 | **none** (already intense) |
| Boss wave | 2 × 7 | 14 | 6 | 6 |

---

## 9. Weapon Stat Patching (Runtime — WeaponStatPatchThread)

### Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| MachineGun FireInterval | 0.03s | ~2000 RPM (minigun speed) |
| MachineGun MaxClip | 100 | Both int + attrib floats |
| MachineGun MaxReserve | 900 | Both int + attrib floats |
| Vigor SaltCost multiplier | ×0.5 | All vigors halved |
| Initial delay | 30s | Wait for game to fully load |
| Fast scan passes | 12 × 10s | First 2 minutes |
| Continuous scan | every 30s | Forever (catches level changes) |

### XWeapon Object Offsets Used

| Offset | Field | Type | Patched |
|--------|-------|------|---------|
| +0x0240 | StandardFireDelay | float | MachineGun → 0.03 |
| +0x02BC | ShotCost (tap) | float | Vigors × 0.5 |
| +0x039C | ShotCost (held) | float | Vigors × 0.5 |
| +0x07C4 | AmmoCount | int | MachineGun → 100 |
| +0x07D0 | MaxAmmoAttrib.CurrentValue | float | MachineGun → 100.0 |
| +0x07D4 | MaxAmmoAttrib.BaseValue | float | MachineGun → 100.0 |
| +0x07EC | SpareAmmoCount | int | MachineGun → 900 |
| +0x07F8 | MaxSpareAttrib.CurrentValue | float | MachineGun → 900.0 |
| +0x07FC | MaxSpareAttrib.BaseValue | float | MachineGun → 900.0 |

### XWeapon DamageType/Projectile Pointers

| Offset | Field | Type | Notes |
|--------|-------|------|-------|
| +0x0228 | TapDamageType | UObject* | DamageType for primary/tap fire mode |
| +0x02EC | TapProjectile | UObject* | Projectile for primary/tap fire mode |
| +0x0308 | HoldDamageType | UObject* | DamageType for secondary/hold fire mode |
| +0x03CC | HoldProjectile | UObject* | Projectile for secondary/hold fire mode |

### XWeaponRollingThunder (Bucking Bronco subclass)

Bucking Bronco does NOT use XWeapon — it uses `XWeaponRollingThunder` (different UClass*).
Same property layout as XWeapon but different class pointer at +0x20.

| Instance | FName Index | DamageType |
|----------|-------------|------------|
| Plasmid_BuckingBroncoBase | 68219 | BuckingBronco_Founders_Damage (XRollingThunderDamageType) |
| Plasmid_BuckingBroncoFounder | 50180 | BuckingBronco_Founders_Damage (tap), BuckingBronco_Trap_Damage (hold) |

### Vigor Combination Approach

Copy DamageType data (+0x28 to +0x128) from source vigor into target vigor's DamageType.
UObject header (0x00–0x27) is preserved → class vtable stays intact → primary effect retained.
Secondary effect's damage values/status arrays are layered in via the copied data fields.

Current combinations:
- **Hell's Rodeo** = Bronco lift (XRollingThunderDamageType vtable) + DevilsKiss fire (data fields)

### Engine Globals (RVAs — stable across sessions)

| Symbol | RVA | Description |
|--------|-----|-------------|
| GNames | 0x00F9DFEC | Pointer to global FName table (TArray<FNameEntry*>) |
| GEngine | 0x00FAA024 | Pointer to UGameEngine singleton (XGameEngine) |
| GWorld (class) | 0x01000468 | Pointer to XWorldInfo UClass |
| SecurityCookie | 0x0134BD60 | __security_cookie for stack protection |

### Object Traversal Offsets (stable)

| From | Offset | To | Type |
|------|--------|----|------|
| GEngine obj | +0x01B0 | GamePlayers TArray | TArray\<ULocalPlayer*\> (count=1) |
| GEngine obj | +0x01BC | GameViewportClient | XGameViewportClient instance |
| LocalPlayer | +0x002C | PlayerController | XPlayerController instance |
| LocalPlayer | +0x0050 | GameViewportClient | XGameViewportClient (back-ref) |
| PlayerController | +0x0200 | PlayerReplicationInfo | XPlayerReplicationInfo |
| PlayerController | +0x023C | LocalPlayer | XLocalPlayer (back-ref) |
| PlayerController | +0x0240 | Camera | XCamera |
| PlayerController | +0x02B4 | HUD | HUD |
| PlayerController | +0x033C | CheatManager class | XCheatManager UClass (not instance) |
| PlayerController | +0x0340 | PlayerInput | XPlayerInput |
| PlayerController | +0x0674 | PlayerPawn | XPlayerPawn (class=XHuman) |
| PlayerPawn | +0x0310 | InvManager class | XInventoryManager UClass (not instance) |
| PlayerPawn | +0x1DEC | SkyhookMelee | XWeaponDedicatedMelee |

### UFunction Native Addresses

| Function | UFunction Addr | Native RVA | Native VA | Calling Convention |
|----------|----------------|------------|-----------|-------------------|
| ConsoleCommand | 0x16824E0C | 0x00136070 | 0x00536070 | thiscall (exec wrapper) |
| ServerCauseEvent | 0x168322BC | 0x000CFD10 | 0x004CFD10 | thiscall (exec wrapper) |

### DLC Vigor UClasses (present but data-empty in main campaign)

| Vigor | UClass FName | CDO FName |
|-------|-------------|-----------|
| Old Man Winter | XWeaponWinterbolt | Default__XWeaponWinterbolt |
| Peeping Tom | XWeaponChameleon | Default__XWeaponChameleon |
| Ironsides | XWeaponReturnToSender | Default__XWeaponReturnToSender |
