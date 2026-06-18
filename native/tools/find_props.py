"""Search BioShock exe for property and class names related to salt costs and weapons."""
import re, sys

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

terms = [
    b'Salt', b'Salts', b'SaltCost', b'ManaCost', b'AmmoCost',
    b'Consumable', b'XWeapon', b'XItem',
    b'MachineGun', b'Crank', b'Gatling', b'Repeater', b'Peppermill',
    b'Volley', b'Burstgun', b'Carbine', b'Hailfire',
    b'FireInterval', b'FireRate', b'RateOfFire', b'RoundsPerMinute',
    b'VigorCost', b'EnergyCost', b'ResourceCost',
    b'SaltsUsed', b'SaltsRequired', b'SaltsDrain',
]

for t in terms:
    hits = [m.start() for m in re.finditer(re.escape(t), data)]
    if hits:
        print(f"\n=== {t.decode():30s} ({len(hits)} hits) ===")
        shown = set()
        for h in hits[:20]:
            start = h
            while start > 0 and data[start-1] != 0 and data[start-1] >= 0x20 and data[start-1] < 0x7F:
                start -= 1
            end = h
            while end < len(data) and data[end] != 0 and data[end] >= 0x20 and data[end] < 0x7F:
                end += 1
            s = data[start:end].decode('ascii', errors='replace')
            if s not in shown and len(s) < 100 and len(s) > 2:
                shown.add(s)
                print(f"  @0x{start:08X}: {s}")
