"""Find Bucking Bronco XWeapon instances and dump their properties.
Also find Devil's Kiss to compare damage types for vigor combination."""
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
if not pid: print("Game not running!"); sys.exit(1)
hp = kernel32.OpenProcess(0x1F0FFF, False, pid)

psapi = ctypes.windll.psapi
hMods = (ctypes.c_uint32 * 1024)()
cbNeeded = wt.DWORD()
psapi.EnumProcessModulesEx(hp, ctypes.byref(hMods), ctypes.sizeof(hMods), ctypes.byref(cbNeeded), 0x01)
base = None
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value: base = mod; break
if not base: base = hMods[0]
print(f"Base: 0x{base:08X}")
gn = struct.unpack('<I', read_mem(hp, base + 0xF9DFEC, 4))[0]

def rfn(i):
    if i < 0 or i > 400000: return None
    ep = read32(hp, gn + i * 4)
    if not ep: return None
    fl = read32(hp, ep + 8); sa = ep + 0x10
    if fl & 1:
        d = read_mem(hp, sa, 512)
        if not d: return None
        try: e = d.index(b'\x00\x00'); e += (e%2); return d[:e].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, sa, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

# Find FName indices for relevant vigors
print("\n=== Searching GNames for vigor-related FNames ===")
bronco_names = []
devilskiss_names = []
for i in range(200000):
    n = rfn(i)
    if not n: continue
    nl = n.lower()
    if 'bronco' in nl or 'bucking' in nl:
        bronco_names.append((i, n))
    if 'devilskiss' in nl or 'devils' in nl or 'devil' in nl:
        devilskiss_names.append((i, n))

print(f"\nBronco-related FNames ({len(bronco_names)}):")
for idx, n in bronco_names[:30]:
    print(f"  [{idx:6d}] {n}")

print(f"\nDevil's Kiss-related FNames ({len(devilskiss_names)}):")
for idx, n in devilskiss_names[:30]:
    print(f"  [{idx:6d}] {n}")

# Find XWeapon class
xwi = -1
for i in range(200000):
    if rfn(i) == 'XWeapon': xwi = i; break

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]
mbi = MBI()

# Find XWeapon UClass
xwc = None
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
    if re2 <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x40, 4):
                if struct.unpack_from('<i', data, i + 0x18)[0] != xwi: continue
                if struct.unpack_from('<i', data, i + 0x1C)[0] != 0: continue
                cp = struct.unpack_from('<I', data, i + 0x20)[0]
                if not cp: continue
                cd = read_mem(hp, cp + 0x18, 4)
                if cd and rfn(struct.unpack_from('<i', cd)[0]) == 'Class':
                    xwc = (mbi.BaseAddress or 0) + i; break
        if xwc: break
    scan = re2
print(f"\nXWeapon UClass @ 0x{xwc:08X}")

# Find ALL vigor XWeapon instances
weapons = {}
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
    if re2 <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100) and (mbi.Protect & 0x6C):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x0E00, 4):
                if struct.unpack_from('<I', data, i + 0x20)[0] != xwc: continue
                ni = struct.unpack_from('<i', data, i + 0x18)[0]
                nn = struct.unpack_from('<i', data, i + 0x1C)[0]
                if ni < 0 or ni > 500000: continue
                n = rfn(ni)
                if not n: continue
                addr = (mbi.BaseAddress or 0) + i
                weapons[f"{n}_{nn}"] = addr
    scan = re2

print(f"\n=== All XWeapon instances ({len(weapons)}) ===")
# Filter vigor-related ones
vigor_weapons = {k: v for k, v in weapons.items() 
                 if 'Plasmid' in k or 'Bronco' in k or 'Devil' in k or 'Kiss' in k}
gun_weapons = {k: v for k, v in weapons.items() if k not in vigor_weapons}

print(f"\nVigor XWeapon instances ({len(vigor_weapons)}):")
for name, addr in sorted(vigor_weapons.items()):
    data = read_mem(hp, addr, 0x0E00)
    if not data: continue
    arch = struct.unpack_from('<I', data, 0x24)[0]
    arch_name = ''
    if arch:
        ad = read_mem(hp, arch + 0x18, 4)
        if ad: arch_name = rfn(struct.unpack_from('<i', ad)[0]) or ''
    
    # Key properties
    fire_interval = struct.unpack_from('<f', data, 0x0240)[0]
    salt_tap = struct.unpack_from('<f', data, 0x02BC)[0]
    salt_held = struct.unpack_from('<f', data, 0x039C)[0]
    
    print(f"  {name:40s} @ 0x{addr:08X} (arch: {arch_name})")
    print(f"    FireInterval={fire_interval:.3f}  SaltTap={salt_tap:.1f}  SaltHeld={salt_held:.1f}")

# Now dump extra detail for Bronco and DevilsKiss
print(f"\n{'='*80}")
print("=== Detailed dump: Bronco & DevilsKiss vigors ===")
print(f"{'='*80}")

# Offsets of interest beyond standard weapon
# We want to find: DamageType references, effect classes, projectile classes
# UE3 Weapon class has WeaponProjectiles array and InstantHitDamageTypes
# Let's dump a range of pointers and identify them

for name, addr in sorted(vigor_weapons.items()):
    if 'Bronco' not in name and 'DevilsKiss' not in name and 'Enrage' not in name:
        continue
    data = read_mem(hp, addr, 0x0E00)
    if not data: continue
    
    arch = struct.unpack_from('<I', data, 0x24)[0]
    arch_name = ''
    if arch:
        ad = read_mem(hp, arch + 0x18, 4)
        if ad: arch_name = rfn(struct.unpack_from('<i', ad)[0]) or ''
    
    print(f"\n{'─'*60}")
    print(f"{name} @ 0x{addr:08X} (arch: {arch_name})")
    
    # Dump all pointer-like values with name resolution in key ranges
    # Focus on +0x200 to +0x400 (weapon config area)
    print(f"  Offset range +0x200 to +0x400 (pointers with names):")
    for off in range(0x200, 0x400, 4):
        val = struct.unpack_from('<I', data, off)[0]
        if val < 0x10000 or val > 0x7FFF0000: continue
        # Try to read as UObject - check if it has a valid FName
        d2 = read_mem(hp, val + 0x18, 8)
        if not d2: continue
        ni2 = struct.unpack_from('<i', d2, 0)[0]
        nn2 = struct.unpack_from('<i', d2, 4)[0]
        n2 = rfn(ni2)
        if n2 and len(n2) > 2 and len(n2) < 100:
            # Also get class
            cd = read_mem(hp, val + 0x20, 4)
            cls = ''
            if cd:
                ci = struct.unpack_from('<I', cd)[0]
                cn = read_mem(hp, ci + 0x18, 4) if ci else None
                cls = rfn(struct.unpack_from('<i', cn)[0]) if cn else ''
            print(f"    +0x{off:04X}: -> {n2}_{nn2} (class: {cls or '?'})")

kernel32.CloseHandle(hp)
print("\nDone!")
