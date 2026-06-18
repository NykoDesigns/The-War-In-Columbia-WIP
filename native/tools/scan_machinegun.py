"""Directly scan MachineGun weapon instances for fire-rate float values.
Also scan for vigor salt cost values on vigor weapon instances.
Strategy: dump large range of weapon memory and look for recognizable patterns."""
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

# First, let's figure out the correct property offset by examining the UProperty 
# layout more carefully. We know SpareAmmoCount is an IntProperty.
# Let me also check field +0x04 which had value 0x9C37 for SpareAmmoCount
# This might be an ObjObjects index.

# Let's read the +0x04 field of several properties and see the pattern
SAC = 0x17248294  # SpareAmmoCount
print("=== Checking UProperty +0x04 field ===")
props_chain = []
cur = SAC
for i in range(20):
    if not cur: break
    ni = read_i32(hp, cur + 0x18)
    name = resolve_fname(ni) if ni else None
    if not name: break
    f04 = read_u32(hp, cur + 0x04)
    f5c = read_u32(hp, cur + 0x5C)
    elem = read_u32(hp, cur + 0x30)
    arr = read_u32(hp, cur + 0x2C)
    print(f"  {name:40s} +0x04={f04:08X} +0x5C={f5c:08X} elem={elem} arr={arr}")
    props_chain.append((name, f04, f5c, elem, arr))
    # Follow Next at +0x28
    next_ptr = read_u32(hp, cur + 0x28)
    if not next_ptr or next_ptr == cur: break
    cur = next_ptr

# The +0x04 values look like GObjObjects indices
# The +0x5C values differ by 1 for consecutive float properties
# This suggests +0x5C might be a DWORD offset (multiply by 4 to get byte offset)

print("\n=== Testing offset interpretations ===")
# Hypothesis: +0x5C * 4 = byte offset in object
# SpareAmmoCount: 0x9C38 * 4 = 0x270E0 = 159,968 bytes
# That seems too large for an object

# Hypothesis: +0x5C is direct byte offset
# SpareAmmoCount: 0x9C38 = 39,992 bytes
# For a deeply inherited class this MIGHT work

# Hypothesis: +0x04 - some_base = property index in memory layout
# SpareAmmoCount: +0x04 = 0x9C37 (differs from +0x5C by 1)

# Let me test by reading weapon instances at both potential offsets
# MachineGunVP_0 showed SpareAmmo=1 at +0x9C38 - let me verify it's valid

MGVP = 0x7DBC0000
print(f"\nMachineGunVP_0 @ 0x{MGVP:08X}:")
# Read 20 ints around offset 0x9C38
for delta in range(-20, 20):
    off = 0x9C38 + delta * 4
    val = read_i32(hp, MGVP + off)
    fval = read_float(hp, MGVP + off)
    if val is not None:
        marker = ""
        if delta == 0: marker = " <-- SpareAmmoCount"
        if fval and 0.01 < abs(fval) < 100 and fval == fval:
            print(f"  +0x{off:05X}: int={val:10d}  float={fval:10.6f}{marker}")
        else:
            print(f"  +0x{off:05X}: int={val:10d}{marker}")

# Now scan a WIDE range of the MachineGun object for fire-interval-like floats
# Machine gun fire interval should be around 0.05-0.15 seconds
print(f"\n=== Scanning MachineGunVP for fire-interval-like floats (0.03-0.20 range) ===")
# Read chunks of the weapon object
for start in range(0, 0x20000, 0x1000):
    data = read_mem(hp, MGVP + start, 0x1000)
    if not data: continue
    for i in range(0, len(data) - 4, 4):
        fval = struct.unpack_from('<f', data, i)[0]
        if fval == fval and 0.03 < fval < 0.20:
            off = start + i
            # Also check if nearby values look like weapon data (damage, range, etc.)
            print(f"  +0x{off:05X}: {fval:.6f}")

# Also scan for small integer values that could be salt/vigor costs (10-100 range)
print(f"\n=== Scanning Plasmid_DevilsKiss for salt cost integers (1-100 range) ===")
DK = 0x7DBC8000
for start in range(0, 0x20000, 0x1000):
    data = read_mem(hp, DK + start, 0x1000)
    if not data: continue
    for i in range(0, len(data) - 4, 4):
        ival = struct.unpack_from('<i', data, i)[0]
        fval = struct.unpack_from('<f', data, i)[0]
        if 10 <= ival <= 100:
            off = start + i
            # Check for nearby VigorEnergy-related pattern  
            if fval != fval or abs(fval) > 1000:  # looks like int, not float
                # Only show if there are other small values nearby
                pass  # too many false positives for ints
        # Better: search for specific known vigor costs as floats
        # Devil's Kiss costs ~14 salts per use
        if fval == fval and 10.0 < fval < 50.0:
            off = start + i
            # Also check as int
            ival2 = struct.unpack_from('<i', data, i)[0]
            if ival2 == int(fval):  # clean integer stored as float
                print(f"  +0x{off:05X}: {fval:.1f} (int={ival2})")

# Compare MachineGun vs Pistol for fire-rate floats
print(f"\n=== Comparing MachineGun vs Pistol at fire-interval-like offsets ===")
PISTOL = 0x3666E000
mg_data = read_mem(hp, MGVP, 0x20000)
p_data = read_mem(hp, PISTOL, 0x20000)
if mg_data and p_data:
    for off in range(0, min(len(mg_data), len(p_data)) - 4, 4):
        mg_f = struct.unpack_from('<f', mg_data, off)[0]
        p_f = struct.unpack_from('<f', p_data, off)[0]
        if mg_f == mg_f and p_f == p_f:
            # Look for offsets where BOTH weapons have small positive floats
            # but they DIFFER (MG faster = smaller interval than pistol)
            if 0.01 < mg_f < 2.0 and 0.01 < p_f < 2.0 and mg_f != p_f:
                print(f"  +0x{off:05X}: MG={mg_f:.6f}  Pistol={p_f:.6f}  ratio={p_f/mg_f:.2f}")

kernel32.CloseHandle(hp)
print("\nDone!")
