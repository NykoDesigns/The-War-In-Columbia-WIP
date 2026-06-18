"""Find all XWeapon subclass names and Possession-related FNames."""
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

# Part 1: Find all XWeapon* class names
print("=== All XWeapon* FNames ===")
xweapon_classes = {}
for i in range(200000):
    n = rfn(i)
    if n and n.startswith('XWeapon'):
        print(f"  [{i:6d}] {n}")
        xweapon_classes[n] = i

# Part 2: Find Possession plasmid FNames
print("\n=== Possession-related Plasmid FNames ===")
possess_fnames = []
for i in range(200000):
    n = rfn(i)
    if not n: continue
    nl = n.lower()
    if 'plasmid' in nl and ('possess' in nl or 'domin' in nl or 'control' in nl):
        print(f"  [{i:6d}] {n}")
        possess_fnames.append((i, n))

# Part 3: Find ALL Plasmid_ weapon FNames
print("\n=== All Plasmid_ FNames ===")
all_plasmid = []
for i in range(100000):
    n = rfn(i)
    if n and n.startswith('Plasmid_') and not any(x in n for x in ['FPModel', 'TPModel', 'Prox', 'Fire', 'Idle', 'Anim', 'SFX', 'Unlock', 'Multiple']):
        print(f"  [{i:6d}] {n}")
        all_plasmid.append((i, n))

kernel32.CloseHandle(hp)
