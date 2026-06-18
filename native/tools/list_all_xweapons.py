"""List ALL XWeapon instances with their names and archetype chains."""
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

# Find XWeapon FName index
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
print(f"XWeapon UClass @ 0x{xwc:08X}")

# Also find XWeaponConsumable class (vigors may use a subclass)
xwci = -1
for i in range(200000):
    n = rfn(i)
    if n and 'XWeaponConsumable' in n:
        print(f"  Found FName: [{i}] {n}")
        xwci = i

# Find ALL XWeapon instances
weapons = []
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
    if re2 <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100) and (mbi.Protect & 0x6C):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x400, 4):
                cp = struct.unpack_from('<I', data, i + 0x20)[0]
                if cp != xwc: continue
                ni = struct.unpack_from('<i', data, i + 0x18)[0]
                nn = struct.unpack_from('<i', data, i + 0x1C)[0]
                if ni < 0 or ni > 500000: continue
                n = rfn(ni)
                if not n: continue
                addr = (mbi.BaseAddress or 0) + i
                # Get archetype chain (2 levels)
                arch1 = struct.unpack_from('<I', data, i + 0x24)[0]
                a1_name = ''
                if arch1:
                    ad = read_mem(hp, arch1 + 0x18, 4)
                    if ad: a1_name = rfn(struct.unpack_from('<i', ad)[0]) or ''
                arch2 = 0
                a2_name = ''
                if arch1:
                    ad = read_mem(hp, arch1 + 0x24, 4)
                    if ad:
                        arch2 = struct.unpack_from('<I', ad)[0]
                        if arch2:
                            ad2 = read_mem(hp, arch2 + 0x18, 4)
                            if ad2: a2_name = rfn(struct.unpack_from('<i', ad2)[0]) or ''
                
                # Get class name for this object's class
                cls_name = ''
                cd = read_mem(hp, cp + 0x18, 4)
                if cd: cls_name = rfn(struct.unpack_from('<i', cd)[0]) or ''
                
                weapons.append((f"{n}_{nn}", addr, a1_name, a2_name, cls_name))
    scan = re2

print(f"\nAll XWeapon instances ({len(weapons)}):")
print(f"{'Name':45s} {'Address':>12s} {'Class':>20s} {'Archetype1':>30s} {'Archetype2':>30s}")
print('-' * 140)
for name, addr, a1, a2, cls in sorted(weapons):
    print(f"{name:45s} 0x{addr:08X}  {cls:>20s}  {a1:>30s}  {a2:>30s}")

# Also scan for objects with Bronco-related class pointers (XWeaponConsumable, etc.)
print(f"\n=== Scanning for Bronco-named objects of ANY class ===")
bronco_fnames = set()
for i in range(200000):
    n = rfn(i)
    if n and ('BuckingBronco' in n or 'Bronco' in n) and 'Plasmid' in n:
        bronco_fnames.add((i, n))

print(f"Bronco Plasmid FName indices: {[(i,n) for i,n in bronco_fnames]}")

# Scan for any objects with these FName indices
found_bronco = []
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
    if re2 <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100) and (mbi.Protect & 0x6C):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for bfi, bfn in bronco_fnames:
                for i in range(0, len(data) - 0x40, 4):
                    if struct.unpack_from('<i', data, i + 0x18)[0] != bfi: continue
                    addr = (mbi.BaseAddress or 0) + i
                    cp = struct.unpack_from('<I', data, i + 0x20)[0]
                    cls_name = '?'
                    if cp:
                        cd = read_mem(hp, cp + 0x18, 4)
                        if cd: cls_name = rfn(struct.unpack_from('<i', cd)[0]) or '?'
                    found_bronco.append((bfn, addr, cls_name))
    scan = re2

print(f"\nFound {len(found_bronco)} Bronco Plasmid objects:")
for name, addr, cls in found_bronco:
    print(f"  {name} @ 0x{addr:08X} (class: {cls})")

kernel32.CloseHandle(hp)
