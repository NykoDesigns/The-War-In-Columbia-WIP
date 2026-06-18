"""Dump the MaxAmmoCountAttrib and MaxSpareAmmoCountAttrib structs
on all MachineGun XWeapon instances."""
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

# Known XWeapon class - find it
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

# Find all MG-like weapons
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

# Struct layout:
# MaxAmmoCountAttrib at +0x07C8, size 36 (9 DWORDs)
# MaxSpareAmmoCountAttrib at +0x07F0, size 36 (9 DWORDs)

print(f"\n{'='*100}")
print(f"{'Weapon':30s} | {'AmmoCount':>9s} | MaxAmmoCountAttrib (36 bytes @ +0x07C8)")
print(f"{'':30s} | {'SpareAmmo':>9s} | MaxSpareAmmoCountAttrib (36 bytes @ +0x07F0)")
print(f"{'='*100}")

for key in ['MachineGunBase_0', 'MachineGunFounder_0', 'MachineGunVP_0', 'GatlingGun_0',
            'PistolBase_0', 'PistolFounder_0', 'ShotgunBase_0', 'CarbineBase_0',
            'XWeapon_1', 'Default__XWeapon_0']:
    if key not in weapons: continue
    addr = weapons[key]
    data = read_mem(hp, addr, 0x0E00)
    if not data: continue
    
    # Check archetype
    arch = struct.unpack_from('<I', data, 0x24)[0]
    arch_name = ''
    if arch:
        ad = read_mem(hp, arch + 0x18, 4)
        if ad:
            arch_name = rfn(struct.unpack_from('<i', ad)[0]) or ''
    
    ammo = struct.unpack_from('<i', data, 0x07C4)[0]
    spare = struct.unpack_from('<i', data, 0x07EC)[0]
    
    # Dump MaxAmmoCountAttrib struct
    mac_bytes = data[0x07C8:0x07C8+36]
    mac_vals = []
    for j in range(0, 36, 4):
        vi = struct.unpack_from('<i', mac_bytes, j)[0]
        vf = struct.unpack_from('<f', mac_bytes, j)[0]
        vf_s = f"{vf:.1f}" if vf == vf and abs(vf) < 100000 else "ptr"
        mac_vals.append(f"{vi:6d}/{vf_s:>8s}")
    
    # Dump MaxSpareAmmoCountAttrib struct
    msa_bytes = data[0x07F0:0x07F0+36]
    msa_vals = []
    for j in range(0, 36, 4):
        vi = struct.unpack_from('<i', msa_bytes, j)[0]
        vf = struct.unpack_from('<f', msa_bytes, j)[0]
        vf_s = f"{vf:.1f}" if vf == vf and abs(vf) < 100000 else "ptr"
        msa_vals.append(f"{vi:6d}/{vf_s:>8s}")
    
    print(f"\n{key:30s} (arch: {arch_name})")
    print(f"  AmmoCount={ammo:4d} | MaxAmmoCountAttrib:")
    for j, v in enumerate(mac_vals):
        print(f"    +0x{0x07C8+j*4:04X} (struct+{j*4:02X}): {v}")
    print(f"  SpareAmmo={spare:4d} | MaxSpareAmmoCountAttrib:")
    for j, v in enumerate(msa_vals):
        print(f"    +0x{0x07F0+j*4:04X} (struct+{j*4:02X}): {v}")

# Also find XWeapon instances via archetype chain
print(f"\n{'='*60}")
print("XWeapon instances with MG archetypes:")
mg_arch_addrs = set()
for key in weapons:
    if 'MachineGun' in key or 'Gatling' in key:
        mg_arch_addrs.add(weapons[key])

for key, addr in weapons.items():
    if 'XWeapon' not in key and 'None' not in key: continue
    data = read_mem(hp, addr, 0x0E00)
    if not data: continue
    arch = struct.unpack_from('<I', data, 0x24)[0]
    if arch not in mg_arch_addrs: continue
    
    arch_name = ''
    ad = read_mem(hp, arch + 0x18, 4)
    if ad: arch_name = rfn(struct.unpack_from('<i', ad)[0]) or ''
    
    ammo = struct.unpack_from('<i', data, 0x07C4)[0]
    spare = struct.unpack_from('<i', data, 0x07EC)[0]
    
    mac_bytes = data[0x07C8:0x07C8+36]
    msa_bytes = data[0x07F0:0x07F0+36]
    
    print(f"\n  {key} @ 0x{addr:08X} (arch: {arch_name})")
    print(f"    AmmoCount={ammo}, SpareAmmo={spare}")
    print(f"    MaxAmmoAttrib struct:")
    for j in range(0, 36, 4):
        vi = struct.unpack_from('<i', mac_bytes, j)[0]
        vf = struct.unpack_from('<f', mac_bytes, j)[0]
        vf_s = f"{vf:.1f}" if vf == vf and abs(vf) < 100000 else "ptr"
        print(f"      +{j:02X}: int={vi:8d}  float={vf_s}")
    print(f"    MaxSpareAttrib struct:")
    for j in range(0, 36, 4):
        vi = struct.unpack_from('<i', msa_bytes, j)[0]
        vf = struct.unpack_from('<f', msa_bytes, j)[0]
        vf_s = f"{vf:.1f}" if vf == vf and abs(vf) < 100000 else "ptr"
        print(f"      +{j:02X}: int={vi:8d}  float={vf_s}")

kernel32.CloseHandle(hp)
print("\nDone!")
