"""Search the exe for all FName strings that look like property names for XWeapon/XItem classes."""
import re

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

# Focus on regions where class/property FNames are stored
# Dump ALL readable strings in the name table area (around 0xDA-0xE9)
# and filter for property-looking names

print("=== All strings containing fire/ammo/salt/cost/damage near XWeapon area ===")
# Search the full name table for any property-like strings
seen = set()
for m in re.finditer(rb'[\x00]([A-Za-z][A-Za-z0-9_]{2,60})[\x00]', data):
    s = m.group(1).decode('ascii')
    if s in seen: continue
    sl = s.lower()
    # Filter for weapon/vigor related property names
    if any(k in sl for k in [
        'fire', 'ammo', 'salt', 'cost', 'energy', 'mana',
        'interval', 'rate', 'burst', 'clip', 'magazine', 'mag',
        'reload', 'spread', 'recoil', 'kickback',
        'damage', 'impulse', 'range', 'projectile',
        'vigor', 'plasmid', 'weapon', 'gear',
        'cooldown', 'cool_down', 'warmup', 'warm_up',
        'charge', 'drain', 'consume', 'deplete',
        'regen', 'recover', 'restore',
    ]):
        seen.add(s)
        pos = m.start() + 1
        # Check if it's in the common FName area
        print(f"  @0x{pos:08X}: {s}")

# Also specifically search for these exact strings
print("\n=== Specific property names ===")
exact = [
    b'FireInterval', b'TimeBetweenShots', b'RefireDelay',
    b'AmmoPerShot', b'SaltsPerUse', b'SaltsPerShot',
    b'AmmoPerFire', b'CostToFire', b'SaltDrain',
    b'EnergyPerShot', b'EnergyDrainRate', b'EnergyCostPerShot',
    b'ManaPerShot', b'ManaDrainRate',
    b'WeaponDamage', b'BaseDamage',
    b'MaxTotalAmmo', b'SpareAmmoCapacity',
]
for term in exact:
    pos = data.find(term)
    if pos != -1:
        print(f"  FOUND @0x{pos:08X}: {term.decode()}")
