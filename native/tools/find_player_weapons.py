"""Find all XWeapon instances owned by the player pawn.
Uses the XWeapon UClass to find all instances, then checks Owner/Outer/Instigator."""
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

# Get player pawn address
engine_ptr = read32(hp, base + 0x00FAA024)
tarray_ptr = read32(hp, engine_ptr + 0x1B0)
local_player = read32(hp, tarray_ptr)
pc = read32(hp, local_player + 0x2C)
pawn = read32(hp, pc + 0x0674)
print(f"Player Pawn @ 0x{pawn:08X}")

# Find the XWeapon UClass (already known from previous work)
# XWeapon FName should be around index 10030-ish
xweapon_class = None
for i in range(20000):
    n = rfn(i)
    if n == 'XWeapon':
        # Find the UClass object with this FName
        # We know from previous scans it exists - let me use a known address approach
        print(f"  XWeapon FName = {i}")
        break

# Instead of scanning all memory for the UClass, let's use the known approach:
# Find objects whose class has "XWeapon" in the inheritance chain
# Simpler: scan memory for objects whose Outer = pawn and whose class is a weapon class

# Actually, let's just scan all writable memory for any object whose:
# 1. Outer (at +0x14) == pawn address
# 2. FName resolves to something weapon/plasmid related

print(f"\n=== Scanning for objects with Outer=PlayerPawn ===")

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]

mbi = MBI()
scan = 0x10000
found_weapons = []
pawn_bytes = struct.pack('<I', pawn)

while scan < 0x7FFE0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        scan += 0x10000; continue
    region_end = mbi.BaseAddress + mbi.RegionSize
    if region_end <= scan: scan += 0x10000; continue
    
    if (mbi.State == 0x1000 and not (mbi.Protect & 0x100) and
        (mbi.Protect & (0x04 | 0x40 | 0x08))):
        sz = min(mbi.RegionSize, 0x4000000)
        data = read_mem(hp, mbi.BaseAddress, sz)
        if data:
            # Search for pawn pointer at Outer offset (+0x14)
            pos = 0
            while True:
                pos = data.find(pawn_bytes, pos)
                if pos == -1: break
                # Check if this could be a UObject with Outer=pawn at +0x14
                obj_start = pos - 0x14
                if obj_start >= 0 and obj_start + 0x28 <= len(data):
                    # Verify: check FName at +0x18 is valid
                    name_idx = struct.unpack_from('<i', data, obj_start + 0x18)[0]
                    name_num = struct.unpack_from('<i', data, obj_start + 0x1C)[0]
                    if 0 < name_idx < 200000 and name_num == 0:
                        addr = mbi.BaseAddress + obj_start
                        name = rfn(name_idx)
                        if name and 'Default__' not in name:
                            cls = obj_class_name(addr)
                            if cls and ('Weapon' in cls or 'XWeapon' in cls or 'Plasmid' in name or 
                                       'Inventory' in cls or name in ['Pistol', 'Shotgun', 'MachineGun', 
                                       'Carbine', 'HandCannon', 'RPG', 'SniperRifle', 'FlakCannon']):
                                found_weapons.append((addr, name, cls))
                pos += 4
    scan = region_end

print(f"\nFound {len(found_weapons)} weapon/inventory objects owned by player pawn:")
for addr, name, cls in sorted(found_weapons, key=lambda x: x[1]):
    print(f"  0x{addr:08X} name={name} class={cls}")

kernel32.CloseHandle(hp)
