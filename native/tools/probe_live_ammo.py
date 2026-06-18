"""Probe a live machine gun instance to find actual ammo offsets.
Reads the full weapon object and compares with archetype to find differences."""
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

# Find XWeapon class
xweapon_idx = -1
for i in range(200000):
    name = resolve_fname(i)
    if name == 'XWeapon':
        xweapon_idx = i
        break

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100

mbi = MEMORY_BASIC_INFORMATION()

# Find XWeapon class
xweapon_class = None
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan: break
    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x28, 4):
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

print(f"XWeapon class @ 0x{xweapon_class:08X}")

# Find ALL XWeapon instances
weapons = {}
scan = 0x10000
while scan < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hp, ctypes.c_void_p(scan), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0: break
    region_end = (mbi.BaseAddress or 0) + mbi.RegionSize
    if region_end <= scan: break
    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD) and (mbi.Protect & 0x6C):
        data = read_mem(hp, mbi.BaseAddress or 0, min(mbi.RegionSize, 0x1000000))
        if data:
            for i in range(0, len(data) - 0x800, 4):
                if struct.unpack_from('<I', data, i + 0x20)[0] != xweapon_class: continue
                name_idx = struct.unpack_from('<i', data, i + 0x18)[0]
                name_num = struct.unpack_from('<i', data, i + 0x1C)[0]
                if name_idx < 0 or name_idx > 500000: continue
                name = resolve_fname(name_idx)
                if not name: continue
                addr = (mbi.BaseAddress or 0) + i
                key = f"{name}_{name_num}"
                weapons[key] = addr
    scan = region_end

# Identify machine gun archetypes and instances
mg_archetypes = {}
mg_instances = {}
for key, addr in weapons.items():
    if 'MachineGun' in key or 'Gatling' in key:
        mg_archetypes[key] = addr
    else:
        # Check archetype chain
        arch_data = read_mem(hp, addr + 0x24, 4)
        if arch_data:
            arch_ptr = struct.unpack('<I', arch_data)[0]
            if arch_ptr in mg_archetypes.values():
                mg_instances[key] = addr
            elif arch_ptr:
                arch2_data = read_mem(hp, arch_ptr + 0x24, 4)
                if arch2_data:
                    arch2 = struct.unpack('<I', arch2_data)[0]
                    if arch2 in mg_archetypes.values():
                        mg_instances[key] = addr

print(f"\nMG Archetypes: {list(mg_archetypes.keys())}")
print(f"MG Live Instances: {list(mg_instances.keys())}")

# Read and compare data between archetype and a live instance
# Focus on offsets 0x0200-0x0A00 for ammo-like values
if mg_archetypes and mg_instances:
    arch_key = next(k for k in mg_archetypes if 'Base' in k or 'Founder' in k)
    inst_key = next(iter(mg_instances))
    arch_addr = mg_archetypes[arch_key]
    inst_addr = mg_instances[inst_key]
    
    arch_data = read_mem(hp, arch_addr, 0xA000)
    inst_data = read_mem(hp, inst_addr, 0xA000)
    
    if arch_data and inst_data:
        print(f"\nComparing {arch_key} @ 0x{arch_addr:08X} vs {inst_key} @ 0x{inst_addr:08X}")
        print(f"\n{'Offset':>8s}  {'Arch(int)':>10s} {'Arch(flt)':>10s}  {'Inst(int)':>10s} {'Inst(flt)':>10s}  Note")
        
        for off in range(0x0200, 0x0A00, 4):
            ai = struct.unpack_from('<i', arch_data, off)[0]
            af = struct.unpack_from('<f', arch_data, off)[0]
            ii = struct.unpack_from('<i', inst_data, off)[0]
            if_val = struct.unpack_from('<f', inst_data, off)[0]
            
            # Only show interesting offsets
            show = False
            note = ""
            
            # Show if either has a small positive int (ammo-like)
            if (1 <= ai <= 1000 and ai != ii) or (1 <= ii <= 1000 and ai != ii):
                show = True
                note = "INT differs"
            
            # Show known offsets
            if off in [0x0240, 0x02BC, 0x039C, 0x07C0, 0x07D0, 0x07D4, 0x07F8]:
                show = True
                note += " KNOWN"
            
            # Show if float is ammo-like and differs
            if (af == af and 1.0 <= af <= 1000.0 and if_val == if_val and 1.0 <= if_val <= 1000.0 and abs(af - if_val) > 0.5):
                show = True
                note += " FLOAT-DIFF"
            
            if show:
                af_s = f"{af:.1f}" if af == af and abs(af) < 10000 else "NaN/big"
                if_s = f"{if_val:.1f}" if if_val == if_val and abs(if_val) < 10000 else "NaN/big"
                print(f"  +0x{off:04X}  {ai:10d} {af_s:>10s}  {ii:10d} {if_s:>10s}  {note}")

# Also just dump all small positive ints on the live MG instance
if mg_instances:
    inst_key = next(iter(mg_instances))
    inst_addr = mg_instances[inst_key]
    inst_data = read_mem(hp, inst_addr, 0xA000)
    if inst_data:
        print(f"\n=== All small positive ints (1-1000) on live instance {inst_key} ===")
        for off in range(0, 0xA000 - 4, 4):
            v = struct.unpack_from('<i', inst_data, off)[0]
            f = struct.unpack_from('<f', inst_data, off)[0]
            # Show if it looks like clip count (20-50) or reserve (50-250)
            if v in [35, 45, 20, 30, 100, 105, 175, 215, 900]:
                print(f"  +0x{off:04X}: int={v}, float={f:.4f}")

print("\n=== Checking what the player currently sees ===")
# Look for the PLAYER's weapon — should have ammo count matching HUD
# Find all MG-type instances and show their clip/reserve values
for key, addr in sorted({**mg_archetypes, **mg_instances}.items()):
    data = read_mem(hp, addr, 0x0A00)
    if not data: continue
    # Check several candidate offsets for ammo
    print(f"\n  {key} @ 0x{addr:08X}:")
    for off in [0x07C0, 0x07C4, 0x07C8, 0x07CC, 0x07D0, 0x07D4, 0x07D8, 0x07DC,
                0x07E0, 0x07E4, 0x07E8, 0x07EC, 0x07F0, 0x07F4, 0x07F8, 0x07FC, 0x0800]:
        vi = struct.unpack_from('<i', data, off)[0]
        vf = struct.unpack_from('<f', data, off)[0]
        vf_s = f"{vf:.2f}" if vf == vf and abs(vf) < 100000 else "big/nan"
        if 0 < vi < 10000 or off in [0x07C0, 0x07D0, 0x07F8]:
            print(f"    +0x{off:04X}: int={vi:6d}  float={vf_s}")

kernel32.CloseHandle(hp)
print("\nDone!")
