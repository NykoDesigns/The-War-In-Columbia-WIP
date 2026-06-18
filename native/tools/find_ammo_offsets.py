"""Find magazine/clip size and reserve ammo offsets by comparing integer values across weapons.
Known clip sizes: MachineGun=35, Pistol=12, Shotgun=4, Carbine=12, HandCannon=6, RPG=1, Sniper=4
Known reserve: MachineGun=175, Pistol=48, Shotgun=20, Carbine=48, HandCannon=24, RPG=5, Sniper=12"""
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

# Known weapon addresses from previous scans - find them fresh
# We need the XWeapon class address first
xweapon_class = None
# Search for XWeapon FName
xweapon_idx = -1
for i in range(200000):
    name = resolve_fname(i)
    if name == 'XWeapon':
        xweapon_idx = i
        break

print(f"XWeapon FName index: {xweapon_idx}")

# Find XWeapon class and all instances by scanning memory
from ctypes import wintypes
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]

MEM_COMMIT = 0x1000
PAGE_RW = 0x04
PAGE_RWX = 0x40
PAGE_WC = 0x08
PAGE_GUARD = 0x100

mbi = MEMORY_BASIC_INFORMATION()
addr = 0x10000
weapons = {}  # name -> address

# First pass: find XWeapon class
print("Searching for XWeapon class...")
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan:
        break
    
    if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and
        (mbi.Protect & (PAGE_RW | PAGE_RWX | PAGE_WC | 0x02 | 0x20))):  # include RO pages for class
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x28, 4):
                name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                if name_idx != xweapon_idx:
                    continue
                name_num = struct.unpack_from('<i', data, i + 0x1C)[0]
                if name_num != 0:
                    continue
                cls_ptr = struct.unpack_from('<I', data, i + 0x20)[0]
                if not cls_ptr:
                    continue
                # Check if cls is "Class" metaclass
                cls_data = read_mem(hp, cls_ptr + 0x18, 4)
                if not cls_data:
                    continue
                cls_name_idx = struct.unpack_from('<i', cls_data)[0]
                cls_name = resolve_fname(cls_name_idx)
                if cls_name == 'Class':
                    xweapon_class = (mbi.BaseAddress or 0) + i
                    print(f"Found XWeapon UClass @ 0x{xweapon_class:08X}")
                    break
        if xweapon_class:
            break
    scan = region_end

if not xweapon_class:
    print("Could not find XWeapon class!")
    sys.exit(1)

# Second pass: find all weapon instances
print("Searching for weapon instances...")
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan:
        break
    
    if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and
        (mbi.Protect & (PAGE_RW | PAGE_RWX | PAGE_WC))):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x400, 4):
                cls_ptr = struct.unpack_from('<I', data, i + 0x20)[0]
                if cls_ptr != xweapon_class:
                    continue
                name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                name_num = struct.unpack_from('<i', data, i + 0x1C)[0]
                if name_idx < 0 or name_idx > 500000:
                    continue
                name = resolve_fname(name_idx)
                if not name:
                    continue
                obj_addr = (mbi.BaseAddress or 0) + i
                key = f"{name}_{name_num}"
                weapons[key] = obj_addr
    scan = region_end

print(f"\nFound {len(weapons)} weapon instances:")
for k, v in sorted(weapons.items()):
    print(f"  {k:30s} @ 0x{v:08X}")

# Now read weapon data and search for ammo-related integers
# Known clip sizes (approximate)
known_clips = {
    'MachineGunBase': 35, 'MachineGunFounder': 35, 'MachineGunVP': 35,
    'PistolBase': 12, 'PistolFounder': 12,
    'ShotgunBase': 4, 'ShotgunFounder': 4,
    'CarbineBase': 12, 'CarbineFounder': 12,
    'HandCannonBase': 6, 'HandCannonFounder': 6,
    'RPGBase': 1, 'RPGFounder': 1,
    'SniperRifleBase': 4,
    'GatlingGun': 100,
}

weapon_data = {}
for key, addr in weapons.items():
    data = read_mem(hp, addr, 0x5000)
    if data and len(data) == 0x5000:
        weapon_data[key] = data

# Search for offsets where the integer value matches known clip sizes
print("\n=== Searching for ClipSize offsets ===")
clip_matches = {}
for off in range(0, 0x5000 - 4, 4):
    matches = 0
    total_checked = 0
    for key, clip in known_clips.items():
        k0 = f"{key}_0"
        if k0 not in weapon_data:
            continue
        val = struct.unpack_from('<i', weapon_data[k0], off)[0]
        total_checked += 1
        if val == clip:
            matches += 1
    if matches >= 4 and total_checked >= 5:
        # Print this offset with all values
        print(f"\n  +0x{off:04X} ({matches}/{total_checked} matches):")
        for key in sorted(known_clips.keys()):
            k0 = f"{key}_0"
            if k0 in weapon_data:
                val = struct.unpack_from('<i', weapon_data[k0], off)[0]
                expected = known_clips[key]
                mark = " ✓" if val == expected else ""
                print(f"    {key:25s}: {val:6d} (expected {expected}){mark}")
        clip_matches[off] = matches

# Also look for reserve ammo (MaxAmmoCount or SpareAmmoCount)
known_reserve = {
    'MachineGunBase': 175, 'MachineGunFounder': 175, 'MachineGunVP': 175,
    'PistolBase': 48, 'PistolFounder': 48,
    'ShotgunBase': 20, 'ShotgunFounder': 20,
    'CarbineBase': 48, 'CarbineFounder': 48,
    'HandCannonBase': 24, 'HandCannonFounder': 24,
    'RPGBase': 5, 'RPGFounder': 5,
    'SniperRifleBase': 12,
}

print("\n=== Searching for Reserve/SpareAmmo offsets ===")
for off in range(0, 0x5000 - 4, 4):
    matches = 0
    total_checked = 0
    for key, reserve in known_reserve.items():
        k0 = f"{key}_0"
        if k0 not in weapon_data:
            continue
        val = struct.unpack_from('<i', weapon_data[k0], off)[0]
        total_checked += 1
        if val == reserve:
            matches += 1
    if matches >= 3 and total_checked >= 5:
        print(f"\n  +0x{off:04X} ({matches}/{total_checked} matches):")
        for key in sorted(known_reserve.keys()):
            k0 = f"{key}_0"
            if k0 in weapon_data:
                val = struct.unpack_from('<i', weapon_data[k0], off)[0]
                expected = known_reserve[key]
                mark = " ✓" if val == expected else ""
                print(f"    {key:25s}: {val:6d} (expected {expected}){mark}")

# Also brute-force: look for integer 35 on MachineGun and 12 on Pistol at the same offset
print("\n=== Offsets where MachineGun=35 AND Pistol=12 (clip size candidates) ===")
mg_data = weapon_data.get('MachineGunBase_0') or weapon_data.get('MachineGunVP_0')
pi_data = weapon_data.get('PistolBase_0')
sg_data = weapon_data.get('ShotgunBase_0')
if mg_data and pi_data:
    mg_name = 'MachineGunBase_0' if 'MachineGunBase_0' in weapon_data else 'MachineGunVP_0'
    for off in range(0, 0x5000 - 4, 4):
        mg_val = struct.unpack_from('<i', mg_data, off)[0]
        pi_val = struct.unpack_from('<i', pi_data, off)[0]
        if mg_val == 35 and pi_val == 12:
            sg_val = struct.unpack_from('<i', sg_data, off)[0] if sg_data else '?'
            print(f"  +0x{off:04X}: MG={mg_val}, Pistol={pi_val}, Shotgun={sg_val}")

# Also check for MaxAmmoCount patterns: MG=175, Pistol=48
print("\n=== Offsets where MachineGun=175 AND Pistol=48 (reserve candidates) ===")
if mg_data and pi_data:
    for off in range(0, 0x5000 - 4, 4):
        mg_val = struct.unpack_from('<i', mg_data, off)[0]
        pi_val = struct.unpack_from('<i', pi_data, off)[0]
        if mg_val == 175 and pi_val == 48:
            sg_val = struct.unpack_from('<i', sg_data, off)[0] if sg_data else '?'
            print(f"  +0x{off:04X}: MG={mg_val}, Pistol={pi_val}, Shotgun={sg_val}")

kernel32.CloseHandle(hp)
print("\nDone!")
