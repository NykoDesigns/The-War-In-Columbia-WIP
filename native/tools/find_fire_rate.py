"""Find the fire rate mechanism in BioShock Infinite.
1. Scan GNames for ALL fire/rate/interval related names
2. Walk XWeapon UClass property chain from the class object itself
3. Also check the parent class chain (Weapon -> Inventory -> Actor)
"""
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

def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(br)):
        return buf.raw[:br.value]
    return None

def read_u32(h, addr):
    d = read_mem(h, addr, 4)
    return struct.unpack('<I', d)[0] if d and len(d) == 4 else None

def read_i32(h, addr):
    d = read_mem(h, addr, 4)
    return struct.unpack('<i', d)[0] if d and len(d) == 4 else None

pid = find_pid('BioShockInfinite.exe')
if not pid: print("Game not running!"); sys.exit(1)

h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
psapi = ctypes.windll.psapi
hMods = (ctypes.c_void_p * 1024)()
cb = wt.DWORD()
psapi.EnumProcessModules(h, hMods, ctypes.sizeof(hMods), ctypes.byref(cb))
base = hMods[0]

RVA_GNames = 0xF9DFEC
OFF_FNE_Flags = 0x08; OFF_FNE_Str = 0x10
OFF_Name = 0x18; OFF_Class = 0x20

gnames = read_u32(h, base + RVA_GNames)
print(f"Base=0x{base:08X}, GNames=0x{gnames:08X}")

def resolve_fname(index):
    if index < 0 or index > 0x400000: return None
    ep = read_u32(h, gnames + index * 4)
    if not ep: return None
    flags = read_u32(h, ep + OFF_FNE_Flags)
    if flags is None: return None
    sa = ep + OFF_FNE_Str
    if flags & 1:
        d = read_mem(h, sa, 512)
        if not d: return None
        try:
            end = d.index(b'\x00\x00')
            if end % 2 == 1: end += 1
            return d[:end].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(h, sa, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

# Scan ALL GNames for fire/rate/interval/cooldown related entries
print("\n=== Scanning full GNames table for fire/rate properties ===")
fire_names = {}
for i in range(500000):
    name = resolve_fname(i)
    if not name: continue
    nl = name.lower()
    if any(k in nl for k in ['fireinterval', 'firerate', 'rateoffire', 'fireperiod',
                               'firetim', 'firefreq', 'firedelay', 'refiretime',
                               'refire', 'burstrate', 'burstdelay', 'burstinterval',
                               'cycletime', 'cycletim', 'shotdelay', 'shotinterval',
                               'timebetween', 'roundsper', 'shotspersec']):
        fire_names[name] = i
        print(f"  FName[{i}] = '{name}'")

# Also find vigor energy / salt drain related
print("\n=== Salt/Energy drain related FNames ===")
salt_names = {}
for i in range(500000):
    name = resolve_fname(i)
    if not name: continue
    nl = name.lower()
    if any(k in nl for k in ['vigorenergy', 'saltcost', 'saltdrain', 'saltsper',
                               'energycost', 'energydrain', 'energyper',
                               'ammocostper', 'costperuse', 'costpershot',
                               'plasmidenergy', 'plasmidcost', 'healthbattery',
                               'drainrate', 'energyrate']):
        if name not in salt_names:
            salt_names[name] = i
            print(f"  FName[{i}] = '{name}'")

# Now walk the XWeapon class (found at 0x16EE6B20) from the beginning
# Let me find the Children pointer (first property in the class definition)
XWEAPON_CLASS = 0x16EE6B20
print(f"\n=== Exploring XWeapon UClass at 0x{XWEAPON_CLASS:08X} ===")

# UClass extends UStruct extends UField extends UObject
# UStruct has: Children (UField*) and SuperField (UStruct*)
# Let me dump the UClass and find these pointers
cls_data = read_mem(h, XWEAPON_CLASS, 512)
if cls_data:
    print("XWeapon UClass fields (looking for Children, SuperField, PropertyLink):")
    for off in range(0, 512, 4):
        val = struct.unpack_from('<I', cls_data, off)[0]
        if val > 0x10000000 and val < 0x7FFF0000:
            ni = read_i32(h, val + OFF_Name)
            if ni and 0 < ni < 500000:
                name = resolve_fname(ni)
                if name:
                    ci = read_u32(h, val + OFF_Class)
                    cn = None
                    if ci:
                        cni = read_i32(h, ci + OFF_Name)
                        cn = resolve_fname(cni) if cni else None
                    if cn:
                        # Only print interesting ones
                        if 'Property' in cn or cn == 'Class' or cn == 'Function' or cn == 'ScriptStruct':
                            print(f"  +0x{off:03X}: -> '{name}' ({cn}) @ 0x{val:08X}")

# Try to find the SuperField (parent class) - should be "Weapon" class
print(f"\n=== Looking for parent class chain ===")
for off in range(0x28, 0x80, 4):
    val = struct.unpack_from('<I', cls_data, off)[0]
    if val > 0x10000000 and val < 0x7FFF0000:
        ni = read_i32(h, val + OFF_Name)
        if ni and 0 < ni < 500000:
            name = resolve_fname(ni)
            ci = read_u32(h, val + OFF_Class)
            cn = None
            if ci:
                cni = read_i32(h, ci + OFF_Name)
                cn = resolve_fname(cni) if cni else None
            if cn == 'Class':
                print(f"  +0x{off:02X}: SuperClass? -> '{name}' (Class) @ 0x{val:08X}")
                # Check if this is the Weapon parent
                # Walk one more level
                parent_data = read_mem(h, val, 128)
                if parent_data:
                    for off2 in range(0x28, 0x80, 4):
                        val2 = struct.unpack_from('<I', parent_data, off2)[0]
                        if val2 > 0x10000000 and val2 < 0x7FFF0000:
                            ni2 = read_i32(h, val2 + OFF_Name)
                            if ni2 and 0 < ni2 < 500000:
                                name2 = resolve_fname(ni2)
                                ci2 = read_u32(h, val2 + OFF_Class)
                                cn2 = None
                                if ci2:
                                    cni2 = read_i32(h, ci2 + OFF_Name)
                                    cn2 = resolve_fname(cni2) if cni2 else None
                                if cn2 == 'Class' and name2:
                                    print(f"    +0x{off2:02X}: -> '{name2}' (Class)")

kernel32.CloseHandle(h)
print("\nDone!")
