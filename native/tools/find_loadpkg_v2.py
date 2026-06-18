"""Find LoadPackage by searching for UNICODE error messages and nearby function calls."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF

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
hp = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)

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
        base = mod
        class MODULEINFO(ctypes.Structure):
            _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD), ("EntryPoint", ctypes.c_void_p)]
        mi_info = MODULEINFO()
        psapi.GetModuleInformation(hp, ctypes.c_void_p(mod), ctypes.byref(mi_info), ctypes.sizeof(mi_info))
        base_size = mi_info.SizeOfImage
        break

print(f"Base=0x{base:08X} Size=0x{base_size:08X}")
exe_data = read_mem(hp, base, base_size)
if not exe_data: print("Failed!"); sys.exit(1)

# Search for UNICODE (UTF-16LE) strings related to package loading
unicode_strings = [
    "Failed to load package",
    "LoadPackage",
    "Error loading",
    "StaticLoadObject",
    "Can't find file for package",
    "obj load",
    "OBJ LOAD",
    "Obj Load",
    "pkg=",
    "LoadObject",
]

print("\n=== UNICODE string search ===")
for s in unicode_strings:
    ws = s.encode('utf-16-le')
    pos = 0
    while True:
        pos = exe_data.find(ws, pos)
        if pos == -1: break
        # Show context
        ctx_start = max(0, pos - 4)
        ctx_end = min(len(exe_data), pos + len(ws) + 20)
        raw = exe_data[pos:pos+60]
        # Try to decode more context
        try:
            decoded = raw.decode('utf-16-le').split('\x00')[0]
        except:
            decoded = "?"
        print(f"  '{s}' at RVA 0x{pos:08X}: \"{decoded}\"")
        
        # Find code xrefs to this string
        str_va = base + pos
        push_bytes = b'\x68' + struct.pack('<I', str_va)
        for reg_byte in [0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF]:
            ref_bytes = bytes([reg_byte]) + struct.pack('<I', str_va)
            ref_pos = exe_data.find(ref_bytes, 0, 0xD00000)
            if ref_pos != -1:
                # Find function start
                func_start = None
                for back in range(ref_pos, max(ref_pos - 0x800, 0), -1):
                    if exe_data[back:back+3] == b'\x55\x8B\xEC':
                        func_start = back
                        break
                fs2 = f"0x{func_start:08X}" if func_start else "?"
                print(f"    MOV ref at RVA 0x{ref_pos:08X} (func @ {fs2})")
        
        ref_pos = exe_data.find(push_bytes, 0, 0xD00000)
        if ref_pos != -1:
            func_start = None
            for back in range(ref_pos, max(ref_pos - 0x800, 0), -1):
                if exe_data[back:back+3] == b'\x55\x8B\xEC':
                    func_start = back
                    break
            fs_str = f"0x{func_start:08X}" if func_start else "?"
            print(f"    PUSH ref at RVA 0x{ref_pos:08X} (func @ {fs_str})")
        
        pos += 2

# Also search for the "ce " command handler
# The CE command in UE3 is handled by AActor::ProcessConsoleExec
# It looks for "CE " prefix and then fires the event
ce_ws = "ce ".encode('utf-16-le')
print(f"\n=== 'ce ' UNICODE references ===")
pos = 0
while True:
    pos = exe_data.find(ce_ws, pos)
    if pos == -1: break
    # Check surrounding context
    raw = exe_data[pos:pos+40]
    try:
        decoded = raw.decode('utf-16-le').split('\x00')[0]
    except:
        decoded = "?"
    if len(decoded) < 10:  # Filter noise
        str_va = base + pos
        push_bytes = b'\x68' + struct.pack('<I', str_va)
        ref = exe_data.find(push_bytes, 0, 0xD00000)
        if ref != -1:
            print(f"  'ce ' at RVA 0x{pos:08X}: \"{decoded}\" -> PUSH ref at 0x{ref:08X}")
    pos += 2

kernel32.CloseHandle(hp)
