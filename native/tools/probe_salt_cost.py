"""Probe vigor salt cost values more carefully. Compare across vigor types and weapon types."""
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

gnames = struct.unpack('<I', read_mem(hp, base + 0xF9DFEC, 4))[0]

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    ep_data = read_mem(hp, gnames + index * 4, 4)
    if not ep_data: return None
    ep = struct.unpack('<I', ep_data)[0]
    if not ep: return None
    flags_data = read_mem(hp, ep + 0x08, 4)
    if not flags_data: return None
    flags = struct.unpack('<I', flags_data)[0]
    sa = ep + 0x10
    if flags & 1:
        d = read_mem(hp, sa, 512)
        if not d: return None
        try:
            end = d.index(b'\x00\x00')
            if end % 2 == 1: end += 1
            return d[:end].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, sa, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

# All vigor/weapon instances
weapons = {
    'DevilsKiss':     0x7DBC8000,
    'EnrageBase':     0x36662000,
    'EnrageFounder':  0x7DBCD000,
    'VoltSwarmFounder': 0x7DBCB000,
    'MachineGunVP':   0x7DBC0000,
    'MachineGunBase': 0x68D34000,
    'PistolBase':     0x3666E000,
    'CarbineBase':    0x68D45000,
    'ShotgunBase':    0x68D48000,
    'GatlingGun':     0x62F94000,
}

# Read all weapon data
weapon_data = {}
for name, addr in weapons.items():
    data = read_mem(hp, addr, 0x5000)
    if data and len(data) == 0x5000:
        weapon_data[name] = data

# Focus on comparing vigor weapons vs regular weapons
# Look at ALL offsets where vigors have integer-valued floats (1-200)
# that regular weapons DON'T have
vigors = ['DevilsKiss', 'EnrageBase', 'EnrageFounder', 'VoltSwarmFounder']
regulars = ['MachineGunVP', 'PistolBase', 'CarbineBase', 'ShotgunBase']

print("=== Offsets where vigorshave integer-valued floats (10-200) ===")
print(f"{'Offset':>8s}", end='')
for v in vigors:
    if v in weapon_data:
        print(f"  {v:>18s}", end='')
for r in regulars:
    if r in weapon_data:
        print(f"  {r:>14s}", end='')
print()

interesting_offsets = []
for off in range(0, 0x5000 - 4, 4):
    vigor_vals = {}
    regular_vals = {}
    
    for v in vigors:
        if v not in weapon_data: continue
        f = struct.unpack_from('<f', weapon_data[v], off)[0]
        if f == f:
            vigor_vals[v] = f
    
    for r in regulars:
        if r not in weapon_data: continue
        f = struct.unpack_from('<f', weapon_data[r], off)[0]
        if f == f:
            regular_vals[r] = f
    
    # Look for offsets where at least 2 vigors have values in 5-200 range
    # and regular weapons have 0 or very different values
    vigor_matches = sum(1 for v in vigor_vals.values() if 5 <= v <= 200)
    regular_matches = sum(1 for v in regular_vals.values() if 5 <= v <= 200)
    
    if vigor_matches >= 2 and regular_matches == 0:
        # Also check if values look like integer salt costs
        has_int = any(v == int(v) for v in vigor_vals.values() if 5 <= v <= 200)
        if has_int:
            print(f"+0x{off:04X}:", end='')
            for v in vigors:
                if v in vigor_vals:
                    print(f"  {vigor_vals[v]:18.1f}", end='')
                else:
                    print(f"  {'N/A':>18s}", end='')
            for r in regulars:
                if r in regular_vals:
                    print(f"  {regular_vals[r]:14.1f}", end='')
                else:
                    print(f"  {'N/A':>14s}", end='')
            print()
            interesting_offsets.append(off)

# Now examine the most promising salt cost offsets in detail
# The ShotCostAttrib struct property was found in XWeaponFireMode
# Let's also look at what +0x0240 area looks like on vigors (we know it's the fire interval)
print(f"\n=== Fire interval at +0x0240 for all weapons ===")
for name in sorted(weapon_data.keys()):
    f = struct.unpack_from('<f', weapon_data[name], 0x0240)[0]
    if f == f and abs(f) < 10:
        print(f"  {name:25s}: {f:.6f}")

# Check the 0x1000-stride repeating pattern for vigor costs
print(f"\n=== Checking 0x1000-stride pattern for DevilsKiss salt costs ===")
dk = weapon_data.get('DevilsKiss')
if dk:
    # Check several offsets at 0x1000 stride
    for base_off in range(0x0800, 0x0C00, 4):
        vals = []
        for stride_n in range(5):
            off = base_off + stride_n * 0x1000
            if off + 4 <= len(dk):
                f = struct.unpack_from('<f', dk, off)[0]
                i = struct.unpack_from('<i', dk, off)[0]
                if f == f and 1 <= f <= 200 and f == int(f):
                    vals.append((stride_n, off, f))
        if len(vals) >= 2:
            print(f"  Base 0x{base_off:04X}:", end='')
            for n, o, v in vals:
                print(f" [+0x{o:04X}]={v:.0f}", end='')
            print()

# Also check if there's a "ShotCost" or ammo cost field near the fire interval
print(f"\n=== Detailed view around +0x0240 (fire interval area) for DevilsKiss ===")
if dk:
    for off in range(0x0200, 0x0300, 4):
        f = struct.unpack_from('<f', dk, off)[0]
        i = struct.unpack_from('<i', dk, off)[0]
        if f == f and abs(f) < 100000:
            label = ""
            if off == 0x0240:
                label = " <-- FIRE INTERVAL"
            # Show for multiple weapons
            vals = {}
            for name, data in weapon_data.items():
                v = struct.unpack_from('<f', data, off)[0]
                if v == v and abs(v) < 100000:
                    vals[name] = v
            if len(set(f'{v:.4f}' for v in vals.values())) > 1:  # values differ
                desc = ' | '.join(f'{k}={v:.3f}' for k, v in sorted(vals.items())[:4])
                print(f"  +0x{off:04X}: {desc}{label}")

kernel32.CloseHandle(hp)
print("\nDone!")
