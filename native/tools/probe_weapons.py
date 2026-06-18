"""Probe weapon instances to find fire rate and vigor energy values.
Read the FireMode StructProperty offset, then read actual values on weapon instances."""
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

def read_u32(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<I', d)[0] if d and len(d) == 4 else None

def read_i32(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<i', d)[0] if d and len(d) == 4 else None

def read_float(hp, addr):
    d = read_mem(hp, addr, 4)
    return struct.unpack('<f', d)[0] if d and len(d) == 4 else None

pid = find_pid('BioShockInfinite.exe')
if not pid: print("Game not running!"); sys.exit(1)

hp = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cb = wt.DWORD()
psapi.EnumProcessModules(hp, hMods, ctypes.sizeof(hMods), ctypes.byref(cb))
base = hMods[0]

gnames = read_u32(hp, base + 0xF9DFEC)

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    ep = read_u32(hp, gnames + index * 4)
    if not ep: return None
    flags = read_u32(hp, ep + 0x08)
    if flags is None: return None
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

# 1. Read the FireMode StructProperty at 0x1724A73C
FIREMODE_PROP = 0x1724A73C
print("=== FireMode StructProperty ===")
fm_data = read_mem(hp, FIREMODE_PROP, 128)
if fm_data:
    fm_name_idx = struct.unpack_from('<I', fm_data, 0x18)[0]
    fm_name = resolve_fname(fm_name_idx)
    print(f"  Name: '{fm_name}' (FName idx={fm_name_idx})")
    fm_offset = struct.unpack_from('<I', fm_data, 0x5C)[0]
    fm_elemsize = struct.unpack_from('<I', fm_data, 0x30)[0]
    fm_arrdim = struct.unpack_from('<I', fm_data, 0x2C)[0]
    print(f"  Offset: 0x{fm_offset:04X}")
    print(f"  ElementSize: {fm_elemsize}")
    print(f"  ArrayDim: {fm_arrdim}")
    
    # The Outer should be XWeapon
    fm_outer = read_u32(hp, FIREMODE_PROP + 0x14)
    if fm_outer:
        oni = read_i32(hp, fm_outer + 0x18)
        on = resolve_fname(oni) if oni else None
        print(f"  Outer: '{on}' @ 0x{fm_outer:08X}")

# 2. Read the StandardFireDelay UProperty at 0x1724B124
SFD_PROP = 0x1724B124
print("\n=== StandardFireDelay UProperty ===")
sfd_data = read_mem(hp, SFD_PROP, 128)
if sfd_data:
    sfd_offset = struct.unpack_from('<I', sfd_data, 0x5C)[0]
    sfd_name_idx = struct.unpack_from('<I', sfd_data, 0x18)[0]
    sfd_name = resolve_fname(sfd_name_idx)
    sfd_outer = read_u32(hp, SFD_PROP + 0x14)
    sfd_outer_name = None
    if sfd_outer:
        oni = read_i32(hp, sfd_outer + 0x18)
        sfd_outer_name = resolve_fname(oni) if oni else None
    print(f"  Name: '{sfd_name}'")
    print(f"  Offset (within struct): 0x{sfd_offset:04X}")
    print(f"  Outer: '{sfd_outer_name}' @ 0x{sfd_outer:08X}")

# 3. Walk the XWeaponFireMode struct properties to find ALL fire timing fields
print("\n=== Walking XWeaponFireMode struct properties ===")
# The StandardFireDelay is one property. Let's walk from it using Next (+0x28)
cur = SFD_PROP
count = 0
firemode_props = []
while cur and count < 200:
    name_idx = read_i32(hp, cur + 0x18)
    if not name_idx: break
    name = resolve_fname(name_idx)
    if not name: break
    
    cls_ptr = read_u32(hp, cur + 0x20)
    cn = None
    if cls_ptr:
        cni = read_i32(hp, cls_ptr + 0x18)
        cn = resolve_fname(cni) if cni else None
    
    offset_val = read_u32(hp, cur + 0x5C)
    elem_size = read_u32(hp, cur + 0x30)
    
    nl = name.lower()
    interesting = any(k in nl for k in ['fire', 'time', 'delay', 'interval', 'rate', 'burst',
                                          'cooldown', 'refire', 'cycle', 'standard', 'damage',
                                          'ammo', 'cost', 'spread', 'range', 'vigor', 'energy',
                                          'overheat', 'heat'])
    if interesting:
        print(f"  [{count:3d}] {cn:20s} '{name}' offset=0x{offset_val:04X} size={elem_size}")
    
    firemode_props.append((name, cn, offset_val, elem_size))
    
    next_ptr = read_u32(hp, cur + 0x28)
    if not next_ptr or next_ptr == cur: break
    cur = next_ptr
    count += 1

print(f"  Total XWeaponFireMode properties: {count}")

# 4. Now probe the MachineGun weapon instances
# Known instances from previous scan:
weapon_addrs = {
    'MachineGunBase_0': 0x68D34000,
    'MachineGunFounder_0': 0x68D37000,
    'MachineGunVP_0': 0x7DBC0000,
    'XAI_GunnerBeta_MachineGun_0': 0x68D49000,
    'CarbineBase_0': 0x68D45000,
    'PistolBase_0': 0x3666E000,
    'Plasmid_DevilsKiss_0': 0x7DBC8000,
    'Plasmid_EnrageBase_0': 0x36662000,
}

print(f"\n=== Probing weapon instances for fire rate values ===")
if fm_data:
    fm_base = struct.unpack_from('<I', fm_data, 0x5C)[0]
    print(f"FireMode struct base offset in XWeapon: 0x{fm_base:04X}")
    print(f"StandardFireDelay offset within struct: 0x{sfd_offset:04X}")
    
    # For struct properties in UE3, the Offset field on the StructProperty gives
    # the absolute offset from the object start. Inner property offsets are relative
    # to the struct start.
    # BUT this depends on how UE3 handles struct offsets...
    
    # Let's try both absolute and relative interpretations
    for wname, waddr in weapon_addrs.items():
        print(f"\n  {wname} @ 0x{waddr:08X}:")
        
        # Try reading fire-related floats at various candidate offsets
        # If fm_base is the absolute offset of FireMode in the weapon,
        # then StandardFireDelay would be at fm_base + sfd_offset (if relative)
        # or just sfd_offset (if absolute)
        
        candidates = []
        # Interpretation A: sfd_offset is absolute (from weapon start)
        candidates.append(('AbsoluteOffset', sfd_offset))
        # Interpretation B: sfd_offset is relative to struct start
        candidates.append(('fm_base+sfd', fm_base + sfd_offset))
        
        # Also try scanning a range around the likely area for float values
        # that look like fire intervals (0.01 - 2.0 seconds)
        for label, off in candidates:
            val = read_float(hp, waddr + off)
            if val is not None:
                print(f"    {label} (0x{off:04X}): {val:.6f}")
        
        # Brute force: scan ALL floats in the property area for fire-interval-like values
        # Look at fire-related offsets from the struct walk
        for pn, cn, poff, psz in firemode_props:
            if 'fire' in pn.lower() or 'delay' in pn.lower() or 'time' in pn.lower() or 'standard' in pn.lower():
                if psz == 4:  # float-sized
                    for test_base in [0, fm_base]:
                        val = read_float(hp, waddr + test_base + poff)
                        if val is not None and 0.001 < abs(val) < 100.0:
                            print(f"    {pn} (base=0x{test_base:X}+0x{poff:04X}=0x{test_base+poff:04X}): {val:.6f}")

kernel32.CloseHandle(hp)
print("\nDone!")
