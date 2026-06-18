"""Targeted scan for Default__XWeaponWinterbolt, Default__XWeaponChameleon, 
and Default__XWeaponReturnToSender objects (class default objects)."""
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

def readf(hp, a):
    d = read_mem(hp, a, 4)
    return struct.unpack('<f', d)[0] if d else 0.0

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

OFF_Name = 0x18

# Target FName indices to find
target_fnames = {}
search_names = [
    'Default__XWeaponWinterbolt',
    'Default__XWeaponChameleon', 
    'Default__XWeaponReturnToSender',
    'XWeaponWinterbolt',
    'XWeaponChameleon',
    'XWeaponReturnToSender',
    'Plasmid_WinterBolt',
    'Plasmid_Chameleon',
    'Plasmid_ShockJockey_Rapture',
    'Default__XWeaponVoltSwarm',
    'Plasmid_VoltSwarmFounder',
    'XWeaponVoltSwarm',
]
print("Finding FName indices...")
for i in range(200000):
    n = rfn(i)
    if n and n in search_names:
        target_fnames[n] = i
        print(f"  [{i:6d}] {n}")

if not target_fnames:
    print("No target FNames found!")
    kernel32.CloseHandle(hp)
    sys.exit(1)

# Scan all memory for UObjects with these FName indices at +0x18
print(f"\nScanning memory for {len(target_fnames)} target FNames...")

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]

found = {}
mbi = MBI()
scan = 0x10000
total_scanned = 0
target_indices = set(target_fnames.values())

while scan < 0x7FFE0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        scan += 0x10000
        continue
    region_end = mbi.BaseAddress + mbi.RegionSize
    if region_end <= scan:
        scan += 0x10000
        continue
    
    if (mbi.State == 0x1000 and not (mbi.Protect & 0x100) and
        (mbi.Protect & (0x04 | 0x40 | 0x08 | 0x02))):  # include READ_ONLY too
        sz = min(mbi.RegionSize, 0x4000000)
        data = read_mem(hp, mbi.BaseAddress, sz)
        if data:
            total_scanned += len(data)
            for off in range(0, len(data) - 0x28, 4):
                name_idx = struct.unpack_from('<i', data, off + OFF_Name)[0]
                if name_idx in target_indices:
                    name_num = struct.unpack_from('<i', data, off + OFF_Name + 4)[0]
                    if name_num != 0: continue
                    addr = mbi.BaseAddress + off
                    cls_ptr = struct.unpack_from('<I', data, off + 0x20)[0]
                    arch_ptr = struct.unpack_from('<I', data, off + 0x24)[0]
                    # Resolve name
                    for nm, idx in target_fnames.items():
                        if idx == name_idx:
                            if nm not in found: found[nm] = []
                            found[nm].append((addr, cls_ptr, arch_ptr))
                            break
    scan = region_end

print(f"Scanned {total_scanned/1024/1024:.0f} MB")

for name in sorted(found.keys()):
    instances = found[name]
    print(f"\n{name}: {len(instances)} instance(s)")
    for addr, cls, arch in instances[:5]:
        cls_name = "?"
        if cls:
            cn_idx = read32(hp, cls + OFF_Name)
            if cn_idx: cls_name = rfn(cn_idx) or f"idx={cn_idx}"
        arch_name = "?"
        if arch:
            an_idx = read32(hp, arch + OFF_Name)
            if an_idx: arch_name = rfn(an_idx) or f"idx={an_idx}"
        print(f"  @ 0x{addr:08X}  class=0x{cls:08X}({cls_name})  archetype=0x{arch:08X}({arch_name})")
        # For Default__ objects, dump some key fields
        if 'Default__' in name:
            tap_dmg = read32(hp, addr + 0x0228)
            hold_dmg = read32(hp, addr + 0x0308)
            tap_proj = read32(hp, addr + 0x02EC)
            tap_cost = readf(hp, addr + 0x02BC)
            hold_cost = readf(hp, addr + 0x039C)
            fire_delay = readf(hp, addr + 0x0240)
            print(f"    TapDmgType=0x{tap_dmg:08X} TapProj=0x{tap_proj:08X}")
            print(f"    HoldDmgType=0x{hold_dmg:08X}")
            print(f"    TapCost={tap_cost:.1f} HoldCost={hold_cost:.1f} FireDelay={fire_delay:.3f}")

kernel32.CloseHandle(hp)
