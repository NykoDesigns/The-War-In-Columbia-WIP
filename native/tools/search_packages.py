"""Search cooked package files for weapon/vigor property and item names."""
import os, glob

game_dir = r'D:\SteamLibrary\steamapps\common\BioShock Infinite'
cook_dir = os.path.join(game_dir, 'XGame', 'CookedPCConsole_FR')

search_terms = [
    b'MachineGun', b'Machine_Gun',
    b'Triple_R', b'TripleR',
    b'Repeater', b'Carbine', b'HandCannon',
    b'Burstgun', b'BurstGun',
    b'Hailfire', b'HailFire',
    b'CrankGun', b'Crank_Gun',
    b'Peppermill', b'PepperMill',
    b'PortableGatlingGun',
    b'FireInterval',
    b'AmmoPerShot', b'SaltsPerUse',
    b'AmmoCost', b'SaltCost',
    b'PlasmidAmmo', b'PlasmidEnergy',
    b'VigorAmmo', b'VigorCost',
    b'MaxAmmo', b'ClipSize', b'ReloadTime',
]

# Search GlobalXItemDatabase and weapon packages
target_packages = []
for f in glob.glob(os.path.join(cook_dir, '*.xxx')):
    fname = os.path.basename(f).lower()
    if any(k in fname for k in ['global', 'item', 'weapon', 'vigor', 'gun', 'xcore']):
        target_packages.append(f)

# Also add a few specific ones
for name in ['GlobalXItemDatabase_SF.xxx', 'GlobalXItemDatabase.xxx', 'XCore.xxx', 'XGame.xxx']:
    p = os.path.join(cook_dir, name)
    if os.path.exists(p) and p not in target_packages:
        target_packages.append(p)

if not target_packages:
    # Just search all .xxx files
    target_packages = glob.glob(os.path.join(cook_dir, '*.xxx'))[:30]

print(f"Searching {len(target_packages)} packages...")
for pkg_path in sorted(target_packages):
    try:
        data = open(pkg_path, 'rb').read()
    except:
        continue
    fname = os.path.basename(pkg_path)
    hits = []
    for term in search_terms:
        count = data.count(term)
        if count > 0:
            hits.append((term.decode(), count))
    if hits:
        print(f"\n=== {fname} ({len(data)//1024}KB) ===")
        for term, count in hits:
            print(f"  {term:30s} x{count}")
