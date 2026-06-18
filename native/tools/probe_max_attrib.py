"""Find the MaxAmmoCountAttrib and MaxSpareAmmoCountAttrib struct offsets
by walking the XWeapon property chain with the correct UProperty::Offset at +0x48.
Then dump the struct contents on a MachineGun instance."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll

class PBI(ctypes.Structure):
    _fields_ = [("R1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                ("R2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.c_void_p), ("R3", ctypes.c_void_p)]

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

# Get base via module name match
psapi = ctypes.windll.psapi
hMods = (ctypes.c_uint32 * 1024)()
cbNeeded = wt.DWORD()
# LIST_MODULES_32BIT = 0x01
psapi.EnumProcessModulesEx(hp, ctypes.byref(hMods), ctypes.sizeof(hMods), ctypes.byref(cbNeeded), 0x01)
nMods = cbNeeded.value // 4
base = None
for mi in range(nMods):
    mod = hMods[mi]
    if not mod: continue
    modName = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), modName, 260)
    if b'BioShockInfinite' in modName.value:
        base = mod
        break
if not base:
    # fallback: first module
    base = hMods[0]
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
        try:
            e = d.index(b'\x00\x00')
            if e % 2 == 1: e += 1
            return d[:e].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, sa, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

# Find XWeapon class
xwi = -1
for i in range(200000):
    if rfn(i) == 'XWeapon': xwi = i; break

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]
mbi = MBI()

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

# Walk property chain, find MaxAmmoCountAttrib and MaxSpareAmmoCountAttrib
print("\n=== Walking property chain (offset from +0x48) ===")
child = read32(hp, xwc + 0x38)
vis = set(); ct = 0
target_offsets = {}
while child and child > 0x10000 and child < 0xFFFF0000 and child not in vis and ct < 1000:
    vis.add(child); ct += 1
    ni = read32(hp, child + 0x18); n = rfn(ni)
    off48 = read32(hp, child + 0x48)
    sz = read32(hp, child + 0x30)
    cls = read32(hp, child + 0x20)
    cn = rfn(read32(hp, cls + 0x18)) if cls else ''
    
    if n and ('Max' in n or 'Ammo' in n or 'Spare' in n or 'Clip' in n or 'Reload' in n or 'Rounds' in n
             or 'HasInfinite' in n or 'bReplicatedCanAdd' in n):
        print(f"  {n:50s} +0x{off48:04X}  size={sz:4d}  ({cn})")
        target_offsets[n] = (off48, sz)
    
    child = read32(hp, child + 0x28)

# Find a live MachineGun instance
print("\n=== Finding live MachineGun instances ===")
mg_addrs = {}
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    re2 = (mbi.BaseAddress or 0) + mbi.RegionSize
    if re2 <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100) and (mbi.Protect & 0x6C):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x900, 4):
                if struct.unpack_from('<I', data, i + 0x20)[0] != xwc: continue
                ni = struct.unpack_from('<i', data, i + 0x18)[0]
                nn = struct.unpack_from('<i', data, i + 0x1C)[0]
                if ni < 0 or ni > 500000: continue
                n = rfn(ni)
                if not n: continue
                addr = (mbi.BaseAddress or 0) + i
                key = f"{n}_{nn}"
                if 'MachineGun' in key or 'XWeapon' in key:
                    mg_addrs[key] = addr
    scan = re2

print(f"Found: {list(mg_addrs.keys())}")

# Dump MaxAmmoCountAttrib and MaxSpareAmmoCountAttrib struct contents on each
for key, addr in sorted(mg_addrs.items()):
    data = read_mem(hp, addr, 0x0900)
    if not data: continue
    
    # Check archetype to confirm it's a MG
    arch = struct.unpack_from('<I', data, 0x24)[0]
    arch_ni = 0
    if arch:
        ad = read_mem(hp, arch + 0x18, 4)
        if ad: arch_ni = struct.unpack_from('<i', ad)[0]
    arch_name = rfn(arch_ni) if arch_ni else ''
    if not ('MachineGun' in key or 'MachineGun' in (arch_name or '') or 'Gatling' in key):
        continue
    
    print(f"\n  {key} @ 0x{addr:08X} (arch: {arch_name}):")
    
    # Show known ammo values
    for pname, (off, sz) in sorted(target_offsets.items(), key=lambda x: x[1][0]):
        if off + sz <= len(data):
            # Dump the struct contents
            chunk = data[off:off + min(sz, 64)]
            vals = []
            for j in range(0, len(chunk), 4):
                vi = struct.unpack_from('<i', chunk, j)[0]
                vf = struct.unpack_from('<f', chunk, j)[0]
                vf_s = f"{vf:.2f}" if vf == vf and abs(vf) < 100000 else "ptr/nan"
                vals.append(f"+{j:02X}:i={vi:6d}/f={vf_s}")
            print(f"    {pname:45s} @+0x{off:04X} [{', '.join(vals[:8])}]")

kernel32.CloseHandle(hp)
print("\nDone!")
