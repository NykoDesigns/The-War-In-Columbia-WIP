"""Compare float values across different weapon instances to find fire rate offsets.
Offsets where values differ between weapons but are in the 0.01-5.0 range = weapon stats."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

def find_pid(name):
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for line in out.strip().split('\n'):
        if name.lower() in line.lower():
            return int(line.strip().split(',')[1].strip('"'))
    return None

def read_mem(hp, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(hp, ctypes.c_void_p(addr), buf, size, ctypes.byref(br)):
        return buf.raw[:br.value]
    return None

pid = find_pid('BioShockInfinite.exe')
if not pid: print("Game not running!"); sys.exit(1)

hp = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cb = wt.DWORD()
psapi.EnumProcessModules(hp, hMods, ctypes.sizeof(hMods), ctypes.byref(cb))
base = hMods[0]

# Weapon instances from previous scan
weapons = {
    'MachineGunVP':  0x7DBC0000,
    'MachineGunBase': 0x68D34000,
    'MachineGunFounder': 0x68D37000,
    'CarbineFounder': 0x375A3000,
    'CarbineBase':    0x68D45000,
    'PistolBase':     0x3666E000,
    'ShotgunBase':    0x68D48000,
    'RPGBase':        0x3666C000,
    'SniperBase':     0x3666D000,
    'GatlingGun':     0x62F94000,
    'HandCannonBase': 0x36661000,
    'DevilsKiss':     0x7DBC8000,
    'EnrageBase':     0x36662000,
}

# Read 0x5000 bytes from each weapon
weapon_data = {}
for name, addr in weapons.items():
    data = read_mem(hp, addr, 0x5000)
    if data and len(data) == 0x5000:
        weapon_data[name] = data
    else:
        print(f"  WARNING: Could not read {name} at 0x{addr:08X}")

print(f"Read data from {len(weapon_data)} weapons\n")

# Find offsets where MachineGun values differ from other weapons
# Focus on float values in weapon-stat ranges
mg_data = weapon_data.get('MachineGunVP')
if not mg_data:
    print("MachineGunVP data not available, trying MachineGunFounder")
    mg_data = weapon_data.get('MachineGunFounder')

if not mg_data:
    print("No machine gun data available!"); sys.exit(1)

# Compare MachineGun vs Pistol, Carbine, Sniper at each float offset
comparisons = ['PistolBase', 'CarbineBase', 'ShotgunBase', 'RPGBase', 'GatlingGun']
existing_comps = [c for c in comparisons if c in weapon_data]

print("=== Float offsets where MachineGunVP differs from other weapons ===")
print(f"Comparing against: {', '.join(existing_comps)}")
print(f"{'Offset':>8s}  {'MachineGunVP':>14s}", end='')
for c in existing_comps:
    print(f"  {c:>14s}", end='')
print()

interesting = []
for off in range(0, 0x5000 - 4, 4):
    mg_f = struct.unpack_from('<f', mg_data, off)[0]
    
    # Skip NaN/Inf and zero
    if mg_f != mg_f or abs(mg_f) > 100000 or mg_f == 0:
        continue
    
    # Check if this looks like a weapon stat (small positive value)
    if not (0.001 < mg_f < 5000):
        continue
    
    # Compare with other weapons
    values = {'MachineGunVP': mg_f}
    all_same = True
    any_valid = False
    
    for cname in existing_comps:
        c_data = weapon_data[cname]
        c_f = struct.unpack_from('<f', c_data, off)[0]
        values[cname] = c_f
        if c_f != c_f or abs(c_f) > 100000:
            continue
        any_valid = True
        if abs(c_f - mg_f) > 0.001:
            all_same = False
    
    # We want offsets where values DIFFER (different weapon stats)
    # and where multiple weapons have valid values
    if any_valid and not all_same:
        # Filter: at least 2 other weapons should have valid values in similar range
        valid_count = sum(1 for v in values.values() if v == v and 0.001 < abs(v) < 5000)
        if valid_count >= 3:
            is_fire_interval = all(0.01 < abs(v) < 2.0 for v in values.values() if v == v and v != 0)
            label = ""
            if is_fire_interval and 0.03 < mg_f < 0.2:
                label = " *** FIRE INTERVAL? ***"
            
            print(f"+0x{off:04X}: {mg_f:14.6f}", end='')
            for c in existing_comps:
                v = values.get(c, 0)
                if v == v and abs(v) < 100000:
                    print(f"  {v:14.6f}", end='')
                else:
                    print(f"  {'N/A':>14s}", end='')
            print(label)
            interesting.append((off, values, label))

# Also show the complete picture for fire-interval candidates
print(f"\n=== Fire interval candidates (all weapon types) ===")
fire_interval_offs = [off for off, vals, label in interesting if '***' in label]
for off in fire_interval_offs:
    mg_f = struct.unpack_from('<f', mg_data, off)[0]
    print(f"\nOffset +0x{off:04X}: MachineGunVP = {mg_f:.6f}")
    for name, data in sorted(weapon_data.items()):
        f = struct.unpack_from('<f', data, off)[0]
        if f == f and 0.001 < abs(f) < 10:
            print(f"  {name:25s}: {f:.6f}")

# Also look at vigor weapons for salt cost
print(f"\n=== Vigor weapon comparison (salt costs) ===")
vigor_weapons = {k: v for k, v in weapon_data.items() if k in ['DevilsKiss', 'EnrageBase']}
regular_weapons = {k: v for k, v in weapon_data.items() if k in ['MachineGunVP', 'PistolBase']}

if vigor_weapons and regular_weapons:
    dk_data = vigor_weapons.get('DevilsKiss')
    if dk_data:
        print("Offsets where DevilsKiss has float values 1-100 (possible salt costs):")
        for off in range(0, 0x5000 - 4, 4):
            f = struct.unpack_from('<f', dk_data, off)[0]
            if f == f and 1.0 <= f <= 100.0 and f == int(f):  # clean integer as float
                # Check if regular weapons have different values here
                mg_f = struct.unpack_from('<f', mg_data, off)[0]
                if mg_f != mg_f or abs(mg_f - f) > 0.5:
                    print(f"  +0x{off:04X}: DevilsKiss={f:.0f}, MachineGunVP={mg_f:.6f}")

kernel32.CloseHandle(hp)
print("\nDone!")
