"""Find the actual XConsole instance (not class) and examine its command processing fields.
Also look for the Exec virtual function on PlayerController."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF

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
hp = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)

psapi = ctypes.windll.psapi
hMods = (ctypes.c_uint32 * 1024)()
cbNeeded = wt.DWORD()
psapi.EnumProcessModulesEx(hp, ctypes.byref(hMods), ctypes.sizeof(hMods), ctypes.byref(cbNeeded), 0x01)
base = hMods[0]
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value: base = mod; break

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

# The Console should be reachable from GameViewportClient
# GEngine -> GameViewportClient -> Console
engine_ptr = read32(hp, base + 0x00FAA024)
viewport = read32(hp, engine_ptr + 0x1BC)  # XGameViewportClient
print(f"GameViewportClient @ 0x{viewport:08X}")

# Scan ViewportClient for Console reference
vp_data = read_mem(hp, viewport, 0x400)
if vp_data:
    # In UE3, UGameViewportClient::ViewportConsole is typically at some offset
    # Let's scan for XConsole instances
    for off in range(0x28, 0x400, 4):
        ptr = struct.unpack_from('<I', vp_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        cls = obj_class_name(ptr)
        name = obj_name(ptr)
        if cls and 'Console' in cls:
            print(f"  Viewport+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
            # Found it! Explore the console
            console_data = read_mem(hp, ptr, 0x200)
            if console_data:
                print(f"\n  === Console @ 0x{ptr:08X} ===")
                # Look for FString fields (TypedStr, etc.)
                # FString in UE3 is: [TCHAR* Data, int Count, int Max]
                for coff in range(0x28, 0x200, 4):
                    data_ptr = struct.unpack_from('<I', console_data, coff)[0]
                    count = struct.unpack_from('<i', console_data, coff + 4)[0]
                    max_val = struct.unpack_from('<i', console_data, coff + 8)[0]
                    if 0 < count < 1000 and count <= max_val < 2000 and data_ptr > 0x10000:
                        # Try to read as wide string
                        ws = read_mem(hp, data_ptr, min(count * 2, 512))
                        if ws:
                            try:
                                s = ws.decode('utf-16-le').rstrip('\x00')
                                if s and len(s) > 0 and all(32 <= ord(c) < 127 or c == '\x00' for c in s):
                                    print(f"    Console+0x{coff:04X}: FString[{count}/{max_val}] = \"{s[:60]}\"")
                            except:
                                pass

# Also: look for UFunction objects named "ConsoleCommand" or "ServerCauseEvent"
# These would be in the PlayerController or Actor class hierarchy
print(f"\n=== Searching for UFunction 'ConsoleCommand' ===")
# Walk the PlayerController's class hierarchy for UFunctions
tarray_ptr = read32(hp, engine_ptr + 0x1B0)
local_player = read32(hp, tarray_ptr)
pc = read32(hp, local_player + 0x2C)
pc_class = read32(hp, pc + 0x20)
print(f"PC class: {obj_name(pc_class)} @ 0x{pc_class:08X}")

# Walk class hierarchy: Children at +0x38, Next at +0x28
# Also check SuperClass
current_class = pc_class
depth = 0
while current_class and current_class > 0x10000 and depth < 10:
    cls_name = obj_name(current_class)
    print(f"\n  Class: {cls_name} @ 0x{current_class:08X}")
    
    # Walk children (UField chain: Functions, Properties, etc.)
    child = read32(hp, current_class + 0x38)
    func_count = 0
    while child and child > 0x10000 and func_count < 500:
        child_cls = obj_class_name(child)
        child_name = obj_name(child)
        if child_cls == 'Function':
            if child_name and any(k in child_name for k in ['ConsoleCommand', 'CauseEvent', 
                    'ServerCauseEvent', 'Exec', 'AddInventory', 'GiveWeapon']):
                print(f"    UFunction: {child_name} @ 0x{child:08X}")
                # Read the function's native pointer (UFunction::Func at +0x88 or similar)
                # In UE3, UFunction has NativeFunc pointer
                for foff in [0x80, 0x84, 0x88, 0x8C, 0x90]:
                    fptr = read32(hp, child + foff)
                    if fptr > base and fptr < base + 0x1250000:
                        rva = fptr - base
                        print(f"      +0x{foff:02X} -> native func? VA 0x{fptr:08X} (RVA 0x{rva:08X})")
        func_count += 1
        child = read32(hp, child + 0x28)  # UField::Next
    
    # Go to super class
    super_class = read32(hp, current_class + 0x30)  # UClass::SuperClass at +0x30 in UE3
    if super_class == current_class: break
    current_class = super_class
    depth += 1

kernel32.CloseHandle(hp)
