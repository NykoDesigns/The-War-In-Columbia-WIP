# The War In Columbia — TODO

## DLC Vigor Integration (HIGH PRIORITY — In Progress)

Bring Old Man Winter, Peeping Tom, and Ironsides into the main campaign.

### Completed
- [x] Confirmed DLC vigor UClasses exist in memory (XWeaponWinterbolt, XWeaponChameleon, XWeaponReturnToSender)
- [x] Confirmed CDOs are empty shells (no configured data — packages not loaded)
- [x] Located DLC package files on disk (`DLC\DLCB\`, `DLC\DLCC\`)
- [x] **Approach 1 FAILED**: Config-based SeekFreePackage loading → crashes game (I/O failure on 'Core')
- [x] **Approach 2 BLOCKED**: Dev console disabled in shipping build (tilde key does nothing)
- [x] Found GEngine (RVA 0x00FAA024) and full traversal chain to PlayerController/Pawn
- [x] Found `ConsoleCommand` UFunction (native VA 0x00536070) and `ServerCauseEvent` (native VA 0x004CFD10)
- [x] Mapped ConsoleCommand/ServerCauseEvent parameter layouts
- [x] Found LoadPackage-related function addresses via string xrefs
- [x] Identified base-game cheat FNames (CheatShockJockey, CheatDevilsKiss, etc.)
- [x] **Built package extraction tool chain** — decompress.exe + UELib + C# dumper
- [x] **Extracted ALL DLC vigor property data** from dlcb/dlcc_CoalescedItems.xxx
  - Old Man Winter: ShotCost=33/66, FireMode[0]=Projectile freeze, FireMode[1]=Trap
  - Peeping Tom: ShotCost=5, FireMode[0]=Invisibility activate, FireMode[1]=Channeled
  - Ironsides: Shield+absorb ammo, ReturnToSenderTapShieldDuration=2.0
- [x] **Mapped all DLC-specific classes**: XDLCBDamageType, XDLCCWeaponChameleon, XDLCCReturnToSenderShield, etc.
- [x] **Extracted full archetype references** (damage types, projectiles, model definitions)

### Next Steps
- [ ] **Test ServerCauseEvent from DLL** — call with CheatShockJockey FName to verify the exec mechanism works
- [ ] **Find ProcessEvent vtable index** — needed to call UFunction methods from C++ on any UObject
- [ ] **Find/call LoadPackage at runtime** — load `dlcb_CoalescedItems.xxx` from game thread after boot
- [ ] **Verify DLC archetypes populate** — after package load, check if Plasmid_WinterBolt etc. appear with data
- [ ] **Find inventory/vigor slot system** — understand how vigors are added to the player's loadout
- [ ] **Grant DLC vigors to player** — add loaded vigor instances to the player's inventory

## Weapon Reverse Engineering (Unknown Offsets)

These properties need memory analysis to find their XWeapon/DamageType offsets before we can patch them at runtime.

### Dead Ringer (Pistol)
- [ ] **Damage value** — increase to "high" (hand cannon feel)
- [ ] **Headshot multiplier** — increase to "very high" (reward aim)
- [ ] **Accuracy/spread** — tighten to "excellent"

### Boomstick (Shotgun)
- [ ] **Pellet count** — increase (more pellets per shot)
- [ ] **Damage value** — very high up close, awful at range
- [ ] **Damage falloff** — steep dropoff so it's a true CQB weapon
- [ ] **Knockback/stagger** — increase significantly
- [ ] **Reload speed** — faster reload

### Union Carbine
- [ ] **Damage value** — increase to "medium-high"
- [ ] **Recoil** — reduce to "low-medium" (clean, controlled feel)

### General
- [ ] **Reload speed offset** — find `ReloadTime` or equivalent on XWeapon
- [ ] **Recoil offset** — find spread/recoil properties
- [ ] **Damage offset** — likely on DamageType objects, need to map XDamageType fields
- [ ] **Headshot multiplier offset** — may be on DamageType or global config
- [ ] **Pellet count offset** — shotgun-specific, may be on XWeapon or projectile

## Weapon Renames (HUD Display)

The localization file renames work for vending machines, tooltips, and descriptions. But the Scaleform HUD may load weapon names from a different source. All new names are longer than originals, so broad memory scanning is NOT safe (Wwise audio crash).

- [ ] Investigate where Scaleform HUD pulls weapon display names from
- [ ] Find a targeted approach to patch HUD-only strings without hitting audio memory
- [ ] Verify: Pistol → Dead Ringer, Shotgun → Boomstick, Carbine → Union Carbine on HUD

## Future Vigor Combinations

Hell's Rodeo (Bronco + Devil's Kiss) is done. Same DamageType data-copy pattern works for:
- [ ] Other vigor pairings (e.g. Possession + Shock Jockey, etc.)
- [ ] User to decide which combinations to implement

## Weapon Carry Limit

- [ ] Increase from 2 weapons to 4 via mouse wheel cycling
- [ ] Override `NextWeapon` to cycle through 4 populated weapon slots
- [ ] Structure mapped, `SetEquippedWeaponIndex` identified — needs implementation
