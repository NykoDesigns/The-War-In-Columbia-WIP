"""Dump Bucking Bronco (XWeaponRollingThunder) instances and compare with Devil's Kiss."""
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
base = None
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value: base = mod; break
if not base: base = hMods[0]
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

def resolve_obj(addr):
    """Resolve UObject at addr to (name, class_name)"""
    if not addr or addr < 0x10000: return None, None
    d = read_mem(hp, addr + 0x18, 8)
    if not d: return None, None
    ni = struct.unpack_from('<i', d, 0)[0]
    nn = struct.unpack_from('<i', d, 4)[0]
    name = rfn(ni)
    if not name: return None, None
    cp = read32(hp, addr + 0x20)
    cls = None
    if cp:
        cd = read_mem(hp, cp + 0x18, 4)
        if cd: cls = rfn(struct.unpack_from('<i', cd)[0])
    return f"{name}_{nn}", cls

# Known addresses from previous scan
targets = {
    'Plasmid_BuckingBroncoBase': 0x36BDF000,
    'Plasmid_BuckingBroncoFounder': 0x77492000,
    'Plasmid_DevilsKiss': 0x77496000,
}

for label, addr in targets.items():
    data = read_mem(hp, addr, 0x1000)
    if not data:
        print(f"\n{label} @ 0x{addr:08X}: FAILED TO READ")
        continue
    
    # Verify
    ni = struct.unpack_from('<i', data, 0x18)[0]
    name = rfn(ni)
    cp = struct.unpack_from('<I', data, 0x20)[0]
    _, cls = resolve_obj(addr)
    arch = struct.unpack_from('<I', data, 0x24)[0]
    _, arch_cls = resolve_obj(arch) if arch else (None, None)
    arch_name, _ = resolve_obj(arch) if arch else (None, None)
    
    print(f"\n{'='*80}")
    print(f"{label} @ 0x{addr:08X}")
    print(f"  FName: {name}, Class: {cls}, Archetype: {arch_name}")
    print(f"{'='*80}")
    
    # Dump known weapon offsets
    fire_interval = struct.unpack_from('<f', data, 0x0240)[0]
    salt_tap = struct.unpack_from('<f', data, 0x02BC)[0]
    salt_held = struct.unpack_from('<f', data, 0x039C)[0]
    print(f"  FireInterval={fire_interval:.3f}  SaltTap={salt_tap:.1f}  SaltHeld={salt_held:.1f}")
    
    # Dump ALL pointer-like values that resolve to named objects
    # Extended range to cover subclass-specific fields
    print(f"\n  All named object pointers (+0x100 to +0x800):")
    for off in range(0x100, min(0x800, len(data) - 4), 4):
        val = struct.unpack_from('<I', data, off)[0]
        if val < 0x10000 or val > 0x7FFF0000: continue
        obj_name, obj_cls = resolve_obj(val)
        if obj_name and len(obj_name) > 2 and len(obj_name) < 100 and obj_cls:
            # Filter out noise - only show interesting classes
            if any(k in (obj_cls or '') for k in ['Damage', 'Projectile', 'Effect', 'Particle',
                                                    'Status', 'Rolling', 'Weapon', 'Family',
                                                    'Archetype', 'Anim', 'Pawn', 'Sound',
                                                    'AK', 'Actor', 'Component', 'Template']):
                print(f"    +0x{off:04X}: -> {obj_name:50s} (class: {obj_cls})")
            # Also show DamageType specifically
            elif 'Damage' in obj_name:
                print(f"    +0x{off:04X}: -> {obj_name:50s} (class: {obj_cls})")

    # Now dump the DamageType objects themselves to find fire-related properties
    # Check +0x0228 (tap damage type) and +0x0308 (hold damage type) 
    for dt_off, dt_label in [(0x0228, "TapDamageType"), (0x0308, "HoldDamageType")]:
        dt_ptr = struct.unpack_from('<I', data, dt_off)[0]
        if dt_ptr < 0x10000: continue
        dt_name, dt_cls = resolve_obj(dt_ptr)
        if not dt_name: continue
        print(f"\n  {dt_label} @ +0x{dt_off:04X}: {dt_name} (class: {dt_cls})")
        
        # Read the DamageType object
        dt_data = read_mem(hp, dt_ptr, 0x200)
        if not dt_data: continue
        
        # Dump floats and ints in the first 0x100 bytes
        print(f"    Raw dump (first 0x100 bytes, pointer-resolved):")
        for j in range(0x28, min(0x100, len(dt_data) - 4), 4):
            vi = struct.unpack_from('<i', dt_data, j)[0]
            vf = struct.unpack_from('<f', dt_data, j)[0]
            # Check if it's a pointer to a named object
            if 0x10000 < vi < 0x7FFF0000:
                pn, pc = resolve_obj(vi)
                if pn and pc:
                    print(f"      +0x{j:04X}: -> {pn} ({pc})")
                    continue
            # Show non-zero float/int values
            if vi != 0:
                vf_s = f"{vf:.3f}" if vf == vf and abs(vf) < 100000 else f"0x{vi:08X}"
                print(f"      +0x{j:04X}: int={vi:8d}  float={vf_s}")

kernel32.CloseHandle(hp)
print("\nDone!")
