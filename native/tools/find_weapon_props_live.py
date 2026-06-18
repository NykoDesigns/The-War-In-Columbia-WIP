"""Find weapon/vigor property values in the running BioShock Infinite process.

Strategy:
1. Read GNames table to resolve FName indices for property names
2. Search memory for UProperty objects (they have FName at +0x18)
3. Find the property Offset field to know where values live in weapon objects
4. Search for weapon objects and read/modify their property values
"""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
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

def read_mem(hProcess, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(addr), buf, size, ctypes.byref(br)):
        return buf.raw[:br.value]
    return None

def read_u32(hProcess, addr):
    d = read_mem(hProcess, addr, 4)
    return struct.unpack('<I', d)[0] if d and len(d) == 4 else None

def read_i32(hProcess, addr):
    d = read_mem(hProcess, addr, 4)
    return struct.unpack('<i', d)[0] if d and len(d) == 4 else None

def read_float(hProcess, addr):
    d = read_mem(hProcess, addr, 4)
    return struct.unpack('<f', d)[0] if d and len(d) == 4 else None

def read_ptr(hProcess, addr):
    return read_u32(hProcess, addr)

pid = find_pid('BioShockInfinite.exe')
if not pid:
    print("ERROR: Game not running!"); sys.exit(1)
print(f"Game PID: {pid}")

hProcess = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not hProcess:
    print("ERROR: Cannot open process"); sys.exit(1)

# Find module base
import ctypes.wintypes
psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cbNeeded = wt.DWORD()
psapi.EnumProcessModules(hProcess, hMods, ctypes.sizeof(hMods), ctypes.byref(cbNeeded))
base = hMods[0]  # First module = exe
print(f"Module base: 0x{base:08X}")

# Known RVAs
RVA_GNames = 0xF9DFEC
OFF_FNameEntry_Flags = 0x08
OFF_FNameEntry_Str = 0x10

# Read GNames pointer
gnames_ptr_addr = base + RVA_GNames
gnames = read_ptr(hProcess, gnames_ptr_addr)
print(f"GNames table: 0x{gnames:08X}" if gnames else "ERROR: Cannot read GNames")

def resolve_fname(index):
    """Resolve an FName index to a string."""
    if index < 0 or index > 0x400000:
        return None
    entry_ptr = read_ptr(hProcess, gnames + index * 4)
    if not entry_ptr:
        return None
    flags = read_u32(hProcess, entry_ptr + OFF_FNameEntry_Flags)
    if flags is None:
        return None
    str_addr = entry_ptr + OFF_FNameEntry_Str
    if flags & 1:  # wide
        data = read_mem(hProcess, str_addr, 512)
        if not data: return None
        try:
            end = data.index(b'\x00\x00')
            if end % 2 == 1: end += 1
            return data[:end].decode('utf-16-le')
        except:
            return None
    else:
        data = read_mem(hProcess, str_addr, 256)
        if not data: return None
        try:
            end = data.index(b'\x00')
            return data[:end].decode('ascii')
        except:
            return None

# Find FName indices for our target strings
print("\n=== Resolving FName indices ===")
target_names = [
    'FireInterval', 'SpareAmmoCount', 'AmmoCount', 'Spread',
    'InstantHitDamage', 'WeaponRange', 'EquipTime', 'PutDownTime',
    'MachineGun', 'Repeater', 'Carbine', 'Pistol', 'Shotgun',
    'VigorEnergy', 'XWeapon', 'XItem', 'Weapon',
    'FloatProperty', 'IntProperty', 'ArrayProperty',
    'bIsOverheated', 'WeaponEquipState',
    'HealthBatteryEnergy', 'MaxHealthBatteryEnergy',
]

fname_indices = {}
# Scan GNames table (up to 200000 entries)
print("Scanning GNames table...")
for i in range(200000):
    name = resolve_fname(i)
    if name and name in target_names:
        fname_indices[name] = i
        print(f"  FName[{i}] = '{name}'")
        if len(fname_indices) == len(target_names):
            break

print(f"\nFound {len(fname_indices)}/{len(target_names)} FName indices")

# Now search memory for UObject instances that have specific FNames at +0x18
# UObject layout: vtable(+0), ..., FName.Index(+0x18), FName.Number(+0x1C), UClass*(+0x20)

OFF_Name = 0x18
OFF_Class = 0x20

# For each found weapon-related FName, search for UObjects with that name
print("\n=== Searching for weapon/vigor objects in memory ===")
mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)

interesting_objects = {}  # fname -> list of (addr, class_name)

# Search for objects matching our FName indices
targets_to_find = {k: v for k, v in fname_indices.items() 
                   if k in ['FireInterval', 'SpareAmmoCount', 'AmmoCount', 
                            'WeaponEquipState', 'Spread', 'InstantHitDamage',
                            'WeaponRange', 'VigorEnergy',
                            'HealthBatteryEnergy', 'MaxHealthBatteryEnergy']}

if 'FireInterval' in fname_indices:
    fi_idx = fname_indices['FireInterval']
    fi_bytes = struct.pack('<I', fi_idx)
    
    print(f"\nSearching for FName index {fi_idx} ('FireInterval') at UObject +0x18...")
    addr = 0
    fi_objects = []
    
    while addr < 0x7FFF0000:
        if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        rbase = mbi.BaseAddress or 0
        region_end = rbase + mbi.RegionSize
        if region_end <= addr: break
        
        if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
            for offset in range(0, mbi.RegionSize, 0x10000):
                read_addr = rbase + offset
                to_read = min(0x10000, mbi.RegionSize - offset)
                buf = ctypes.create_string_buffer(to_read)
                if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                    data = buf.raw[:bytes_read.value]
                    idx = 0
                    while True:
                        idx = data.find(fi_bytes, idx)
                        if idx == -1: break
                        obj_addr = read_addr + idx - OFF_Name
                        # Verify: check if +0x1C (Number) is 0, and +0x20 (Class*) is a valid pointer
                        num = read_i32(hProcess, obj_addr + OFF_Name + 4)
                        cls_ptr = read_ptr(hProcess, obj_addr + OFF_Class)
                        vtbl = read_ptr(hProcess, obj_addr)
                        
                        if num is not None and num == 0 and cls_ptr and vtbl:
                            # Looks like a UObject! Resolve its class name
                            cls_name_idx = read_i32(hProcess, cls_ptr + OFF_Name)
                            cls_name = resolve_fname(cls_name_idx) if cls_name_idx else None
                            
                            if cls_name and 'Property' in cls_name:
                                # This is a UProperty definition for FireInterval
                                # Read fields around it to find the Offset
                                print(f"\n  Found UProperty '{cls_name}' named 'FireInterval' at 0x{obj_addr:08X}")
                                # Dump surrounding data to find the Offset field
                                prop_data = read_mem(hProcess, obj_addr, 128)
                                if prop_data:
                                    print(f"    Raw: {' '.join(f'{b:02X}' for b in prop_data[:64])}")
                                    print(f"         {' '.join(f'{b:02X}' for b in prop_data[64:128])}")
                                    # Try to extract useful fields
                                    # UProperty layout after UField (approx):
                                    # +0x30: UField* Next
                                    # +0x34: ???
                                    # +0x38: ArrayDim
                                    # +0x3C: ElementSize  
                                    # +0x40: PropertyFlags (8 bytes)
                                    # +0x48: RepOffset
                                    # +0x4A: RepIndex
                                    # +0x4C: Category FName
                                    # +0x54: RepNotifyFunc FName
                                    # +0x5C: Offset
                                    for test_off in [0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 
                                                     0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C, 0x60, 0x64, 0x68, 0x6C, 0x70]:
                                        val = struct.unpack_from('<I', prop_data, test_off)[0] if test_off + 4 <= len(prop_data) else 0
                                        fval = struct.unpack_from('<f', prop_data, test_off)[0] if test_off + 4 <= len(prop_data) else 0
                                        print(f"    +0x{test_off:02X}: 0x{val:08X} ({val:10d}) float={fval:.6f}")
                                fi_objects.append((obj_addr, cls_name))
                        idx += 1
        addr = region_end
    
    print(f"\n  Total FireInterval-named objects: {len(fi_objects)}")

# Also search for the string "SpareAmmoCount" as a property
if 'SpareAmmoCount' in fname_indices:
    sa_idx = fname_indices['SpareAmmoCount']
    sa_bytes = struct.pack('<I', sa_idx)
    print(f"\nSearching for 'SpareAmmoCount' UProperty (FName idx={sa_idx})...")
    addr = 0
    while addr < 0x7FFF0000:
        if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        rbase = mbi.BaseAddress or 0
        region_end = rbase + mbi.RegionSize
        if region_end <= addr: break
        
        if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
            for offset in range(0, mbi.RegionSize, 0x10000):
                read_addr = rbase + offset
                to_read = min(0x10000, mbi.RegionSize - offset)
                buf = ctypes.create_string_buffer(to_read)
                if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                    data = buf.raw[:bytes_read.value]
                    idx = 0
                    while True:
                        idx = data.find(sa_bytes, idx)
                        if idx == -1: break
                        obj_addr = read_addr + idx - OFF_Name
                        num = read_i32(hProcess, obj_addr + OFF_Name + 4)
                        cls_ptr = read_ptr(hProcess, obj_addr + OFF_Class)
                        if num == 0 and cls_ptr:
                            cls_name_idx = read_i32(hProcess, cls_ptr + OFF_Name)
                            cls_name = resolve_fname(cls_name_idx) if cls_name_idx else None
                            if cls_name and 'Property' in cls_name:
                                print(f"  Found UProperty '{cls_name}' named 'SpareAmmoCount' at 0x{obj_addr:08X}")
                                prop_data = read_mem(hProcess, obj_addr, 128)
                                if prop_data:
                                    for test_off in [0x2C, 0x30, 0x34, 0x38, 0x3C, 0x44, 0x4C, 0x54, 0x5C, 0x64, 0x6C]:
                                        val = struct.unpack_from('<I', prop_data, test_off)[0] if test_off + 4 <= len(prop_data) else 0
                                        print(f"    +0x{test_off:02X}: 0x{val:08X} ({val})")
                        idx += 1
        addr = region_end

# Search for VigorEnergy / HealthBatteryEnergy property objects too
for pname in ['VigorEnergy', 'HealthBatteryEnergy']:
    if pname in fname_indices:
        pidx = fname_indices[pname]
        pb = struct.pack('<I', pidx)
        print(f"\nSearching for '{pname}' UProperty (FName idx={pidx})...")
        addr = 0
        found = 0
        while addr < 0x7FFF0000 and found < 5:
            if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
                break
            rbase = mbi.BaseAddress or 0
            region_end = rbase + mbi.RegionSize
            if region_end <= addr: break
            
            if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
                for offset in range(0, mbi.RegionSize, 0x10000):
                    read_addr = rbase + offset
                    to_read = min(0x10000, mbi.RegionSize - offset)
                    buf = ctypes.create_string_buffer(to_read)
                    if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                        data = buf.raw[:bytes_read.value]
                        idx2 = 0
                        while True:
                            idx2 = data.find(pb, idx2)
                            if idx2 == -1: break
                            obj_addr = read_addr + idx2 - OFF_Name
                            num = read_i32(hProcess, obj_addr + OFF_Name + 4)
                            cls_ptr = read_ptr(hProcess, obj_addr + OFF_Class)
                            if num == 0 and cls_ptr:
                                cls_name_idx = read_i32(hProcess, cls_ptr + OFF_Name)
                                cls_name = resolve_fname(cls_name_idx) if cls_name_idx else None
                                if cls_name and 'Property' in cls_name:
                                    print(f"  Found UProperty '{cls_name}' named '{pname}' at 0x{obj_addr:08X}")
                                    prop_data = read_mem(hProcess, obj_addr, 128)
                                    if prop_data:
                                        for test_off in [0x2C, 0x30, 0x34, 0x38, 0x3C, 0x44, 0x4C, 0x54, 0x5C, 0x64, 0x6C]:
                                            val = struct.unpack_from('<I', prop_data, test_off)[0]
                                            print(f"    +0x{test_off:02X}: 0x{val:08X} ({val})")
                                    found += 1
                            idx2 += 1
            addr = region_end

kernel32.CloseHandle(hProcess)
print("\nDone!")
