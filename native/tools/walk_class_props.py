"""Walk the UClass property chain for XWeapon to find ALL property names and offsets.
This traverses UClass -> PropertyLink -> Next -> ... to enumerate every property."""
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

pid = find_pid('BioShockInfinite.exe')
if not pid:
    print("ERROR: Game not running!"); sys.exit(1)

hProcess = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cbNeeded = wt.DWORD()
psapi.EnumProcessModules(hProcess, hMods, ctypes.sizeof(hMods), ctypes.byref(cbNeeded))
base = hMods[0]

RVA_GNames = 0xF9DFEC
OFF_FNameEntry_Flags = 0x08
OFF_FNameEntry_Str = 0x10
OFF_Name = 0x18
OFF_Class = 0x20

gnames = read_u32(hProcess, base + RVA_GNames)
print(f"Base=0x{base:08X}, GNames=0x{gnames:08X}")

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    entry_ptr = read_u32(hProcess, gnames + index * 4)
    if not entry_ptr: return None
    flags = read_u32(hProcess, entry_ptr + OFF_FNameEntry_Flags)
    if flags is None: return None
    str_addr = entry_ptr + OFF_FNameEntry_Str
    if flags & 1:
        data = read_mem(hProcess, str_addr, 512)
        if not data: return None
        try:
            end = data.index(b'\x00\x00')
            if end % 2 == 1: end += 1
            return data[:end].decode('utf-16-le')
        except: return None
    else:
        data = read_mem(hProcess, str_addr, 256)
        if not data: return None
        try:
            end = data.index(b'\x00')
            return data[:end].decode('ascii')
        except: return None

# First find the SpareAmmoCount UProperty (which we know exists at 0x17248294)
# and use it to verify the property chain layout
# UProperty layout:
#   +0x00: vtable
#   +0x18: FName (Index, Number)
#   +0x20: UClass*
#   +0x24: UObject* Outer  (the owning UClass/UStruct)
#   +0x28: UField* Next or UObject fields
#   +0x2C: ArrayDim
#   +0x30: ElementSize
#   +0x5C: Offset (confirmed)

# We need to find the UField::Next offset. Let's check what's at various offsets
# of the SpareAmmoCount UProperty and see if any point to AmmoCount UProperty

SAC_ADDR = 0x17248294
print(f"\n=== Exploring SpareAmmoCount UProperty at 0x{SAC_ADDR:08X} ===")
prop_data = read_mem(hProcess, SAC_ADDR, 128)
if prop_data:
    for off in range(0, 128, 4):
        val = struct.unpack_from('<I', prop_data, off)[0]
        # Check if this points to another UObject (check if it has a valid FName)
        if val > 0x10000000 and val < 0x7FFF0000:
            target_name_idx = read_i32(hProcess, val + OFF_Name)
            if target_name_idx and 0 < target_name_idx < 400000:
                target_name = resolve_fname(target_name_idx)
                if target_name:
                    target_cls_ptr = read_u32(hProcess, val + OFF_Class)
                    target_cls_name = None
                    if target_cls_ptr:
                        tcn_idx = read_i32(hProcess, target_cls_ptr + OFF_Name)
                        target_cls_name = resolve_fname(tcn_idx) if tcn_idx else None
                    print(f"  +0x{off:02X}: ptr -> '{target_name}' (class={target_cls_name}) @ 0x{val:08X}")
                    continue
        print(f"  +0x{off:02X}: 0x{val:08X} ({val})")

# Now let's find the Outer of SpareAmmoCount — this is the UClass that owns it
outer_ptr = read_u32(hProcess, SAC_ADDR + 0x24)
print(f"\n=== Outer UClass at 0x{outer_ptr:08X} ===")
if outer_ptr:
    outer_name_idx = read_i32(hProcess, outer_ptr + OFF_Name)
    outer_name = resolve_fname(outer_name_idx) if outer_name_idx else "?"
    print(f"  Class name: '{outer_name}'")
    
    # Read UClass data to find the PropertyLink / Children
    cls_data = read_mem(hProcess, outer_ptr, 256)
    if cls_data:
        print(f"\n  Exploring UClass '{outer_name}' fields:")
        for off in range(0, 256, 4):
            val = struct.unpack_from('<I', cls_data, off)[0]
            if val > 0x10000000 and val < 0x7FFF0000:
                target_name_idx = read_i32(hProcess, val + OFF_Name)
                if target_name_idx and 0 < target_name_idx < 400000:
                    target_name = resolve_fname(target_name_idx)
                    if target_name:
                        target_cls_ptr = read_u32(hProcess, val + OFF_Class)
                        tcn = None
                        if target_cls_ptr:
                            tcn_idx = read_i32(hProcess, target_cls_ptr + OFF_Name)
                            tcn = resolve_fname(tcn_idx) if tcn_idx else None
                        if tcn and 'Property' in tcn:
                            print(f"  +0x{off:02X}: PROPERTY '{target_name}' ({tcn}) @ 0x{val:08X}")
                        elif target_name:
                            print(f"  +0x{off:02X}: -> '{target_name}' (class={tcn}) @ 0x{val:08X}")

# Let's find which offset in UProperty is the "Next" link by checking the known chain:
# SpareAmmoCount -> AmmoCount -> bIsOverheated (from the FName table area we saw)
print(f"\n=== Finding UField::Next offset ===")
for test_off in [0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48, 0x4C]:
    next_ptr = read_u32(hProcess, SAC_ADDR + test_off)
    if next_ptr and next_ptr > 0x10000000 and next_ptr < 0x7FFF0000:
        next_name_idx = read_i32(hProcess, next_ptr + OFF_Name)
        if next_name_idx and 0 < next_name_idx < 400000:
            next_name = resolve_fname(next_name_idx)
            if next_name:
                print(f"  +0x{test_off:02X}: -> '{next_name}' @ 0x{next_ptr:08X}  ** LIKELY Next **")

# Now walk the FULL property chain from the UClass
# First find PropertyLink on the UClass. It's the head of the linked list of all properties.
# We look for a pointer that leads to a UProperty.
print(f"\n=== Walking property chain from UClass '{outer_name}' ===")
# UStruct::PropertyLink is typically at a specific offset. Let's scan UClass for it.
# We know SpareAmmoCount is a property of this class. Let's find which UClass field
# points to the START of the property chain.

# PropertyLink iterates in REVERSE order (last defined first). Let's find it.
found_next_off = None
for test_off in [0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48, 0x4C]:
    next_ptr = read_u32(hProcess, SAC_ADDR + test_off)
    if next_ptr and next_ptr > 0x10000000 and next_ptr < 0x7FFF0000:
        next_name_idx = read_i32(hProcess, next_ptr + OFF_Name)
        if next_name_idx and 0 < next_name_idx < 400000:
            next_name = resolve_fname(next_name_idx)
            if next_name:
                found_next_off = test_off
                break

if found_next_off:
    print(f"  UField::Next is at +0x{found_next_off:02X}")
    print(f"  Walking chain from SpareAmmoCount...")
    
    # Walk the chain
    cur = SAC_ADDR
    count = 0
    fire_props = []
    ammo_props = []
    all_props = []
    
    while cur and count < 500:
        name_idx = read_i32(hProcess, cur + OFF_Name)
        if not name_idx: break
        name = resolve_fname(name_idx)
        if not name: break
        
        cls_ptr = read_u32(hProcess, cur + OFF_Class)
        cls_name = None
        if cls_ptr:
            cn_idx = read_i32(hProcess, cls_ptr + OFF_Name)
            cls_name = resolve_fname(cn_idx) if cn_idx else None
        
        # Read offset
        offset_val = read_u32(hProcess, cur + 0x5C)
        elem_size = read_u32(hProcess, cur + 0x30)
        arr_dim = read_u32(hProcess, cur + 0x2C)
        
        nl = name.lower()
        interesting = any(k in nl for k in ['fire', 'ammo', 'salt', 'vigor', 'energy',
                                              'damage', 'spread', 'range', 'reload',
                                              'interval', 'rate', 'burst', 'cooldown',
                                              'cost', 'drain', 'consume', 'clip',
                                              'magazine', 'overheat'])
        
        if interesting:
            print(f"  [{count:3d}] {cls_name:20s} '{name}' offset=0x{offset_val:04X} elemSize={elem_size} arrDim={arr_dim}")
            all_props.append((name, cls_name, offset_val, elem_size, arr_dim, cur))
        
        if 'fire' in nl or 'interval' in nl or 'rate' in nl:
            fire_props.append((name, offset_val, elem_size))
        if 'ammo' in nl or 'energy' in nl or 'salt' in nl:
            ammo_props.append((name, offset_val, elem_size))
        
        # Follow Next
        next_ptr = read_u32(hProcess, cur + found_next_off)
        if not next_ptr or next_ptr == cur: break
        cur = next_ptr
        count += 1
    
    print(f"\n  Total properties walked: {count}")
    if fire_props:
        print(f"\n  Fire/rate related:")
        for n, o, s in fire_props:
            print(f"    {n}: offset=0x{o:04X} size={s}")
    if ammo_props:
        print(f"\n  Ammo/energy related:")
        for n, o, s in ammo_props:
            print(f"    {n}: offset=0x{o:04X} size={s}")

kernel32.CloseHandle(hProcess)
