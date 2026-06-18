"""Find the player pawn and list its current weapon/vigor inventory.
Also find Default__XWeaponWinterbolt and Default__XWeaponChameleon objects."""
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

# Module info
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

gn_ptr = read32(hp, base + 0xF9DFEC)  # GNames

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

# UObject layout
OFF_Name = 0x18
OFF_Class = 0x20
OFF_Archetype = 0x24

# Find key FName indices
targets = {
    'XPawn': -1,
    'XPlayerPawn': -1,
    'Default__XWeaponWinterbolt': -1,
    'Default__XWeaponChameleon': -1,
    'Default__XWeaponReturnToSender': -1,
    'XWeaponWinterbolt': -1,
    'XWeaponChameleon': -1,
    'XWeaponReturnToSender': -1,
    'Plasmid_WinterBolt': -1,
    'Plasmid_Chameleon': -1,
    'Plasmid_ShockJockey_Rapture': -1,
    'XPlayerController': -1,
    'XInventoryManager': -1,
    'InvManager': -1,
    'InventoryManager': -1,
    'PlasmidManager': -1,
    'WeaponManager': -1,
    'PlayerReplicationInfo': -1,
}

print("=== Finding key FNames ===")
for i in range(200000):
    n = rfn(i)
    if n and n in targets:
        targets[n] = i
        print(f"  [{i:6d}] {n}")

# Now scan memory for these objects
print("\n=== Scanning for key objects ===")
si = ctypes.create_string_buffer(36)
kernel32.GetSystemInfo(si)
scan_min = struct.unpack_from('<I', si.raw, 4)[0]
scan_max = struct.unpack_from('<I', si.raw, 8)[0]

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]

# Collect found objects
found_objs = {}
mbi = MBI()
scan = scan_min
while scan < scan_max:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    region_end = mbi.BaseAddress + mbi.RegionSize
    if region_end <= scan: break
    
    if (mbi.State == 0x1000 and not (mbi.Protect & 0x100) and
        (mbi.Protect & (0x04 | 0x40 | 0x08))):  # RW/RWX/WRITECOPY
        data = read_mem(hp, mbi.BaseAddress, min(mbi.RegionSize, 0x2000000))
        if data:
            for off in range(0, len(data) - 0x100, 4):
                name_idx = struct.unpack_from('<i', data, off + OFF_Name)[0]
                name_num = struct.unpack_from('<i', data, off + OFF_Name + 4)[0]
                if name_num != 0: continue
                
                for tgt_name, tgt_idx in targets.items():
                    if tgt_idx >= 0 and name_idx == tgt_idx:
                        addr = mbi.BaseAddress + off
                        cls_ptr = struct.unpack_from('<I', data, off + OFF_Class)[0]
                        arch_ptr = struct.unpack_from('<I', data, off + OFF_Archetype)[0]
                        if tgt_name not in found_objs:
                            found_objs[tgt_name] = []
                        found_objs[tgt_name].append((addr, cls_ptr, arch_ptr))
    scan = region_end

for name, instances in sorted(found_objs.items()):
    print(f"\n  {name}: ({len(instances)} instances)")
    for addr, cls, arch in instances[:3]:  # show max 3
        cls_name = ""
        if cls:
            cn_idx = read32(hp, cls + OFF_Name)
            cls_name = rfn(cn_idx) or f"?{cn_idx}"
        print(f"    @ 0x{addr:08X}  class={cls_name}(0x{cls:08X})  archetype=0x{arch:08X}")

# If we found Default__XWeaponWinterbolt, dump its size/data
if 'Default__XWeaponWinterbolt' in found_objs:
    addr = found_objs['Default__XWeaponWinterbolt'][0][0]
    print(f"\n=== Default__XWeaponWinterbolt @ 0x{addr:08X} ===")
    # Read first 0x30 bytes (UObject header)
    hdr = read_mem(hp, addr, 0x30)
    if hdr:
        print(f"  Header: {hdr.hex()}")
    # Check DamageType pointer at +0x0228
    tap_dmg = read32(hp, addr + 0x0228)
    hold_dmg = read32(hp, addr + 0x0308)
    tap_proj = read32(hp, addr + 0x02EC)
    print(f"  TapDmgType=0x{tap_dmg:08X} HoldDmgType=0x{hold_dmg:08X} TapProj=0x{tap_proj:08X}")
    # Check salt cost
    tap_cost = readf(hp, addr + 0x02BC)
    hold_cost = readf(hp, addr + 0x039C)
    print(f"  TapSaltCost={tap_cost:.1f} HoldSaltCost={hold_cost:.1f}")

kernel32.CloseHandle(hp)
