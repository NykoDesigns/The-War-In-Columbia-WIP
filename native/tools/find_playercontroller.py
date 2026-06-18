"""Traverse GEngine -> GamePlayers -> LocalPlayer -> PlayerController
to find the player controller and its vtable for ConsoleCommand."""
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

def readf(hp, a):
    d = read_mem(hp, a, 4)
    return struct.unpack('<f', d)[0] if d else 0.0

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
    return rfn(ni) or f"idx={ni}"

def obj_class(addr):
    if not addr or addr < 0x10000: return "NULL"
    cls = read32(hp, addr + 0x20)
    if not cls or cls < 0x10000: return "?"
    ni = read32(hp, cls + 0x18)
    return rfn(ni) or f"idx={ni}"

# GEngine
RVA_GENGINE = 0x00FAA024
engine_ptr = read32(hp, base + RVA_GENGINE)
print(f"GEngine = 0x{engine_ptr:08X} ({obj_name(engine_ptr)}, class={obj_class(engine_ptr)})")

# Dump GEngine's properties to find GamePlayers TArray
# In UE3, UGameEngine typically has:
# - GamePlayers: TArray<ULocalPlayer*> 
# Let's scan through the engine object for pointers to LocalPlayer objects
print(f"\n=== Exploring GEngine object (first 0x200 bytes after UObject header) ===")
engine_data = read_mem(hp, engine_ptr, 0x400)
if engine_data:
    # Look for TArray patterns: [Data, Count, Max] where Count is small (1 for single player)
    for off in range(0x28, len(engine_data) - 12, 4):
        data_ptr = struct.unpack_from('<I', engine_data, off)[0]
        count = struct.unpack_from('<i', engine_data, off + 4)[0]
        max_val = struct.unpack_from('<i', engine_data, off + 8)[0]
        # TArray<ULocalPlayer*> should have count=1, max>=1
        if count == 1 and 1 <= max_val <= 16 and data_ptr > 0x10000 and data_ptr < 0x7FFE0000:
            # Read the first element
            elem = read32(hp, data_ptr)
            if elem and elem > 0x10000 and elem < 0x7FFE0000:
                elem_name = obj_name(elem)
                elem_class = obj_class(elem)
                if 'Player' in elem_name or 'Player' in elem_class or 'Local' in elem_name:
                    print(f"  +0x{off:04X}: TArray ptr=0x{data_ptr:08X} count={count} max={max_val}")
                    print(f"    [0] = 0x{elem:08X} name={elem_name} class={elem_class}")

# Let's also try to find the ViewportClient (which has LocalPlayers)
print(f"\n=== Scanning for ViewportClient and LocalPlayer ===")
# Find all objects in engine data that might be ViewportClient or have Player references
for off in range(0x28, min(len(engine_data), 0x400) - 4, 4):
    ptr = struct.unpack_from('<I', engine_data, off)[0]
    if ptr < 0x10000 or ptr > 0x7FFE0000: continue
    name = obj_name(ptr)
    if name and ('Viewport' in name or 'Player' in name or 'Console' in name or 'Pawn' in name):
        cls = obj_class(ptr)
        print(f"  GEngine+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

# Now explore the Console object
RVA_CONSOLE = 0x00FFD5F4
console_ptr = read32(hp, base + RVA_CONSOLE)
print(f"\n=== Console object @ 0x{console_ptr:08X} ===")
print(f"  name={obj_name(console_ptr)} class={obj_class(console_ptr)}")

# The console typically has a reference to the LocalPlayer or ViewportClient
console_data = read_mem(hp, console_ptr, 0x200)
if console_data:
    for off in range(0x28, min(len(console_data), 0x200) - 4, 4):
        ptr = struct.unpack_from('<I', console_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        name = obj_name(ptr)
        if name and ('Viewport' in name or 'Player' in name or 'Engine' in name or 'Local' in name):
            cls = obj_class(ptr)
            print(f"  Console+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

# Try to find PlayerController by scanning memory for XPlayerController instances
print(f"\n=== Scanning for XPlayerController instance ===")
# We know XPlayerController FName index is 8159
# But we need to find the INSTANCE, not the class
# The instance FName might just be "PlayerController" (5381)
# Let's look in the World/Level for the player controller

# Check GWorld
RVA_GWORLD = 0x01000468
world_ptr = read32(hp, base + RVA_GWORLD)
print(f"GWorld = 0x{world_ptr:08X} ({obj_name(world_ptr)}, class={obj_class(world_ptr)})")

# The WorldInfo has a reference to the game or level
# Let's scan the world object for interesting pointers  
world_data = read_mem(hp, world_ptr, 0x400)
if world_data:
    for off in range(0x28, min(len(world_data), 0x400) - 4, 4):
        ptr = struct.unpack_from('<I', world_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        name = obj_name(ptr)
        if name and ('Controller' in name or 'Player' in name or 'Pawn' in name or 'Game' in name):
            cls = obj_class(ptr)
            print(f"  World+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

kernel32.CloseHandle(hp)
