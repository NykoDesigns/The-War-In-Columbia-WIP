"""Search the BioShock exe for all XWeapon-related FName strings to find property names."""
import re

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

# Find all ASCII strings containing 'XWeapon' or 'XItem' or 'Vigor' or 'Plasmid'
# Also find property-like names that could be fire interval or salt cost
patterns = [
    rb'AXWeapon\w+',
    rb'UXWeapon\w+',
    rb'XWeapon\w+',
    rb'Vigor\w+',
    rb'Plasmid\w+',
    rb'Salt\w+',
]

# Let's just dump ALL null-terminated ASCII strings from the FName area (around 0xDA-0xE5)
# that look like property or class names
print("=== Weapon/Vigor/Salt related FName strings ===")
seen = set()
# Scan the name table region
for m in re.finditer(rb'[A-Z][a-zA-Z0-9_]{3,60}', data):
    s = m.group().decode('ascii')
    if s in seen:
        continue
    sl = s.lower()
    if any(k in sl for k in ['fireinterval', 'firerate', 'ammocost', 'saltcost', 'saltsper',
                               'costper', 'ammoper', 'ammoused', 'plasmidammo', 'vigorammo',
                               'energycost', 'manacost', 'ammoconsume', 'ammouse',
                               'magsize', 'clipsize', 'maxammo', 'reloadtime',
                               'weaponfire', 'refiretime', 'burstcount', 'burstdelay',
                               'spreadmin', 'spreadmax', 'spreadincrease',
                               'damage', 'instanthit']):
        seen.add(s)
        print(f"  @0x{m.start():08X}: {s}")

print("\n=== Weapon class names in exe ===")
seen2 = set()
for m in re.finditer(rb'[A-Z][a-zA-Z0-9_]{3,80}', data):
    s = m.group().decode('ascii')
    if s in seen2: continue
    sl = s.lower()
    if any(k in sl for k in ['machinegun', 'pistol', 'shotgun', 'rpg', 'carbine',
                               'sniper', 'crank', 'gatling', 'peppermill',
                               'hailfire', 'volley', 'burstgun', 'heater',
                               'repeater', 'barnstormer', 'huntsman',
                               'paddywhacker', 'chinaman', 'handcannon',
                               'broadsider', 'blunderbuss', 'triple']):
        seen2.add(s)
        print(f"  @0x{m.start():08X}: {s}")
