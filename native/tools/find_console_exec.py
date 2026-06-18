"""Find ProcessConsoleExec, DynamicLoadObject, and XCheatManager function addresses."""
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
base_size = 0
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value:
        mi2 = (ctypes.c_void_p * 1)()
        info = ctypes.create_string_buffer(ctypes.sizeof(wt.DWORD) * 3)
        base = mod
        # Get module size
        class MODULEINFO(ctypes.Structure):
            _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD), ("EntryPoint", ctypes.c_void_p)]
        mi_info = MODULEINFO()
        psapi.GetModuleInformation(hp, ctypes.c_void_p(mod), ctypes.byref(mi_info), ctypes.sizeof(mi_info))
        base_size = mi_info.SizeOfImage
        break

print(f"BioShockInfinite.exe base=0x{base:08X} size=0x{base_size:08X}")

# Search for string references in the .exe that relate to console commands
# Look for "DynamicLoadObject", "ConsoleCommand", "ce " patterns in the binary
# These strings should be near their function implementations

# Search for ASCII strings in the module
search_strings = [
    b"DynamicLoadObject",
    b"ConsoleCommand", 
    b"ProcessConsoleExec",
    b"StaticLoadObject",
    b"LoadPackage",
    b"AddInventory",
    b"GiveWeapon",
]

print(f"\n=== Searching for function name strings in .exe ===")
# Read chunks of the module
chunk_size = 0x1000000  # 16MB chunks
for chunk_start in range(0, min(base_size, 0x10000000), chunk_size):
    data = read_mem(hp, base + chunk_start, min(chunk_size, base_size - chunk_start))
    if not data: continue
    for s in search_strings:
        pos = 0
        while True:
            pos = data.find(s, pos)
            if pos == -1: break
            rva = chunk_start + pos
            # Check if it's a null-terminated string (not part of a larger word)
            end = pos + len(s)
            if end < len(data) and data[end:end+1] in (b'\x00', b'\x22', b'\x20'):
                print(f"  '{s.decode()}' found at RVA 0x{rva:08X} (VA 0x{base+rva:08X})")
            pos += 1

# Also search for the XCheatManager vtable or function pointers
# by looking for references to cheat FName strings
print(f"\n=== Looking for 'ce ' command handler pattern ===")
# In UE3, 'ce' triggers ConsoleEvent which fires Kismet
# The pattern is typically: the engine parses "ce EventName" from console input
# and calls TriggerGlobalEventByName or similar
ce_patterns = [b"ce ", b"CE ", b"causeEvent", b"CauseEvent", b"TriggerGlobalEvent"]
for chunk_start in range(0, min(base_size, 0x10000000), chunk_size):
    data = read_mem(hp, base + chunk_start, min(chunk_size, base_size - chunk_start))
    if not data: continue
    for s in ce_patterns:
        pos = data.find(s)
        if pos != -1:
            rva = chunk_start + pos
            context = data[max(0,pos-4):pos+len(s)+32]
            print(f"  Pattern '{s.decode()}' at RVA 0x{rva:08X}: {context[:40].hex()}")

kernel32.CloseHandle(hp)
