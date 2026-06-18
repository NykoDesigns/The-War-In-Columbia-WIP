"""Find ALL instances of every XWeapon subclass to identify Possession."""
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
base = hMods[0]
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value: base = mod; break
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

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]
mbi = MBI()

# All vigor-related XWeapon subclasses to search
target_classes = [
    'XWeapon', 'XWeaponSlave', 'XWeaponIncinerate', 'XWeaponMurderOfCrows',
    'XWeaponRollingThunder', 'XWeaponCharge', 'XWeaponUndertow',
    'XWeaponReturnToSender', 'XWeaponVoltSwarm', 'XWeaponChameleon',
    'XWeaponBeam', 'XWeaponWinterbolt', 'XWeaponDedicatedMelee'
]

# Step 1: Find FName indices
class_fnames = {}
for i in range(200000):
    n = rfn(i)
    if n in target_classes:
        class_fnames[n] = i

# Step 2: Find UClasses
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
                        break
            if cname in found_classes: break
        scan = re2

print(f"Found {len(found_classes)} UClasses:")
for cname, addr in sorted(found_classes.items()):
    print(f"  {cname:30s} @ 0x{addr:08X}")

# Step 3: Scan for ALL instances of all found classes
class_addrs = {v: k for k, v in found_classes.items()}
all_instances = []

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
                # Only show Plasmid-related or interesting vigor instances
                if 'Plasmid' in n or 'Possess' in n or 'Enrage' in n or 'Slave' in n or 'Default__' in n:
                    addr = (mbi.BaseAddress or 0) + i
                    cls = class_addrs[cp]
                    all_instances.append((cls, n, nn, addr))
    scan = re2

print(f"\nVigor/Plasmid instances ({len(all_instances)}):")
print(f"{'Class':30s} {'Name':50s} {'Address':>12s}")
print('-' * 95)
for cls, name, nn, addr in sorted(all_instances):
    print(f"{cls:30s} {name}_{nn:<45d} 0x{addr:08X}")

kernel32.CloseHandle(hp)
