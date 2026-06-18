"""Explore XPlayerPawn to find inventory, weapon list, and vigor slots."""
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

# Navigate to PlayerPawn
engine_ptr = read32(hp, base + 0x00FAA024)
tarray_ptr = read32(hp, engine_ptr + 0x1B0)
local_player = read32(hp, tarray_ptr)
pc = read32(hp, local_player + 0x2C)
pawn = read32(hp, pc + 0x0674)

print(f"XPlayerPawn @ 0x{pawn:08X}")
print(f"  name={obj_name(pawn)} class={obj_class_name(pawn)}")

# Scan pawn for all object references (larger scan since pawn is complex)
print(f"\n=== Pawn object scan (0x1000 bytes) ===")
pawn_data = read_mem(hp, pawn, 0x1000)
if pawn_data:
    for off in range(0x28, 0x1000, 4):
        ptr = struct.unpack_from('<I', pawn_data, off)[0]
        if ptr < 0x10000 or ptr > 0x7FFE0000: continue
        name = obj_name(ptr)
        cls = obj_class_name(ptr)
        if not name: continue
        # Show weapon, inventory, plasmid, vigor related
        keywords = ['Weapon', 'Inventory', 'Plasmid', 'Vigor', 'Manager', 'Ammo',
                    'Slot', 'Item', 'Loadout', 'Arsenal', 'XWeapon', 'InvManager']
        if any(k.lower() in (name or '').lower() for k in keywords):
            print(f"  Pawn+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")
        elif any(k.lower() in (cls or '').lower() for k in keywords):
            print(f"  Pawn+0x{off:04X} -> 0x{ptr:08X} name={name} class={cls}")

    # Also look for TArrays that might contain weapons
    print(f"\n=== Looking for weapon TArrays ===")
    for off in range(0x28, 0xF00, 4):
        data_ptr = struct.unpack_from('<I', pawn_data, off)[0]
        count = struct.unpack_from('<i', pawn_data, off + 4)[0]
        max_val = struct.unpack_from('<i', pawn_data, off + 8)[0]
        # TArray with reasonable count (2-10 weapons/vigors)
        if 2 <= count <= 20 and count <= max_val <= 32 and data_ptr > 0x10000 and data_ptr < 0x7FFE0000:
            # Read elements and check if they're XWeapon instances
            arr_data = read_mem(hp, data_ptr, count * 4)
            if not arr_data: continue
            weapons_found = []
            for i in range(count):
                elem = struct.unpack_from('<I', arr_data, i * 4)[0]
                if elem < 0x10000: continue
                ecls = obj_class_name(elem)
                ename = obj_name(elem)
                if ecls and 'Weapon' in ecls:
                    weapons_found.append((elem, ename, ecls))
            if weapons_found:
                print(f"\n  Pawn+0x{off:04X}: TArray[{count}/{max_val}] @ 0x{data_ptr:08X}")
                for addr, name, cls in weapons_found:
                    print(f"    0x{addr:08X} name={name} class={cls}")

kernel32.CloseHandle(hp)
