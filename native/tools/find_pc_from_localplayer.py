"""Explore XLocalPlayer to find PlayerController and its ConsoleCommand function."""
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
if not pid: print("Game not running!"); sys.exit(1)
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
    if not addr or addr < 0x10000: return "NULL"
    ni = read32(hp, addr + 0x18)
    n = rfn(ni)
    return n if n else f"idx={ni}"

def obj_class_name(addr):
    if not addr or addr < 0x10000: return "NULL"
    cls = read32(hp, addr + 0x20)
    if not cls or cls < 0x10000: return "?"
    ni = read32(hp, cls + 0x18)
    return rfn(ni) or f"idx={ni}"

# XLocalPlayer found at GEngine+0x1B0 TArray
engine_ptr = read32(hp, base + 0x00FAA024)
tarray_ptr = read32(hp, engine_ptr + 0x1B0)
local_player = read32(hp, tarray_ptr)  # First element
print(f"XLocalPlayer @ 0x{local_player:08X}")
print(f"  name={obj_name(local_player)} class={obj_class_name(local_player)}")

# Explore LocalPlayer for PlayerController, ViewportClient, Console
print(f"\n=== XLocalPlayer object data ===")
lp_data = read_mem(hp, local_player, 0x200)
if lp_data:
    # In UE3, ULocalPlayer typically has:
    # +0x28: (after UObject header) some base class data
    # PlayerController is usually in the Player base class
    # Let's scan for any UObject pointers with interesting names
    for off in range(0x28, 0x200, 4):
        ptr = struct.unpack_from('<I', lp_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        # Quick check: is this a valid UObject?
        name = obj_name(ptr)
        cls = obj_class_name(ptr)
        if name == "NULL" or cls == "NULL": continue
        # Filter for interesting objects
        if any(x in name for x in ['Controller', 'Player', 'Pawn', 'Viewport', 'Console', 'Camera', 'HUD']):
            print(f"  +0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
        elif any(x in cls for x in ['Controller', 'Player', 'Pawn', 'Viewport', 'Console']):
            print(f"  +0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

# Also check the GameViewportClient for Console and LocalPlayer refs
viewport_ptr = read32(hp, engine_ptr + 0x1BC)
print(f"\n=== GameViewportClient @ 0x{viewport_ptr:08X} ===")
print(f"  name={obj_name(viewport_ptr)} class={obj_class_name(viewport_ptr)}")
vp_data = read_mem(hp, viewport_ptr, 0x300)
if vp_data:
    for off in range(0x28, 0x300, 4):
        ptr = struct.unpack_from('<I', vp_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        name = obj_name(ptr)
        cls = obj_class_name(ptr)
        if name == "NULL" or cls == "NULL": continue
        if any(x in name for x in ['Console', 'Player', 'Controller']) or any(x in cls for x in ['Console', 'Player', 'XConsole']):
            print(f"  +0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

kernel32.CloseHandle(hp)
