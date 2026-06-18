"""Find ammo offsets on XWeapon objects AND vending machine price structures.
Needs the game running with weapons loaded."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys, re

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

gnames_addr = struct.unpack('<I', read_mem(hp, base + 0xF9DFEC, 4))[0]

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    ep_data = read_mem(hp, gnames_addr + index * 4, 4)
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

# ── Step 1: Find key FName indices ──
print("=== Scanning GNames for key FNames ===")
target_names = ['XWeapon', 'AmmoCount', 'SpareAmmoCount', 'MaxAmmoCount', 'MaxSpareAmmoCount',
                'ClipSize', 'DefaultClipSize', 'VendCostValue', 'VendCostString',
                'XVendingMachine', 'XDollarBillScreen', 'XItemDatabase',
                'UpgradePrice', 'Price', 'BaseCost', 'SilverEagle']
found_names = {}
for i in range(300000):
    name = resolve_fname(i)
    if name and name in target_names:
        found_names[name] = i
        print(f"  FName[{i}] = '{name}'")
        if len(found_names) == len(target_names):
            break

# ── Step 2: Find XWeapon class and instances ──
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]

MEM_COMMIT = 0x1000
PAGE_RW = 0x04
PAGE_RWX = 0x40
PAGE_WC = 0x08
PAGE_GUARD = 0x100

mbi = MEMORY_BASIC_INFORMATION()
xweapon_idx = found_names.get('XWeapon', -1)

# Find XWeapon class
xweapon_class = None
print("\nSearching for XWeapon class...")
scan = 0x10000
while scan < 0x7FFF0000 and not xweapon_class:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan: break
    if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and
        (mbi.Protect & (PAGE_RW | PAGE_RWX | PAGE_WC | 0x02 | 0x20))):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x28, 4):
                if struct.unpack_from('<i', data, i + 0x18)[0] != xweapon_idx: continue
                if struct.unpack_from('<i', data, i + 0x1C)[0] != 0: continue
                cls_ptr = struct.unpack_from('<I', data, i + 0x20)[0]
                if not cls_ptr: continue
                cls_data = read_mem(hp, cls_ptr + 0x18, 4)
                if not cls_data: continue
                cls_name = resolve_fname(struct.unpack_from('<i', cls_data)[0])
                if cls_name == 'Class':
                    xweapon_class = (mbi.BaseAddress or 0) + i
                    print(f"  XWeapon UClass @ 0x{xweapon_class:08X}")
                    break
    scan = region_end

# Find all weapon instances
weapons = {}
print("\nSearching for weapon instances...")
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan: break
    if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and
        (mbi.Protect & (PAGE_RW | PAGE_RWX | PAGE_WC))):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x400, 4):
                if struct.unpack_from('<I', data, i + 0x20)[0] != xweapon_class: continue
                name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                name_num = struct.unpack_from('<i', data, i + 0x1C)[0]
                if name_idx < 0 or name_idx > 500000: continue
                name = resolve_fname(name_idx)
                if not name: continue
                key = f"{name}_{name_num}"
                weapons[key] = (mbi.BaseAddress or 0) + i
    scan = region_end

print(f"\nFound {len(weapons)} weapons:")
for k, v in sorted(weapons.items()):
    print(f"  {k:30s} @ 0x{v:08X}")

# ── Step 3: Read weapon data and find ammo offsets ──
weapon_data = {}
for key, addr in weapons.items():
    data = read_mem(hp, addr, 0x5000)
    if data and len(data) == 0x5000:
        weapon_data[key] = data

# Search for clip size patterns: look for int values that match known clip sizes
# BioShock Infinite default clip sizes (may vary slightly):
# MachineGun: 35, Pistol: 12, Shotgun: 4, Carbine: 12, HandCannon: 6, RPG: 1, Sniper: 4
# GatlingGun: 100
print("\n=== Brute-force search: MachineGun int=35 AND Pistol int=12 at same offset ===")
mg_key = next((k for k in weapon_data if 'MachineGunBase' in k), None)
pi_key = next((k for k in weapon_data if 'PistolBase' in k), None)
sg_key = next((k for k in weapon_data if 'ShotgunBase' in k), None)
hc_key = next((k for k in weapon_data if 'HandCannonBase' in k), None)
cb_key = next((k for k in weapon_data if 'CarbineBase' in k), None)
rpg_key = next((k for k in weapon_data if 'RPGBase' in k), None)
gg_key = next((k for k in weapon_data if 'GatlingGun' in k), None)

# Try various clip size combos
clip_candidates = [
    # (MG, Pistol, Shotgun, HC, Carbine, RPG, Gatling)
    (35, 12, 4, 6, 12, 1, 100),   # exact defaults
    (35, 12, 8, 6, 12, 2, 100),   # some variants
    (70, 24, 8, 12, 24, 2, 200),  # doubled?
]

for mg_clip, pi_clip, sg_clip, hc_clip, cb_clip, rpg_clip, gg_clip in clip_candidates:
    for off in range(0, 0x5000 - 4, 4):
        if not mg_key or not pi_key: break
        mg_val = struct.unpack_from('<i', weapon_data[mg_key], off)[0]
        pi_val = struct.unpack_from('<i', weapon_data[pi_key], off)[0]
        if mg_val == mg_clip and pi_val == pi_clip:
            vals = f"MG={mg_val}"
            vals += f", Pistol={pi_val}"
            if sg_key: vals += f", Shotgun={struct.unpack_from('<i', weapon_data[sg_key], off)[0]}"
            if hc_key: vals += f", HC={struct.unpack_from('<i', weapon_data[hc_key], off)[0]}"
            if cb_key: vals += f", Carbine={struct.unpack_from('<i', weapon_data[cb_key], off)[0]}"
            if rpg_key: vals += f", RPG={struct.unpack_from('<i', weapon_data[rpg_key], off)[0]}"
            if gg_key: vals += f", Gatling={struct.unpack_from('<i', weapon_data[gg_key], off)[0]}"
            print(f"  +0x{off:04X}: {vals}")

# Also search for reserve ammo: MG=175, Pistol=48
print("\n=== Brute-force: MachineGun int=175 AND Pistol int=48 (reserve ammo) ===")
if mg_key and pi_key:
    for off in range(0, 0x5000 - 4, 4):
        mg_val = struct.unpack_from('<i', weapon_data[mg_key], off)[0]
        pi_val = struct.unpack_from('<i', weapon_data[pi_key], off)[0]
        if mg_val == 175 and pi_val == 48:
            vals = f"MG={mg_val}, Pistol={pi_val}"
            if sg_key: vals += f", Shotgun={struct.unpack_from('<i', weapon_data[sg_key], off)[0]}"
            if hc_key: vals += f", HC={struct.unpack_from('<i', weapon_data[hc_key], off)[0]}"
            print(f"  +0x{off:04X}: {vals}")

# Broader: any offset where MG has 30-40 and Pistol has 10-15 (clip-like)
print("\n=== Offsets where MG=30..40, Pistol=8..15, Shotgun=2..6 (clip range) ===")
if mg_key and pi_key and sg_key:
    for off in range(0, 0x5000 - 4, 4):
        mg_val = struct.unpack_from('<i', weapon_data[mg_key], off)[0]
        pi_val = struct.unpack_from('<i', weapon_data[pi_key], off)[0]
        sg_val = struct.unpack_from('<i', weapon_data[sg_key], off)[0]
        if 30 <= mg_val <= 40 and 8 <= pi_val <= 15 and 2 <= sg_val <= 8:
            vals = f"MG={mg_val}, Pistol={pi_val}, Shotgun={sg_val}"
            if hc_key: vals += f", HC={struct.unpack_from('<i', weapon_data[hc_key], off)[0]}"
            if cb_key: vals += f", Carbine={struct.unpack_from('<i', weapon_data[cb_key], off)[0]}"
            if rpg_key: vals += f", RPG={struct.unpack_from('<i', weapon_data[rpg_key], off)[0]}"
            if gg_key: vals += f", Gatling={struct.unpack_from('<i', weapon_data[gg_key], off)[0]}"
            print(f"  +0x{off:04X}: {vals}")

# Also look for reserve: MG=100-200, Pistol=30-60
print("\n=== Offsets where MG=100..200, Pistol=30..60, Shotgun=10..30 (reserve range) ===")
if mg_key and pi_key and sg_key:
    for off in range(0, 0x5000 - 4, 4):
        mg_val = struct.unpack_from('<i', weapon_data[mg_key], off)[0]
        pi_val = struct.unpack_from('<i', weapon_data[pi_key], off)[0]
        sg_val = struct.unpack_from('<i', weapon_data[sg_key], off)[0]
        if 100 <= mg_val <= 200 and 30 <= pi_val <= 60 and 10 <= sg_val <= 30:
            vals = f"MG={mg_val}, Pistol={pi_val}, Shotgun={sg_val}"
            if hc_key: vals += f", HC={struct.unpack_from('<i', weapon_data[hc_key], off)[0]}"
            if cb_key: vals += f", Carbine={struct.unpack_from('<i', weapon_data[cb_key], off)[0]}"
            if rpg_key: vals += f", RPG={struct.unpack_from('<i', weapon_data[rpg_key], off)[0]}"
            if gg_key: vals += f", Gatling={struct.unpack_from('<i', weapon_data[gg_key], off)[0]}"
            print(f"  +0x{off:04X}: {vals}")

# ── Step 4: Search for VendCostValue in GNames and find XVendingMachine/XItemDatabase objects ──
print("\n=== Searching for vending/item database objects ===")
vend_names_to_find = ['XVendingMachine', 'XDollarBillScreen', 'XItemDatabase', 'XItemDatabaseDiff']
vend_fname_indices = {}
for i in range(300000):
    name = resolve_fname(i)
    if name in vend_names_to_find:
        vend_fname_indices[name] = i
        print(f"  FName[{i}] = '{name}'")
        if len(vend_fname_indices) == len(vend_names_to_find):
            break

# Find XItemDatabase class and instances
for target_name, target_idx in vend_fname_indices.items():
    print(f"\n  Searching for {target_name} class objects...")
    scan = 0x10000
    found = 0
    while scan < 0x7FFF0000 and found < 5:
        if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
        if region_end <= scan: break
        if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and
            (mbi.Protect & (PAGE_RW | PAGE_RWX | PAGE_WC | 0x02 | 0x20))):
            data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
            if data:
                for i in range(0, len(data) - 0x28, 4):
                    name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                    if name_idx != target_idx: continue
                    name_num = struct.unpack_from('<i', data, i + 0x1C)[0]
                    cls_ptr = struct.unpack_from('<I', data, i + 0x20)[0]
                    if not cls_ptr: continue
                    cls_data = read_mem(hp, cls_ptr + 0x18, 4)
                    if not cls_data: continue
                    cls_name = resolve_fname(struct.unpack_from('<i', cls_data)[0])
                    obj_addr = (mbi.BaseAddress or 0) + i
                    print(f"    {target_name}_{name_num} @ 0x{obj_addr:08X} (class={cls_name})")
                    found += 1
        scan = region_end

kernel32.CloseHandle(hp)
print("\nDone!")
