"""Check SkyhookMelee's Outer and find where it references the pawn."""
import ctypes, struct, subprocess, sys
kernel32 = ctypes.windll.kernel32

def find_pid(n):
    o = subprocess.check_output(['tasklist','/FI',f'IMAGENAME eq {n}','/FO','CSV','/NH'], text=True)
    for l in o.strip().split('\n'):
        if n.lower() in l.lower(): return int(l.strip().split(',')[1].strip('"'))
    return None

def read_mem(hp, a, s):
    b = ctypes.create_string_buffer(s); br = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(hp, ctypes.c_void_p(a), b, s, ctypes.byref(br)): return b.raw[:br.value]
    return None

def read32(hp, a):
    d = read_mem(hp, a, 4)
    return struct.unpack('<I', d)[0] if d else 0

pid = find_pid('BioShockInfinite.exe')
if not pid: print("Not running"); sys.exit(1)
hp = kernel32.OpenProcess(0x1F0FFF, False, pid)

psapi = ctypes.windll.psapi
hMods = (ctypes.c_uint32 * 1024)()
cb = ctypes.wintypes.DWORD()
psapi.EnumProcessModulesEx(hp, ctypes.byref(hMods), ctypes.sizeof(hMods), ctypes.byref(cb), 0x01)
base = hMods[0]
for mi in range(cb.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value: base = mod; break

gn = read32(hp, base + 0xF9DFEC)

def rfn(i):
    if i < 0 or i > 400000: return None
    ep = read32(hp, gn + i * 4)
    if not ep: return None
    fl = read32(hp, ep + 8)
    if fl & 1:
        d = read_mem(hp, ep + 0x10, 512)
        if not d: return None
        try: e = d.index(b'\x00\x00'); e += (e % 2); return d[:e].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, ep + 0x10, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

# Navigate
engine = read32(hp, base + 0x00FAA024)
ta = read32(hp, engine + 0x1B0)
lp = read32(hp, ta)
pc = read32(hp, lp + 0x2C)
pawn = read32(hp, pc + 0x0674)
print(f"Pawn @ 0x{pawn:08X}")

# SkyhookMelee at Pawn+0x1DEC
skyhook = read32(hp, pawn + 0x1DEC)
print(f"SkyhookMelee @ 0x{skyhook:08X}")
outer = read32(hp, skyhook + 0x14)
outer_name = rfn(read32(hp, outer + 0x18)) if outer > 0x10000 else "NULL"
print(f"  Outer = 0x{outer:08X} ({outer_name})")

# Find which field in SkyhookMelee points to pawn
sk_data = read_mem(hp, skyhook, 0x800)
if sk_data:
    pawn_bytes = struct.pack('<I', pawn)
    for off in range(0, len(sk_data) - 4, 4):
        val = struct.unpack_from('<I', sk_data, off)[0]
        if val == pawn:
            print(f"  Skyhook+0x{off:04X} == PlayerPawn (Owner/Instigator)")

# Also check: are we in a level? Check if there are ANY active Plasmid instances
# by looking for objects with FName "Plasmid_VoltSwarmFounder" that have a valid outer
print(f"\n=== Checking for active vigor instances ===")
# Find Plasmid_VoltSwarmFounder FName index
for i in range(60000):
    n = rfn(i)
    if n == 'Plasmid_VoltSwarmFounder':
        print(f"  FName index: {i}")
        break

# Look in memory for this instance (we know from WeaponStatPatchThread it exists)
# From our earlier scan, Plasmid_VoltSwarmFounder had archetype at 0x7DF65000
# Let's check that address
arch_addr = 0x7DF65000
arch_name = rfn(read32(hp, arch_addr + 0x18)) if read_mem(hp, arch_addr, 4) else None
print(f"  Archetype @ 0x{arch_addr:08X} name={arch_name}")
if arch_name:
    arch_outer = read32(hp, arch_addr + 0x14)
    print(f"    Outer = 0x{arch_outer:08X} ({rfn(read32(hp, arch_outer + 0x18)) if arch_outer > 0x10000 else 'NULL'})")
    # Check if any field in the archetype points to pawn
    arch_data = read_mem(hp, arch_addr, 0x100)
    if arch_data:
        for off in range(0, 0x100, 4):
            val = struct.unpack_from('<I', arch_data, off)[0]
            if val == pawn:
                print(f"    +0x{off:04X} == PlayerPawn")

kernel32.CloseHandle(hp)
