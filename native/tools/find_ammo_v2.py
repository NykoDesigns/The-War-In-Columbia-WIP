"""Find ammo/clip offsets by looking at ALL different int values across weapon archetypes.
Focus on small positive ints that differ between weapons in expected ways."""
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

# Known weapon archetype addresses (from this session)
weapons = {
    'MachineGunBase': 0x62AF8000,
    'PistolBase':     0x65095000,
    'ShotgunBase':    0x6509A000,
    'CarbineBase':    0x65092000,
    'HandCannonBase': 0x6509E000,
    'RPGBase':        0x65097000,
    'SniperBase':     0x6509B000,
    'GatlingGun':     0x6521E000,
    'FlakCannon':     0x65091000,
}

# Read data
weapon_data = {}
for name, addr in weapons.items():
    data = read_mem(hp, addr, 0xA000)  # read more: 40KB per weapon
    if data and len(data) >= 0xA000:
        weapon_data[name] = data

print(f"Read data for {len(weapon_data)} weapons")

# Strategy: find offsets where weapons have DIFFERENT small positive integers
# that could be clip/ammo values (range 1-500)
# Require: at least 4 weapons have values in range AND they differ
print("\n=== Offsets with different clip-like integers (1-500) across weapons ===")
print(f"{'Offset':>8s}", end='')
for w in sorted(weapon_data.keys()):
    print(f"  {w:>14s}", end='')
print()

ammo_candidates = []
for off in range(0, 0xA000 - 4, 4):
    vals = {}
    for w in sorted(weapon_data.keys()):
        v = struct.unpack_from('<i', weapon_data[w], off)[0]
        if 1 <= v <= 500:
            vals[w] = v
    
    if len(vals) >= 5:
        unique_vals = set(vals.values())
        if len(unique_vals) >= 3:  # At least 3 different values
            # Check if MachineGun is higher than Pistol for clip, or vice versa
            mg = vals.get('MachineGunBase', 0)
            pi = vals.get('PistolBase', 0)
            sg = vals.get('ShotgunBase', 0)
            rpg = vals.get('RPGBase', 0)
            
            # Clip-like: MG > Pistol > Shotgun, RPG is small
            clip_like = (mg > 0 and pi > 0 and sg > 0 and rpg > 0 and
                        mg > sg and pi > rpg)
            
            # Reserve-like: MG is largest
            reserve_like = (mg > 0 and pi > 0 and mg > pi and mg >= 50)
            
            if clip_like or reserve_like:
                tag = ""
                if clip_like and mg > pi and pi >= sg: tag = " *** CLIP? ***"
                if reserve_like and mg >= 100: tag = " *** RESERVE? ***"
                
                print(f"+0x{off:04X}:", end='')
                for w in sorted(weapon_data.keys()):
                    v = vals.get(w, '-')
                    print(f"  {str(v):>14s}", end='')
                print(tag)
                ammo_candidates.append((off, vals, tag))

# Also try float interpretation for ammo (some games store as float)
print("\n=== Offsets with different ammo-like FLOATS (1-500, integer-valued) ===")
for off in range(0, 0xA000 - 4, 4):
    vals = {}
    for w in sorted(weapon_data.keys()):
        f = struct.unpack_from('<f', weapon_data[w], off)[0]
        if f == f and 1.0 <= f <= 500.0 and f == int(f):
            vals[w] = int(f)
    
    if len(vals) >= 5:
        unique_vals = set(vals.values())
        if len(unique_vals) >= 3:
            mg = vals.get('MachineGunBase', 0)
            pi = vals.get('PistolBase', 0)
            sg = vals.get('ShotgunBase', 0)
            rpg = vals.get('RPGBase', 0)
            
            if mg > 0 and pi > 0 and sg > 0 and rpg > 0 and mg > sg and pi > rpg:
                tag = ""
                if mg > pi and pi >= sg: tag = " *** CLIP? ***"
                if mg >= 100 and mg > pi: tag = " *** RESERVE? ***"
                
                print(f"+0x{off:04X}:", end='')
                for w in sorted(weapon_data.keys()):
                    v = vals.get(w, '-')
                    print(f"  {str(v):>14s}", end='')
                print(tag)

kernel32.CloseHandle(hp)
print("\nDone!")
