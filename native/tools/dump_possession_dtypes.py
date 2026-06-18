"""Dump DamageType class info for Possession (Enrage) and Murder of Crows."""
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

def dump_weapon_dtypes(addr, label):
    """Read DamageType and Projectile pointers from an XWeapon instance."""
    print(f"\n=== {label} @ 0x{addr:08X} ===")
    
    offsets = [
        (0x0228, "TapDamageType"),
        (0x02EC, "TapProjectile"),
        (0x0308, "HoldDamageType"),
        (0x03CC, "HoldProjectile"),
    ]
    
    for off, name in offsets:
        ptr = read32(hp, addr + off)
        if ptr:
            # Read the object's FName
            obj_name_idx = read32(hp, ptr + 0x18)
            obj_name = rfn(obj_name_idx) or "???"
            # Read the object's class
            cls_ptr = read32(hp, ptr + 0x20)
            cls_name = "???"
            if cls_ptr:
                cls_name_idx = read32(hp, cls_ptr + 0x18)
                cls_name = rfn(cls_name_idx) or "???"
            # Read first few data bytes after UObject header
            data = read_mem(hp, ptr + 0x28, 64)
            data_hex = data.hex() if data else "???"
            print(f"  +0x{off:04X} {name:20s}: 0x{ptr:08X}")
            print(f"    FName: {obj_name}")
            print(f"    Class: {cls_name}")
            print(f"    Data@+0x28: {data_hex[:80]}...")
        else:
            print(f"  +0x{off:04X} {name:20s}: NULL")

# Known addresses from the scan
vigor_addrs = {
    "Plasmid_EnrageBase (Possession)":     0x633CC000,
    "Plasmid_EnrageFounder (Possession)":  0x75922000,
    "Plasmid_MurderOfCrowsBase (Crows)":   0x633C9000,
    "Plasmid_MurderOfCrowsFounder (Crows)":0x75928000,
}

for label, addr in vigor_addrs.items():
    dump_weapon_dtypes(addr, label)

kernel32.CloseHandle(hp)
