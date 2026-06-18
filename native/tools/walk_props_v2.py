"""Walk XWeapon property chain with corrected UStruct layout.
Try all plausible Children offsets and walk via UField::Next (+0x28)."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

def find_pid(name):
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for line in out.strip().split('\n'):
        if name.lower() in line.lower():
            return int(line.strip().split(',')[1].strip('"'))
    return None

def read_mem(hp, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(hp, ctypes.c_void_p(addr), buf, size, ctypes.byref(br)):
        return buf.raw[:br.value]
    return None

def read32(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<I', d)[0] if d else 0

pid = find_pid('BioShockInfinite.exe')
if not pid: print("Game not running!"); sys.exit(1)
hp = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)

psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cb = wt.DWORD()
psapi.EnumProcessModules(hp, hMods, ctypes.sizeof(hMods), ctypes.byref(cb))
base = hMods[0]
gnames_addr = struct.unpack('<I', read_mem(hp, base + 0xF9DFEC, 4))[0]

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    ep_data = read_mem(hp, gnames_addr + index * 4, 4)
    if not ep_data: return None
    ep = struct.unpack('<I', ep_data)[0]
    if not ep: return None
    flags_data = read_mem(hp, ep + 0x08, 4)
    if not flags_data: return None
    flags = struct.unpack('<I', flags_data)[0]
    sa = ep + 0x10
    if flags & 1:
        d = read_mem(hp, sa, 512)
        if not d: return None
        try:
            end = d.index(b'\x00\x00')
            if end % 2 == 1: end += 1
            return d[:end].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, sa, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

# Find XWeapon UClass
xweapon_idx = -1
for i in range(200000):
    name = resolve_fname(i)
    if name == 'XWeapon': xweapon_idx = i; break

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD),
    ]
mbi = MEMORY_BASIC_INFORMATION()

xweapon_class = None
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan: break
    if mbi.State == 0x1000 and not (mbi.Protect & 0x100):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x40, 4):
                if struct.unpack_from('<i', data, i + 0x18)[0] != xweapon_idx: continue
                if struct.unpack_from('<i', data, i + 0x1C)[0] != 0: continue
                cls_ptr = struct.unpack_from('<I', data, i + 0x20)[0]
                if not cls_ptr: continue
                cls_data = read_mem(hp, cls_ptr + 0x18, 4)
                if not cls_data: continue
                if resolve_fname(struct.unpack_from('<i', cls_data)[0]) == 'Class':
                    xweapon_class = (mbi.BaseAddress or 0) + i
                    break
        if xweapon_class: break
    scan = region_end

print(f"XWeapon UClass @ 0x{xweapon_class:08X}")

# Walk from Children at +0x38 via Next at +0x28
# This is the first approach
print("\n=== Walking from +0x38 (Children) via Next at +0x28 ===")
child = read32(hp, xweapon_class + 0x38)
visited = set()
all_props = {}
count = 0
while child and child > 0x10000 and child < 0xFFFF0000 and child not in visited and count < 1000:
    visited.add(child)
    count += 1
    name_idx = read32(hp, child + 0x18)
    name = resolve_fname(name_idx)
    offset_val = read32(hp, child + 0x5C)
    
    # Check class to see if it's a Property
    cls = read32(hp, child + 0x20)
    cls_name = ''
    if cls:
        cls_name_idx = read32(hp, cls + 0x18)
        cls_name = resolve_fname(cls_name_idx) or ''
    
    if name and 'Property' in cls_name:
        all_props[name] = (offset_val, cls_name)
        if ('Ammo' in name or 'Clip' in name or 'Spare' in name or 'Fire' in name
            or 'Max' in name or 'Reserve' in name or 'Cost' in name or 'Energy' in name
            or 'Vigor' in name or 'Salt' in name or 'Magazine' in name
            or 'Damage' in name or 'Spread' in name or 'Range' in name):
            print(f"  {name:45s} +0x{offset_val:04X} ({cls_name})")
    
    child = read32(hp, child + 0x28)

print(f"  Total properties found: {count}")

# If that didn't work well, try walking the PARENT class chain too
# UStruct::SuperField at +0x34, walk its children too
print("\n=== Walking parent classes ===")
super_class = read32(hp, xweapon_class + 0x34)
depth = 0
while super_class and super_class > 0x10000 and depth < 10:
    depth += 1
    sname_idx = read32(hp, super_class + 0x18)
    sname = resolve_fname(sname_idx) or '?'
    print(f"\n  Parent class: {sname} @ 0x{super_class:08X}")
    
    child = read32(hp, super_class + 0x38)
    visited2 = set()
    pcount = 0
    while child and child > 0x10000 and child < 0xFFFF0000 and child not in visited2 and pcount < 500:
        visited2.add(child)
        pcount += 1
        name_idx = read32(hp, child + 0x18)
        name = resolve_fname(name_idx)
        offset_val = read32(hp, child + 0x5C)
        cls = read32(hp, child + 0x20)
        cls_name = ''
        if cls:
            cls_name_idx = read32(hp, cls + 0x18)
            cls_name = resolve_fname(cls_name_idx) or ''
        
        if name and 'Property' in cls_name:
            if ('Ammo' in name or 'Clip' in name or 'Spare' in name or 'Fire' in name
                or 'Max' in name or 'Reserve' in name or 'Magazine' in name):
                all_props[name] = (offset_val, cls_name)
                print(f"    {name:45s} +0x{offset_val:04X} ({cls_name})")
        
        child = read32(hp, child + 0x28)
    
    super_class = read32(hp, super_class + 0x34)

# Read values on MachineGunBase for all discovered ammo props
if all_props:
    # Find MachineGunBase
    scan = 0x10000
    mg_addr = None
    while scan < 0x7FFF0000 and not mg_addr:
        if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
        region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
        if region_end <= scan: break
        if mbi.State == 0x1000 and not (mbi.Protect & 0x100) and (mbi.Protect & 0x6C):
            data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
            if data:
                for i in range(0, len(data) - 0x800, 4):
                    if struct.unpack_from('<I', data, i + 0x20)[0] != xweapon_class: continue
                    name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                    name = resolve_fname(name_idx)
                    if name == 'MachineGunBase':
                        mg_addr = (mbi.BaseAddress or 0) + i
                        break
            if mg_addr: break
        scan = region_end
    
    if mg_addr:
        print(f"\n=== MachineGunBase @ 0x{mg_addr:08X} — values at discovered offsets ===")
        mg_data = read_mem(hp, mg_addr, 0xA000)
        if mg_data:
            for pname, (off, cls_name) in sorted(all_props.items(), key=lambda x: x[1][0]):
                if ('Ammo' in pname or 'Clip' in pname or 'Spare' in pname or 'Fire' in pname
                    or 'Max' in pname or 'Reserve' in pname or 'Magazine' in pname
                    or 'Damage' in pname or 'Spread' in pname):
                    if off < len(mg_data) - 4:
                        vi = struct.unpack_from('<i', mg_data, off)[0]
                        vf = struct.unpack_from('<f', mg_data, off)[0]
                        vf_s = f"{vf:.4f}" if vf == vf and abs(vf) < 100000 else "big/nan"
                        print(f"  {pname:45s} +0x{off:04X}: int={vi:8d}  float={vf_s}")

kernel32.CloseHandle(hp)
print("\nDone!")
