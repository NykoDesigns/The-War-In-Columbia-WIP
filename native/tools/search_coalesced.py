"""Deep search CoalescedItems.xxx for weapon/vigor configuration data."""
import os, struct, re

pkg_path = r'D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\CoalescedItems.xxx'
data = open(pkg_path, 'rb').read()

# Search for ALL interesting terms
terms = [
    b'MachineGun', b'Repeater', b'Carbine', b'Peppermill',
    b'Burstgun', b'BurstGun', b'Hailfire', b'HailFire',
    b'Heater', b'Pistol', b'Shotgun', b'Sniper',
    b'HandCannon', b'Broadsider', b'Blunderbuss',
    b'CrankGun', b'GatlingGun', b'VolleyGun', b'Volley',
    b'Barnstormer', b'Huntsman', b'Paddywhacker',
    b'Triple_R', b'TripleR',
    b'RPG', b'Launcher',
    # Vigor
    b'MurderOfCrows', b'DevilsKiss', b'BuckingBronco',
    b'ShockJockey', b'Possession', b'Undertow', b'Charge',
    b'ReturnToSender', b'OldManWinter',
    # Properties
    b'FireInterval', b'FireRate', b'RateOfFire',
    b'AmmoPerShot', b'AmmoUsedPerShot',
    b'MaxAmmo', b'ClipSize', b'MagSize',
    b'ReloadTime', b'ReloadSpeed',
    b'Spread', b'SpreadMin', b'SpreadMax',
    b'InstantHitDamage', b'Damage',
    b'WeaponRange',
    # Salt/Energy
    b'SaltCost', b'SaltsPerUse', b'AmmoCost',
    b'PlasmidAmmo', b'PlasmidEnergy',
    b'EnergyPerShot', b'EnergyPerUse',
    b'EnergyCost', b'ManaCost',
    b'VigorCost', b'VigorAmmo',
    b'CostPerShot', b'CostPerUse',
]

print(f"Package size: {len(data):,} bytes")

for term in terms:
    positions = []
    idx = 0
    while True:
        idx = data.find(term, idx)
        if idx == -1: break
        positions.append(idx)
        idx += 1
    if positions:
        print(f"\n=== {term.decode():30s} ({len(positions)} hits) ===")
        for pos in positions[:5]:
            # Show context around the match
            start = max(0, pos - 40)
            end = min(len(data), pos + len(term) + 80)
            ctx = data[start:end]
            # Extract printable chars
            readable = ''
            for b in ctx:
                if 0x20 <= b < 0x7F:
                    readable += chr(b)
                else:
                    readable += '.'
            print(f"  @0x{pos:08X}: ...{readable}...")
