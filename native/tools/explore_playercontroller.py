"""Explore XPlayerController to find Pawn, Inventory, and weapon/vigor list."""
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
    if not addr or addr < 0x10000: return None
    ni = read32(hp, addr + 0x18)
    return rfn(ni)

def obj_class_name(addr):
    if not addr or addr < 0x10000: return None
    cls = read32(hp, addr + 0x20)
    if not cls or cls < 0x10000: return None
    ni = read32(hp, cls + 0x18)
    return rfn(ni)

# Navigate: GEngine -> LocalPlayer -> PlayerController
engine_ptr = read32(hp, base + 0x00FAA024)
tarray_ptr = read32(hp, engine_ptr + 0x1B0)
local_player = read32(hp, tarray_ptr)
pc = read32(hp, local_player + 0x2C)

print(f"PlayerController @ 0x{pc:08X}")
print(f"  name={obj_name(pc)} class={obj_class_name(pc)}")
print(f"  vtable = 0x{read32(hp, pc):08X}")

# Explore PlayerController for Pawn, Inventory, CheatManager
print(f"\n=== PlayerController key fields ===")
pc_data = read_mem(hp, pc, 0x800)
if pc_data:
    interesting = {}
    for off in range(0x28, 0x800, 4):
        ptr = struct.unpack_from('<I', pc_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        name = obj_name(ptr)
        cls = obj_class_name(ptr)
        if not name and not cls: continue
        # Filter for game-relevant objects
        keywords = ['Pawn', 'Player', 'Inventory', 'Weapon', 'Cheat', 'HUD', 
                    'Camera', 'Input', 'Plasmid', 'Vigor', 'Manager']
        if name and any(k in name for k in keywords):
            print(f"  PC+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
            interesting[off] = (ptr, name, cls)
        elif cls and any(k in cls for k in keywords):
            print(f"  PC+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
            interesting[off] = (ptr, name, cls)

# Now explore the Pawn (should be early in the PC data)
print(f"\n=== Looking for Pawn reference ===")
# In UE3, AController::Pawn is typically at a specific offset
# Let's check all pointers for XPawn class instances
for off in range(0x28, 0x400, 4):
    ptr = struct.unpack_from('<I', pc_data, off)[0]
    if ptr < 0x10000 or ptr > 0x7FFE0000: continue
    cls = obj_class_name(ptr)
    if cls and ('Pawn' in cls or 'XPawn' in cls):
        name = obj_name(ptr)
        print(f"  PC+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
        # Explore the pawn for inventory
        pawn_data = read_mem(hp, ptr, 0x800)
        if pawn_data:
            print(f"\n  === Pawn @ 0x{ptr:08X} inventory scan ===")
            for poff in range(0x28, 0x800, 4):
                pptr = struct.unpack_from('<I', pawn_data, poff)[0]
                if pptr < 0x10000 or pptr > 0x7FFE0000: continue
                pname = obj_name(pptr)
                pcls = obj_class_name(pptr)
                if not pname: continue
                if any(k in (pname or '') for k in ['Weapon', 'Inventory', 'Plasmid', 'Manager', 'Vigor']):
                    print(f"    Pawn+0x{poff:04X} -> 0x{pptr:08X} name={pname} class={pcls}")
                elif any(k in (pcls or '') for k in ['Weapon', 'Inventory', 'XWeapon']):
                    print(f"    Pawn+0x{poff:04X} -> 0x{pptr:08X} name={pname} class={pcls}")
        break  # First pawn found

# Also check for CheatManager
print(f"\n=== CheatManager ===")
for off in range(0x28, 0x800, 4):
    ptr = struct.unpack_from('<I', pc_data, off)[0]
    if ptr < 0x10000 or ptr > 0x7FFE0000: continue
    cls = obj_class_name(ptr)
    name = obj_name(ptr)
    if name and 'Cheat' in name:
        print(f"  PC+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
    elif cls and 'Cheat' in cls:
        print(f"  PC+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

kernel32.CloseHandle(hp)
