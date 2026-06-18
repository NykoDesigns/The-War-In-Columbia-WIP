"""Find GEngine, GWorld, PlayerController, and LocalPlayer pointers.
These are needed to execute console commands programmatically from our DLL."""
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
base = None
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

print(f"Base=0x{base:08X} Size=0x{base_size:08X}")
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

# Known global pointer RVAs from the .exe (near GNames at 0xF9DFEC)
# Let's scan around it for other globals
print("\n=== Scanning for known global pointers ===")
# GNames is at base+0xF9DFEC. Other UE3 globals are typically nearby.
# Common patterns: GObjects/GObjHash, GEngine, GWorld

# Search for FName indices of key objects
key_fnames = {}
search = ['GameEngine', 'XGameEngine', 'GameViewportClient', 'XGameViewportClient',
          'LocalPlayer', 'XLocalPlayer', 'PlayerController', 'XPlayerController',
          'WorldInfo', 'XWorldInfo', 'Console', 'XConsole',
          'Default__XGameEngine', 'Default__XConsole', 'Default__XPlayerController']
for i in range(100000):
    n = rfn(i)
    if n and n in search:
        key_fnames[n] = i
        print(f"  FName [{i:6d}] {n}")

# Now look for known RVAs of globals in the .data section
# In UE3, GEngine is typically a pointer in the .data section
# Let's look for patterns: a .data section pointer that when dereferenced gives a UObject
# whose FName matches "XGameEngine"

print("\n=== Searching for GEngine pointer in .data section ===")
# The .data section is typically after .rdata. Let's scan the last part of the module
# for pointers that resolve to valid UObjects with engine-related FNames
engine_fname_idx = key_fnames.get('XGameEngine', -1)
if engine_fname_idx < 0:
    engine_fname_idx = key_fnames.get('GameEngine', -1)

# Read .data section - typically in range 0xF00000-0x1000000 for this exe
data_start = 0xF90000  # Near where GNames is
data_end = min(base_size, 0x1250000)
print(f"  Scanning RVA 0x{data_start:08X}-0x{data_end:08X} for engine pointers...")

# Read the data section  
chunk = read_mem(hp, base + data_start, data_end - data_start)
if chunk:
    found_engine = []
    for off in range(0, len(chunk) - 4, 4):
        ptr = struct.unpack_from('<I', chunk, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        # Check if this pointer leads to a UObject with an engine FName
        obj_name_idx = read32(hp, ptr + 0x18)
        if obj_name_idx == engine_fname_idx and engine_fname_idx > 0:
            rva = data_start + off
            cls_ptr = read32(hp, ptr + 0x20)
            cls_name = ""
            if cls_ptr:
                cn = read32(hp, cls_ptr + 0x18)
                cls_name = rfn(cn) or ""
            print(f"  CANDIDATE GEngine at RVA 0x{rva:08X} -> obj@0x{ptr:08X} class={cls_name}")
            found_engine.append((rva, ptr))
    
    # Also look for XConsole
    console_fname_idx = key_fnames.get('XConsole', key_fnames.get('Console', -1))
    if console_fname_idx > 0:
        for off in range(0, len(chunk) - 4, 4):
            ptr = struct.unpack_from('<I', chunk, off)[0]
            if ptr < 0x10000 or ptr > 0x7FFE0000: continue
            obj_name_idx = read32(hp, ptr + 0x18)
            if obj_name_idx == console_fname_idx:
                rva = data_start + off
                print(f"  CANDIDATE Console at RVA 0x{rva:08X} -> obj@0x{ptr:08X}")

# Also find GWorld
print("\n=== Looking for GWorld (XWorldInfo) ===")
world_fname_idx = key_fnames.get('XWorldInfo', key_fnames.get('WorldInfo', -1))
if world_fname_idx > 0 and chunk:
    for off in range(0, len(chunk) - 4, 4):
        ptr = struct.unpack_from('<I', chunk, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        obj_name_idx = read32(hp, ptr + 0x18)
        if obj_name_idx == world_fname_idx:
            rva = data_start + off
            print(f"  CANDIDATE GWorld at RVA 0x{rva:08X} -> obj@0x{ptr:08X}")

kernel32.CloseHandle(hp)
