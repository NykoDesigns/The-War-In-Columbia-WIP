"""Check fire interval and archetype pointer on ALL XWeapon instances, including None_* ones."""
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

# Known weapon archetype addresses from the scan
archetypes = {
    0x62AF8000: 'MachineGunBase',
    0x62912000: 'MachineGunFounder',
    0x65213000: 'MachineGunVP',
    0x65095000: 'PistolBase',
    0x65219000: 'PistolFounder',
    0x6509A000: 'ShotgunBase',
    0x65098000: 'ShotgunFounder',
    0x6D99E000: 'ShotgunVP',
    0x65092000: 'CarbineBase',
    0x6521D000: 'CarbineFounder',
    0x65215000: 'CarbineVP',
    0x6509E000: 'HandCannonBase',
    0x65212000: 'HandCannonFounder',
    0x65097000: 'RPGBase',
    0x6D990000: 'RPGFounder',
    0x6509B000: 'SniperRifleBase',
    0x6521E000: 'GatlingGun',
    0x65091000: 'FlakCannonBase',
    0x65216000: 'Plasmid_DevilsKiss',
    0x6509C000: 'Plasmid_EnrageBase',
    0x5FA5D000: 'Plasmid_EnrageFounder',
    0x5FA54000: 'Plasmid_VoltSwarmFounder',
}

# All weapon instances from the scan
all_weapons = {
    'CarbineBase_0': 0x65092000,
    'CarbineFounder_0': 0x6521D000,
    'CarbineVP_0': 0x65215000,
    'Default__XWeapon_0': 0x16596C78,
    'FlakCannonBase_0': 0x65091000,
    'FlakCannonFounder_0': 0x6521C000,
    'FlakCannonVP_0': 0x6521B000,
    'GatlingGun_0': 0x6521E000,
    'HandCannonBase_0': 0x6509E000,
    'HandCannonFounder_0': 0x65212000,
    'MachineGunBase_0': 0x62AF8000,
    'MachineGunFounder_0': 0x62912000,
    'MachineGunVP_0': 0x65213000,
    'PistolBase_0': 0x65095000,
    'PistolFounder_0': 0x65219000,
    'Plasmid_DevilsKiss_0': 0x65216000,
    'Plasmid_EnrageBase_0': 0x6509C000,
    'Plasmid_EnrageFounder_0': 0x5FA5D000,
    'Plasmid_VoltSwarmFounder_0': 0x5FA54000,
    'RPGBase_0': 0x65097000,
    'RPGFounder_0': 0x6D990000,
    'ShotgunBase_0': 0x6509A000,
    'ShotgunFounder_0': 0x65098000,
    'ShotgunVP_0': 0x6D99E000,
    'ShotgunVP_BW_0': 0x6D99C000,
    'SniperRifleBase_0': 0x6509B000,
    'SniperRifleFounder_0': 0x6D99D000,
    'XAI_Elizabeth_Weapon_0': 0x62914000,
    'XAI_GunnerBeta_MachineGun_0': 0x6509D000,
    'XAI_ShotgunBeta_Weapon_0': 0x65094000,
    'XWeapon_1': 0x774C7000,
    'None_0': 0x37BD0C98,
    'None_1': 0x36BE1DC4,
    'None_2': 0x36BE1FC4,
}

OFF_FIRE = 0x0240
OFF_ARCHETYPE = 0x24  # ObjectArchetype offset in UObject

print("=== All XWeapon instances: fire interval + archetype ===")
print(f"{'Name':35s} {'Address':>12s} {'FireInterval':>14s} {'Archetype':>12s} {'ArchName':>25s}")
for name in sorted(all_weapons.keys()):
    addr = all_weapons[name]
    data = read_mem(hp, addr, 0x400)
    if not data or len(data) < 0x400:
        continue
    fire = struct.unpack_from('<f', data, OFF_FIRE)[0]
    arch_ptr = struct.unpack_from('<I', data, OFF_ARCHETYPE)[0]
    
    # Resolve archetype name
    arch_name = archetypes.get(arch_ptr, '')
    if not arch_name and arch_ptr:
        arch_data = read_mem(hp, arch_ptr + 0x18, 8)
        if arch_data:
            arch_fname_idx = struct.unpack_from('<i', arch_data)[0]
            arch_fname_num = struct.unpack_from('<i', arch_data, 4)[0]
            aname = resolve_fname(arch_fname_idx)
            if aname:
                arch_name = f"{aname}_{arch_fname_num}"
    
    fire_str = f"{fire:.6f}" if fire == fire and abs(fire) < 100 else "N/A"
    print(f"  {name:35s} 0x{addr:08X}  {fire_str:>14s}  0x{arch_ptr:08X}  {arch_name}")

# Also check what the actual fire rate is on archetypes (after patching)
print("\n=== Archetype fire intervals (should be 0.030 for MG) ===")
for name, addr in sorted(archetypes.items(), key=lambda x: x[1]):
    data = read_mem(hp, addr, 0x400)
    if not data or len(data) < 0x400: continue
    fire = struct.unpack_from('<f', data, OFF_FIRE)[0]
    if fire == fire and abs(fire) < 100:
        print(f"  {name:30s} @ 0x{addr:08X}: {fire:.6f}")

# Check ammo values: scan a wider range on MachineGunBase to find clip-like integers
print("\n=== MachineGunBase: all small positive ints (1-500) in first 0x2000 bytes ===")
mg_addr = 0x62AF8000
mg_data = read_mem(hp, mg_addr, 0x2000)
if mg_data:
    pi_data = read_mem(hp, 0x65095000, 0x2000)  # PistolBase
    sg_data = read_mem(hp, 0x6509A000, 0x2000)  # ShotgunBase
    for off in range(0, 0x2000 - 4, 4):
        mg_val = struct.unpack_from('<i', mg_data, off)[0]
        if 1 <= mg_val <= 500:
            pi_val = struct.unpack_from('<i', pi_data, off)[0] if pi_data else 0
            sg_val = struct.unpack_from('<i', sg_data, off)[0] if sg_data else 0
            # Only show if at least 2 weapons have small positive values
            if 1 <= pi_val <= 500 and 1 <= sg_val <= 500:
                if not (mg_val == pi_val == sg_val):  # skip if all same
                    print(f"  +0x{off:04X}: MG={mg_val:5d}, Pistol={pi_val:5d}, Shotgun={sg_val:5d}")

kernel32.CloseHandle(hp)
print("\nDone!")
