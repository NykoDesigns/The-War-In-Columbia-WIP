"""Walk the XWeapon UClass property chain to find exact offsets for AmmoCount,
SpareAmmoCount, MaxAmmoCount, MaxSpareAmmoCount, ClipSize, etc."""
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

def read32(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<I', d)[0] if d else 0

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

# Find XWeapon class
xweapon_idx = -1
for i in range(200000):
    name = resolve_fname(i)
    if name == 'XWeapon':
        xweapon_idx = i
        break

# Find target FName indices
target_props = {}
target_names = ['AmmoCount', 'SpareAmmoCount', 'MaxAmmoCount', 'MaxSpareAmmoCount',
                'ClipSize', 'DefaultClipSize', 'AmmoPerClip', 'MagazineSize',
                'FireInterval', 'StandardFireDelay', 'StandardFireTime',
                'VigorEnergy', 'FractionalVigorEnergyToBurn', 'ShotCost',
                'Ammo', 'MaxAmmo', 'InitialAmmo', 'StartingAmmo',
                'CurrentAmmo', 'RemainingAmmo', 'TotalAmmo']
print("Searching for FName indices...")
for i in range(300000):
    name = resolve_fname(i)
    if name and name in target_names:
        target_props[name] = i
        print(f"  FName[{i}] = '{name}'")

# Find the XWeapon UClass
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD),
    ]

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
mbi = MEMORY_BASIC_INFORMATION()

xweapon_class = None
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan: break
    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x28, 4):
                if struct.unpack_from('<i', data, i + 0x18)[0] != xweapon_idx: continue
                if struct.unpack_from('<i', data, i + 0x1C)[0] != 0: continue
                cls_ptr = struct.unpack_from('<I', data, i + 0x20)[0]
                if not cls_ptr: continue
                cls_data = read_mem(hp, cls_ptr + 0x18, 4)
                if not cls_data: continue
                if resolve_fname(struct.unpack_from('<i', cls_data)[0]) == 'Class':
                    xweapon_class = (mbi.BaseAddress or 0) + i
                    break
        if xweapon_class: break
    scan = region_end

print(f"\nXWeapon UClass @ 0x{xweapon_class:08X}")

# Walk the property chain
# UClass has a PropertyLink or Children pointer
# UStruct::Children at +0x30 (first UField child)
# UField::Next at +0x28
# UProperty: FName at +0x18, Offset at +0x5C, PropertySize at +0x3C

# Try different offsets for UStruct::Children
for children_off in [0x30, 0x34, 0x38, 0x2C]:
    first_child = read32(hp, xweapon_class + children_off)
    if first_child and first_child > 0x10000 and first_child < 0xFFFF0000:
        child_name_idx = read32(hp, first_child + 0x18)
        child_name = resolve_fname(child_name_idx)
        if child_name:
            print(f"\n  Children offset +0x{children_off:02X} -> first child '{child_name}' @ 0x{first_child:08X}")

# Walk from UStruct::Children at +0x30 
print("\n=== Walking XWeapon property chain (Children at +0x30) ===")
prop = read32(hp, xweapon_class + 0x30)
visited = set()
count = 0
ammo_props = {}
while prop and prop > 0x10000 and prop < 0xFFFF0000 and prop not in visited and count < 500:
    visited.add(prop)
    count += 1
    name_idx = read32(hp, prop + 0x18)
    name = resolve_fname(name_idx)
    offset_val = read32(hp, prop + 0x5C)
    prop_size = read32(hp, prop + 0x3C)
    
    # Get property class
    cls = read32(hp, prop + 0x20)
    cls_name = ''
    if cls:
        cls_name_idx = read32(hp, cls + 0x18)
        cls_name = resolve_fname(cls_name_idx) or ''
    
    if name and ('Ammo' in name or 'Clip' in name or 'Magazine' in name or 'Spare' in name 
                 or 'Fire' in name or 'Salt' in name or 'Vigor' in name or 'Energy' in name
                 or 'Cost' in name or 'Max' in name or 'Reserve' in name
                 or name in target_names):
        print(f"  {name:40s} offset=+0x{offset_val:04X} size={prop_size:3d} class={cls_name}")
        ammo_props[name] = offset_val
    
    # Next property
    prop = read32(hp, prop + 0x28)

# Also walk the PropertyLink (usually at +0x34 for UStruct)
print("\n=== Walking via PropertyLink (at +0x34) ===")
# In some UE3 builds, PropertyLink is at a different offset within UStruct
# UProperty has a PropertyLinkNext at a specific offset too
# Let's try +0x34 and +0x38
for link_off_name, link_off in [("0x34", 0x34), ("0x38", 0x38)]:
    prop = read32(hp, xweapon_class + link_off)
    visited2 = set()
    count2 = 0
    while prop and prop > 0x10000 and prop < 0xFFFF0000 and prop not in visited2 and count2 < 500:
        visited2.add(prop)
        count2 += 1
        name_idx = read32(hp, prop + 0x18)
        name = resolve_fname(name_idx)
        offset_val = read32(hp, prop + 0x5C)
        
        if name and ('Ammo' in name or 'Clip' in name or 'Spare' in name or 'Fire' in name 
                     or 'Max' in name or name in target_names):
            print(f"  [{link_off_name}] {name:40s} offset=+0x{offset_val:04X}")
        
        # Try PropertyLinkNext at +0x44 (common in UE3)
        prop = read32(hp, prop + 0x44)
    if count2 > 0:
        print(f"  (walked {count2} properties via +{link_off_name})")

# Now read the actual values at discovered offsets on a MachineGun archetype
if ammo_props:
    print("\n=== Values on MachineGunBase at discovered offsets ===")
    # Find MachineGunBase address
    scan = 0x10000
    mg_addr = None
    while scan < 0x7FFF0000 and not mg_addr:
        if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
        region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
        if region_end <= scan: break
        if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and (mbi.Protect & 0x6C):
            data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
            if data:
                for i in range(0, len(data) - 0x800, 4):
                    if struct.unpack_from('<I', data, i + 0x20)[0] != xweapon_class: continue
                    name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                    name = resolve_fname(name_idx)
                    if name == 'MachineGunBase':
                        mg_addr = (mbi.BaseAddress or 0) + i
                        break
            if mg_addr: break
        scan = region_end
    
    if mg_addr:
        mg_data = read_mem(hp, mg_addr, 0xA000)
        if mg_data:
            for prop_name, off in sorted(ammo_props.items(), key=lambda x: x[1]):
                if off < len(mg_data) - 4:
                    vi = struct.unpack_from('<i', mg_data, off)[0]
                    vf = struct.unpack_from('<f', mg_data, off)[0]
                    vf_s = f"{vf:.4f}" if vf == vf and abs(vf) < 100000 else "big/nan"
                    print(f"  {prop_name:40s} +0x{off:04X}: int={vi:8d}  float={vf_s}")

kernel32.CloseHandle(hp)
print("\nDone!")
