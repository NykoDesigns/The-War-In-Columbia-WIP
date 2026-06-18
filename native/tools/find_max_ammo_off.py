"""Find MaxAmmoCountAttrib and MaxSpareAmmoCountAttrib offsets."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
def find_pid(name):
    out = subprocess.check_output(['tasklist','/FI',f'IMAGENAME eq {name}','/FO','CSV','/NH'],text=True)
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
if not pid:
    print("Game not running!"); sys.exit(1)
hp = kernel32.OpenProcess(0x1F0FFF, False, pid)  # PROCESS_ALL_ACCESS
# Get base address: read PEB
import ctypes.wintypes
ntdll = ctypes.windll.ntdll

class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("Reserved1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                ("Reserved2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.POINTER(ctypes.c_ulong)),
                ("Reserved3", ctypes.c_void_p)]

pbi = PROCESS_BASIC_INFORMATION()
ntdll.NtQueryInformationProcess(hp, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None)
peb_addr = pbi.PebBaseAddress
# PEB->Ldr at +0x0C, then InLoadOrderModuleList at +0x0C
# Or simpler: PEB->ImageBaseAddress at +0x08
base_data = read_mem(hp, peb_addr + 0x08, 4)
base = struct.unpack('<I', base_data)[0]
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

xwc = 0x16566B20
child = read32(hp, xwc + 0x38)
vis = set()
ct = 0
while child and child > 0x10000 and child < 0xFFFF0000 and child not in vis and ct < 1000:
    vis.add(child)
    ct += 1
    ni = read32(hp, child + 0x18)
    n = rfn(ni)
    if n and ('MaxAmmo' in n or 'MaxSpare' in n or 'Ammo' in n or 'Spare' in n or 'Clip' in n or 'Magazine' in n or 'Reload' in n or 'Rounds' in n):
        off48 = read32(hp, child + 0x48)
        sz30 = read32(hp, child + 0x30)
        cls = read32(hp, child + 0x20)
        cn = rfn(read32(hp, cls + 0x18)) if cls else ''
        print(f"  {n:45s} +0x{off48:04X}  size={sz30:3d}  ({cn})")
    child = read32(hp, child + 0x28)

# Also read the MachineGunBase to check values at the discovered offsets
mg_addr = 0x62B7D000  # from previous scan
mg_data = read_mem(hp, mg_addr, 0xC00)
if mg_data:
    print(f"\nMachineGunBase @ 0x{mg_addr:08X} values:")
    for off_name, off in [("AmmoCount", 0x07C4), ("SpareAmmoCount", 0x07EC),
                          ("RoundsPerAmmoBunch", 0x07C0), ("ReloadAmmoCount", 0x07B0)]:
        if off < len(mg_data) - 4:
            vi = struct.unpack_from('<i', mg_data, off)[0]
            print(f"  {off_name:30s} +0x{off:04X}: {vi}")
    # Check region around MaxAmmoCountAttrib
    print("\n  Values around +0x07C0-0x0860:")
    for off in range(0x07B0, 0x0860, 4):
        if off < len(mg_data) - 4:
            vi = struct.unpack_from('<i', mg_data, off)[0]
            vf = struct.unpack_from('<f', mg_data, off)[0]
            vf_s = f"{vf:.2f}" if vf == vf and abs(vf) < 100000 else "big/nan"
            if vi != 0:
                print(f"    +0x{off:04X}: int={vi:10d}  float={vf_s}")

kernel32.CloseHandle(hp)
