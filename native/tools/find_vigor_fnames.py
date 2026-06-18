"""Find all vigor-related FName indices and XWeapon instances (all classes)."""
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

# Search keywords for all vigors
keywords = ['Possess', 'Murder', 'Crows', 'Crow', 'Plasmid', 'Vigor',
            'ShockJockey', 'Charge', 'Undertow', 'ReturnToSender',
            'DevilsKiss', 'BuckingBronco', 'VoltSwarm', 'Enrage']

print("=== Scanning GNames for vigor-related FNames ===")
vigor_fnames = []
for i in range(300000):
    n = rfn(i)
    if not n: continue
    for kw in keywords:
        if kw.lower() in n.lower() and 'Plasmid' in n:
            vigor_fnames.append((i, n))
            print(f"  [{i:6d}] {n}")
            break

# Also look for Possession/Possess/MurderOfCrows specifically
print("\n=== All FNames containing 'Possess' or 'Murder' or 'Crow' ===")
for i in range(300000):
    n = rfn(i)
    if not n: continue
    if any(kw in n for kw in ['Possess', 'Murder', 'Crow']):
        print(f"  [{i:6d}] {n}")

# Find XWeapon and all subclass UClasses
print("\n=== Finding weapon UClasses ===")
class_names_to_find = ['XWeapon', 'XWeaponRollingThunder', 'XWeaponConsumable', 'XWeaponPossession']
class_fnames = {}
for i in range(200000):
    n = rfn(i)
    if n in class_names_to_find:
        class_fnames[n] = i
        print(f"  {n} FName = {i}")

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]
mbi = MBI()

# Find UClasses for each
found_classes = {}
for cname, cfni in class_fnames.items():
    scan = 0x10000
    while scan < 0x7FFF0000:
        if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
        re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
        if re2 <= scan: break
        if mbi.State == 0x1000 and not (mbi.Protect & 0x100):
            data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
            if data:
                for i in range(0, len(data) - 0x40, 4):
                    if struct.unpack_from('<i', data, i + 0x18)[0] != cfni: continue
                    if struct.unpack_from('<i', data, i + 0x1C)[0] != 0: continue
                    cp = struct.unpack_from('<I', data, i + 0x20)[0]
                    if not cp: continue
                    cd = read_mem(hp, cp + 0x18, 4)
                    if cd and rfn(struct.unpack_from('<i', cd)[0]) == 'Class':
                        addr = (mbi.BaseAddress or 0) + i
                        found_classes[cname] = addr
                        print(f"  {cname} UClass @ 0x{addr:08X}")
                        break
            if cname in found_classes: break
        scan = re2

# Scan for ALL instances of found classes
print(f"\n=== Scanning for instances of all weapon classes ===")
all_weapons = []
class_addrs = list(found_classes.values())

scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
    if re2 <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100) and (mbi.Protect & 0x6C):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x800, 4):
                cp = struct.unpack_from('<I', data, i + 0x20)[0]
                if cp not in class_addrs: continue
                ni = struct.unpack_from('<i', data, i + 0x18)[0]
                nn = struct.unpack_from('<i', data, i + 0x1C)[0]
                if ni < 0 or ni > 500000: continue
                n = rfn(ni)
                if not n: continue
                addr = (mbi.BaseAddress or 0) + i
                cls_name = [k for k, v in found_classes.items() if v == cp][0]
                # Only show Plasmid/vigor related
                if 'Plasmid' in n or 'Possess' in n.lower() or 'Crow' in n.lower() or 'Murder' in n.lower():
                    # Read DamageType pointers
                    dt_tap = struct.unpack_from('<I', data, i + 0x0228)[0] if i + 0x0308 < len(data) else 0
                    dt_hold = struct.unpack_from('<I', data, i + 0x0308)[0] if i + 0x0400 < len(data) else 0
                    all_weapons.append((n, nn, addr, cls_name, dt_tap, dt_hold))
    scan = re2

print(f"\nVigor instances found ({len(all_weapons)}):")
print(f"{'Name':45s} {'Address':>12s} {'Class':>25s} {'DmgType_Tap':>12s} {'DmgType_Hold':>12s}")
print('-' * 100)
for name, nn, addr, cls, dt, dh in sorted(all_weapons):
    print(f"{name}_{nn:45s} 0x{addr:08X}  {cls:>25s}  0x{dt:08X}  0x{dh:08X}")

kernel32.CloseHandle(hp)
