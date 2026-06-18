"""Search for vigor energy / salt related property names in the exe."""
import re

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

# Find all null-terminated ASCII strings that contain vigor/energy/salt/plasmid/ammo
seen = set()
for m in re.finditer(rb'[\x00]([A-Za-z][A-Za-z0-9_]{2,80})[\x00]', data):
    s = m.group(1).decode('ascii')
    if s in seen: continue
    sl = s.lower()
    if any(k in sl for k in [
        'vigoren', 'vigorammo', 'vigorcharge', 'vigorcost', 'vigorsalt',
        'plasmidam', 'plasmiden', 'plasmidcost',
        'healthbattery', 'energyper', 'energycost', 'energydrain',
        'saltper', 'saltcost', 'saltdrain', 'saltsper',
        'ammoper', 'ammocost', 'ammouse', 'ammoconsume',
        'consumeammo', 'consumeenergy', 'consumesalt',
        'costper', 'costto',
        'xweaponconsumable', 'xconsumable', 'xammocons',
        'weaponammo', 'maxammo', 'spareammocap',
    ]):
        seen.add(s)
        print(f"  @0x{m.start()+1:08X}: {s}")

# Also search for exec function names related to ammo/salt consumption
print("\n=== exec functions related to ammo/energy ===")
seen2 = set()
for m in re.finditer(rb'[\x00](AXWeapon[A-Za-z0-9_]*exec[A-Za-z0-9_]*)[\x00]', data):
    s = m.group(1).decode('ascii')
    if s in seen2: continue
    sl = s.lower()
    if any(k in sl for k in ['ammo', 'fire', 'consume', 'reload', 'energy', 'salt', 'cost']):
        seen2.add(s)
        print(f"  @0x{m.start()+1:08X}: {s}")

# Also search for XPawn exec functions related to vigor/energy
print("\n=== XPawn vigor/energy functions ===")
seen3 = set()
for m in re.finditer(rb'[\x00](AXPawn[A-Za-z0-9_]*exec[A-Za-z0-9_]*)[\x00]', data):
    s = m.group(1).decode('ascii')
    if s in seen3: continue
    sl = s.lower()
    if any(k in sl for k in ['vigor', 'energy', 'salt', 'plasmid', 'ammo', 'health', 'battery']):
        seen3.add(s)
        print(f"  @0x{m.start()+1:08X}: {s}")
