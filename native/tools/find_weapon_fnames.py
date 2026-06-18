"""Search for weapon and vigor FName entries in the running game process."""
import ctypes, ctypes.wintypes as wt, subprocess, re

kernel32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD),
    ]

def find_pid(name):
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for line in out.strip().split('\n'):
        if name.lower() in line.lower():
            return int(line.strip().split(',')[1].strip('"'))
    return None

pid = find_pid('BioShockInfinite.exe')
if not pid:
    print("Game not running!"); exit(1)

hProcess = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)

# Search for various weapon/vigor related strings in both UTF-16 and ASCII
search_terms = [
    # Weapon names (internal)
    "MachineGun", "Machine_Gun", "Triple_R", "TripleR",
    "Repeater", "Carbine", "HandCannon", "Broadsider",
    "Burstgun", "BurstGun", "Hailfire", "HailFire",
    "Heater", "Huntsman", "Paddywhacker",
    "Blunderbuss", "Peppermill", "PepperMill",
    "CrankGun", "Crank_Gun", "GatlingGun", "Gatling",
    "PortableGatlingGun",
    "Barnstormer", "Volley", "VolleyGun",
    "Pistol", "Shotgun", "Sniper", "RPG",
    # Vigor names
    "MurderOfCrows", "DevilsKiss", "BuckingBronco",
    "ShockJockey", "Possession", "Undertow", "Charge",
    "ReturnToSender", "OldManWinter",
    # Property names
    "FireInterval", "FireRate", "RateOfFire",
    "AmmoPerShot", "AmmoUsedPerShot", "SaltsPerUse",
    "AmmoCost", "SaltCost", "ManaCost", "EnergyCost",
    "MaxAmmo", "ClipSize", "MagSize", "ReloadTime",
    "SpreadMin", "SpreadMax", "InstantHitDamage",
    "PlasmidAmmo", "PlasmidAmmoCost", "PlasmidEnergyCost",
    "VigorAmmoCost", "CostPerShot", "CostPerUse",
]

mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)

results = {}
for term in search_terms:
    results[term] = {'utf16': 0, 'ascii': 0}

addr = 0
while addr < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    base = mbi.BaseAddress or 0
    region_end = base + mbi.RegionSize
    if region_end <= addr: break

    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        for offset in range(0, mbi.RegionSize, 0x10000):
            read_addr = base + offset
            to_read = min(0x10000, mbi.RegionSize - offset)
            buf = ctypes.create_string_buffer(to_read)
            if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                data = buf.raw[:bytes_read.value]
                for term in search_terms:
                    needle_a = term.encode('ascii')
                    needle_w = term.encode('utf-16-le')
                    idx = 0
                    while True:
                        idx = data.find(needle_a, idx)
                        if idx == -1: break
                        results[term]['ascii'] += 1
                        idx += 1
                    idx = 0
                    while True:
                        idx = data.find(needle_w, idx)
                        if idx == -1: break
                        results[term]['utf16'] += 1
                        idx += 2
    addr = region_end

kernel32.CloseHandle(hProcess)

print("=== FName/Property Search Results ===")
for term in search_terms:
    a = results[term]['ascii']
    w = results[term]['utf16']
    if a > 0 or w > 0:
        print(f"  {term:35s} ASCII={a:4d}  UTF16={w:4d}")
