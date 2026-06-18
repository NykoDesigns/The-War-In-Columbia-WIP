"""Search deeper for vigor/weapon property names in the BioShock exe."""
import re

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

# More targeted terms
terms = [
    # Salt/energy cost properties
    b'SaltsPerUse', b'SaltPerUse', b'SaltsToUse', b'CostPerUse',
    b'CostToFire', b'SaltsCost', b'EnergyCost', b'VigorCost',
    b'AmmoPerShot', b'AmmoUsedPerShot', b'AmmoCostPerShot',
    b'ConsumeSalts', b'DrainSalts', b'UseSalts',
    b'SaltsConsumed', b'ResourceConsumed',
    # Try partial matches
    b'alts', b'PerUse', b'PerShot', b'AmmoUse',
    # Weapon types
    b'Triple_R', b'Machine_Gun', b'Machinegun',
    b'Burstgun', b'Crank_Gun', b'Barnstormer',
    b'BurstGun', b'CrankGun',
    b'Pistol', b'Shotgun', b'Sniper', b'Carbine',
    b'RPG', b'Launcher', b'Hailfire', b'Heater',
    b'Huntsman', b'Paddywhacker',
    # Fire interval
    b'FireInterval', b'BurstDelay', b'RefireTime',
    b'TimeBetweenShots', b'CycleTime',
]

for t in terms:
    hits = [m.start() for m in re.finditer(re.escape(t), data)]
    if hits:
        print(f"\n=== {t.decode():30s} ({len(hits)} hits) ===")
        shown = set()
        for h in hits[:15]:
            start = h
            while start > 0 and data[start-1] != 0 and data[start-1] >= 0x20 and data[start-1] < 0x7F:
                start -= 1
            end = h + len(t)
            while end < len(data) and data[end] != 0 and data[end] >= 0x20 and data[end] < 0x7F:
                end += 1
            s = data[start:end].decode('ascii', errors='replace')
            if s not in shown and len(s) < 120 and len(s) > 2:
                shown.add(s)
                print(f"  @0x{start:08X}: {s}")
