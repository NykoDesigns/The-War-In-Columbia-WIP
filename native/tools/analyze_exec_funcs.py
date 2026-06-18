"""Analyze the ConsoleCommand and ServerCauseEvent exec functions
to find the actual C++ implementation we can call from our DLL."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32

def find_pid(name):
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for l in out.strip().split('\n'):
        if name.lower() in l.lower(): return int(l.strip().split(',')[1].strip('"'))
    return None

def read_mem(hp, a, s):
    b = ctypes.create_string_buffer(s); br = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(hp, ctypes.c_void_p(a), b, s, ctypes.byref(br)): return b.raw[:br.value]
    return None

def read32(hp, a):
    d = read_mem(hp, a, 4)
    return struct.unpack('<I', d)[0] if d else 0

pid = find_pid('BioShockInfinite.exe')
if not pid: sys.exit(1)
hp = kernel32.OpenProcess(0x1F0FFF, False, pid)

psapi = ctypes.windll.psapi
hMods = (ctypes.c_uint32 * 1024)()
cbNeeded = wt.DWORD()
psapi.EnumProcessModulesEx(hp, ctypes.byref(hMods), ctypes.sizeof(hMods), ctypes.byref(cbNeeded), 0x01)
base = hMods[0]
base_size = 0
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value:
        base = mod
        class MODULEINFO(ctypes.Structure):
            _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD), ("EntryPoint", ctypes.c_void_p)]
        mi_info = MODULEINFO()
        psapi.GetModuleInformation(hp, ctypes.c_void_p(mod), ctypes.byref(mi_info), ctypes.sizeof(mi_info))
        base_size = mi_info.SizeOfImage
        break

gn_ptr = read32(hp, base + 0xF9DFEC)

def rfn(i):
    if i < 0 or i > 400000: return None
    ep = read32(hp, gn_ptr + i * 4)
    if not ep: return None
    fl = read32(hp, ep + 8)
    if fl & 1:
        d = read_mem(hp, ep + 0x10, 512)
        if not d: return None
        try: e = d.index(b'\x00\x00'); e += (e%2); return d[:e].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, ep + 0x10, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

def obj_name(addr):
    if not addr or addr < 0x10000: return None
    ni = read32(hp, addr + 0x18)
    return rfn(ni)

def obj_class_name(addr):
    if not addr or addr < 0x10000: return None
    cls = read32(hp, addr + 0x20)
    if not cls or cls < 0x10000: return None
    ni = read32(hp, cls + 0x18)
    return rfn(ni)

# Examine the UFunction objects to understand their parameter layout
print("=== ConsoleCommand UFunction @ 0x16824E0C ===")
cc_func = 0x16824E0C
cc_data = read_mem(hp, cc_func, 0x100)
if cc_data:
    # UFunction layout in UE3:
    # UStruct fields first: SuperStruct, Children, PropertySize, etc.
    # Then UFunction-specific: iNative, RepOffset, FunctionFlags, NativeIndex, etc.
    # Key fields:
    # +0x38: Children (first property/param)
    # +0x48: PropertySize (total params size)  
    # +0x88: FunctionFlags
    # +0x8C: NativeFunc pointer
    
    children = struct.unpack_from('<I', cc_data, 0x38)[0]
    prop_size = struct.unpack_from('<H', cc_data, 0x48)[0]
    func_flags = struct.unpack_from('<I', cc_data, 0x88)[0]
    native_ptr = struct.unpack_from('<I', cc_data, 0x8C)[0]
    print(f"  Children: 0x{children:08X}")
    print(f"  PropertySize: {prop_size}")
    print(f"  FunctionFlags: 0x{func_flags:08X}")
    print(f"  NativeFunc: VA 0x{native_ptr:08X}")
    
    # Walk parameters (Children chain)
    child = children
    idx = 0
    while child and child > 0x10000 and idx < 10:
        cn = obj_name(child)
        cc = obj_class_name(child)
        # Read UProperty offset
        prop_offset = read32(hp, child + 0x48)
        prop_size_p = read32(hp, child + 0x4C)
        prop_flags = read32(hp, child + 0x50)
        print(f"  Param[{idx}]: {cn} ({cc}) offset=0x{prop_offset:X} size={prop_size_p} flags=0x{prop_flags:08X}")
        child = read32(hp, child + 0x28)  # Next
        idx += 1

print(f"\n=== ServerCauseEvent UFunction @ 0x168322BC ===")
sce_func = 0x168322BC
sce_data = read_mem(hp, sce_func, 0x100)
if sce_data:
    children = struct.unpack_from('<I', sce_data, 0x38)[0]
    prop_size = struct.unpack_from('<H', sce_data, 0x48)[0]
    func_flags = struct.unpack_from('<I', sce_data, 0x88)[0]
    native_ptr = struct.unpack_from('<I', sce_data, 0x8C)[0]
    print(f"  Children: 0x{children:08X}")
    print(f"  PropertySize: {prop_size}")
    print(f"  FunctionFlags: 0x{func_flags:08X}")
    print(f"  NativeFunc: VA 0x{native_ptr:08X}")
    
    child = children
    idx = 0
    while child and child > 0x10000 and idx < 10:
        cn = obj_name(child)
        cc = obj_class_name(child)
        prop_offset = read32(hp, child + 0x48)
        prop_size_p = read32(hp, child + 0x4C)
        prop_flags = read32(hp, child + 0x50)
        print(f"  Param[{idx}]: {cn} ({cc}) offset=0x{prop_offset:X} size={prop_size_p} flags=0x{prop_flags:08X}")
        child = read32(hp, child + 0x28)
        idx += 1

# Now examine the exec function code at VA 0x00536070 (ConsoleCommand)
# to find the internal C++ implementation
print(f"\n=== execConsoleCommand code at VA 0x00536070 ===")
code = read_mem(hp, 0x00536070, 256)
if code:
    # Look for CALL instructions to find the actual implementation
    for i in range(len(code) - 5):
        if code[i] == 0xE8:
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = 0x00536070 + i + 5 + rel
            rva = target - base
            print(f"  +0x{i:04X}: CALL -> VA 0x{target:08X} (RVA 0x{rva:08X})")
    print(f"  First 64 bytes: {code[:64].hex()}")

# Examine execServerCauseEvent at VA 0x004CFD10
print(f"\n=== execServerCauseEvent code at VA 0x004CFD10 ===")
code = read_mem(hp, 0x004CFD10, 256)
if code:
    for i in range(len(code) - 5):
        if code[i] == 0xE8:
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = 0x004CFD10 + i + 5 + rel
            rva = target - base
            print(f"  +0x{i:04X}: CALL -> VA 0x{target:08X} (RVA 0x{rva:08X})")
    print(f"  First 64 bytes: {code[:64].hex()}")

# Find ProcessEvent vtable index
# Read the PlayerController vtable  
print(f"\n=== PlayerController vtable @ 0x011B2AC0 ===")
vtable = read_mem(hp, 0x011B2AC0, 0x400)  # 256 entries * 4 bytes
if vtable:
    # Look for vtable entries that match known function patterns
    # ProcessEvent in UE3 is typically a large function
    print("  First 80 vtable entries:")
    for i in range(80):
        vfunc = struct.unpack_from('<I', vtable, i * 4)[0]
        rva = vfunc - base if vfunc >= base else 0
        # Check if this could be ProcessEvent by looking at the function size
        if rva > 0 and rva < base_size:
            print(f"  [{i:3d}] VA 0x{vfunc:08X} (RVA 0x{rva:08X})")

kernel32.CloseHandle(hp)
