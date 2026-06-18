"""Find UProperty objects for StandardFireTime, FireTimeAttrib, FractionalVigorEnergyToBurn
and their offsets within the owning objects. Also find weapon instances to modify."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD),
    ]

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

def read_u32(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<I', d)[0] if d and len(d) == 4 else None

def read_i32(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<i', d)[0] if d and len(d) == 4 else None

def read_float(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<f', d)[0] if d and len(d) == 4 else None

pid = find_pid('BioShockInfinite.exe')
if not pid: print("Game not running!"); sys.exit(1)

hp = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cb = wt.DWORD()
psapi.EnumProcessModules(hp, hMods, ctypes.sizeof(hMods), ctypes.byref(cb))
base = hMods[0]

RVA_GNames = 0xF9DFEC
OFF_FNE_Flags = 0x08; OFF_FNE_Str = 0x10
OFF_Name = 0x18; OFF_Class = 0x20

gnames = read_u32(hp, base + RVA_GNames)

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    ep = read_u32(hp, gnames + index * 4)
    if not ep: return None
    flags = read_u32(hp, ep + OFF_FNE_Flags)
    if flags is None: return None
    sa = ep + OFF_FNE_Str
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

# Target FName indices (from previous scan)
targets = {
    'StandardFireTime': 40941,
    'StandardFireDelay': 40940,
    'FireTimeAttrib': 32089,
    'FireMode_0_FireTimeAttrib': 49081,
    'CycleTime': 15442,
    'BurstFireDelay': 26286,
    'ReFireDelay': 20198,
    'FractionalVigorEnergyToBurn': 32305,
    'VigorEnergyRechargeRate': 43255,
    'VigorEnergySizeAttrib': 43258,
    'VigorEnergy': 2133,
}

# Search memory for UProperty objects with these FName indices at +0x18
print(f"Base=0x{base:08X}, GNames=0x{gnames:08X}")
print(f"\n=== Searching for target UProperty objects ===")

mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)

found_props = {}  # name -> list of (addr, class_name, offset, elem_size, outer_name)

for prop_name, fname_idx in targets.items():
    needle = struct.pack('<I', fname_idx)
    results = []
    
    addr = 0
    while addr < 0x7FFF0000:
        if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        rbase = mbi.BaseAddress or 0
        region_end = rbase + mbi.RegionSize
        if region_end <= addr: break
        
        if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
            for chunk_off in range(0, mbi.RegionSize, 0x10000):
                read_addr = rbase + chunk_off
                to_read = min(0x10000, mbi.RegionSize - chunk_off)
                buf = ctypes.create_string_buffer(to_read)
                if kernel32.ReadProcessMemory(hp, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                    data = buf.raw[:bytes_read.value]
                    idx = 0
                    while True:
                        idx = data.find(needle, idx)
                        if idx == -1: break
                        # Check if this looks like UObject.Name at +0x18
                        obj_addr = read_addr + idx - OFF_Name
                        # Verify: Number at +0x1C should be 0, Class at +0x20 should be valid
                        num = read_i32(hp, obj_addr + OFF_Name + 4)
                        cls_ptr = read_u32(hp, obj_addr + OFF_Class)
                        if num == 0 and cls_ptr and cls_ptr > 0x10000000:
                            cn_idx = read_i32(hp, cls_ptr + OFF_Name)
                            cn = resolve_fname(cn_idx) if cn_idx else None
                            if cn and 'Property' in cn:
                                # This is a UProperty! Read its fields
                                offset_val = read_u32(hp, obj_addr + 0x5C)
                                elem_size = read_u32(hp, obj_addr + 0x30)
                                arr_dim = read_u32(hp, obj_addr + 0x2C)
                                # Read Outer (owning class) at +0x14
                                outer_ptr = read_u32(hp, obj_addr + 0x14)
                                outer_name = None
                                if outer_ptr:
                                    on_idx = read_i32(hp, outer_ptr + OFF_Name)
                                    outer_name = resolve_fname(on_idx) if on_idx else None
                                results.append((obj_addr, cn, offset_val, elem_size, arr_dim, outer_name))
                        idx += 1
        addr = region_end
    
    if results:
        found_props[prop_name] = results
        for obj_addr, cn, offset_val, elem_size, arr_dim, outer_name in results:
            print(f"  {prop_name:40s} ({cn:20s}) on '{outer_name}' offset=0x{offset_val:04X} size={elem_size} dim={arr_dim} @ 0x{obj_addr:08X}")
    else:
        print(f"  {prop_name:40s} NOT FOUND")

# Now try to find weapon instances. XWeapon class is at 0x16EE6B20
# Search for UObjects with UClass* pointing to XWeapon
XWEAPON_CLASS = 0x16EE6B20
xw_bytes = struct.pack('<I', XWEAPON_CLASS)

print(f"\n=== Searching for XWeapon instances (class ptr = 0x{XWEAPON_CLASS:08X}) ===")
weapon_instances = []

addr = 0
while addr < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    rbase = mbi.BaseAddress or 0
    region_end = rbase + mbi.RegionSize
    if region_end <= addr: break
    
    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        for chunk_off in range(0, mbi.RegionSize, 0x10000):
            read_addr = rbase + chunk_off
            to_read = min(0x10000, mbi.RegionSize - chunk_off)
            buf = ctypes.create_string_buffer(to_read)
            if kernel32.ReadProcessMemory(hp, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                data = buf.raw[:bytes_read.value]
                idx = 0
                while True:
                    idx = data.find(xw_bytes, idx)
                    if idx == -1: break
                    # Check if this is at +0x20 (UClass* offset)
                    obj_addr = read_addr + idx - OFF_Class
                    name_idx = read_i32(hp, obj_addr + OFF_Name)
                    name_num = read_i32(hp, obj_addr + OFF_Name + 4)
                    if name_idx and 0 < name_idx < 500000 and name_num is not None:
                        name = resolve_fname(name_idx)
                        if name:
                            weapon_instances.append((obj_addr, name, name_num))
                    idx += 1
    addr = region_end

print(f"Found {len(weapon_instances)} potential XWeapon instances:")
shown = set()
for obj_addr, name, num in weapon_instances[:30]:
    key = f"{name}_{num}"
    if key in shown: continue
    shown.add(key)
    # Read some property values at known offsets
    # SpareAmmoCount offset=0x9C38, AmmoCount should be nearby
    spare_ammo = read_i32(hp, obj_addr + 0x9C38)
    ammo_count = read_i32(hp, obj_addr + 0x9C38 + 4)  # next field
    print(f"  '{name}_{num}' @ 0x{obj_addr:08X} SpareAmmo={spare_ammo}")
    
    # If we found StandardFireTime/FireTimeAttrib offset, read those too
    for pn, props in found_props.items():
        if 'fire' in pn.lower() or 'time' in pn.lower():
            for _, _, off, sz, _, on in props:
                if on == 'XWeapon' and sz == 4:
                    val = read_float(hp, obj_addr + off)
                    if val is not None and abs(val) < 10000:
                        print(f"    {pn} (@+0x{off:04X}) = {val:.6f}")

kernel32.CloseHandle(hp)
print("\nDone!")
