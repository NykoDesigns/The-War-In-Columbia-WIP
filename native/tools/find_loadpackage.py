"""Find StaticLoadObject and LoadPackage function addresses by scanning
for their string references and nearby CALL patterns in the .exe."""
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

# Read the entire .exe image
print("Reading entire module...")
exe_data = read_mem(hp, base, base_size)
if not exe_data:
    print("Failed to read module!")
    sys.exit(1)
print(f"Read {len(exe_data)} bytes")

# Search for key ASCII strings in the .rdata section
# These are UE3 function names used in logging/error messages
search_strings = {
    b"StaticLoadObject": [],
    b"LoadPackage": [],
    b"DynamicLoadObject": [],
    b"ConstructObject": [],
    b"StaticConstructObject": [],
    b"SpawnActor": [],
    b"ProcessEvent": [],
    b"ProcessConsoleExec": [],
    b"ServerCauseEvent": [],
    b"ConsoleCommand": [],
    b"CallFunctionByNameWithArguments": [],
}

print("\n=== String locations ===")
for s in search_strings:
    pos = 0
    while True:
        pos = exe_data.find(s, pos)
        if pos == -1: break
        # Check null termination or word boundary
        end = pos + len(s)
        if end < len(exe_data) and exe_data[end:end+1] in (b'\x00', b' ', b'(', b'"'):
            search_strings[s].append(pos)
            print(f"  '{s.decode()}' at RVA 0x{pos:08X}")
        pos += 1

# For each string, find code references (PUSH or LEA instructions that reference the string address)
print("\n=== Cross-references to key strings ===")
for s, locations in search_strings.items():
    if not locations: continue
    for str_rva in locations[:3]:  # Check first 3 occurrences
        str_va = base + str_rva
        # Search for PUSH str_va (0x68 + little-endian address)
        push_bytes = b'\x68' + struct.pack('<I', str_va)
        # Also search for MOV reg, str_va patterns
        mov_patterns = []
        for reg_byte in [0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF]:  # mov eax..edi, imm32
            mov_patterns.append(bytes([reg_byte]) + struct.pack('<I', str_va))
        
        # Search in code section (first ~0xD00000 bytes)
        code_end = min(0xD00000, len(exe_data))
        
        pos = 0
        while pos < code_end:
            pos = exe_data.find(push_bytes, pos, code_end)
            if pos == -1: break
            # Found a reference! The function that contains this is nearby
            # Look backwards for function prologue (PUSH EBP; MOV EBP, ESP = 55 8B EC)
            func_start = None
            for back in range(pos, max(pos - 0x400, 0), -1):
                if exe_data[back:back+3] == b'\x55\x8B\xEC':
                    func_start = back
                    break
            print(f"  '{s.decode()}' (RVA 0x{str_rva:08X}) referenced at RVA 0x{pos:08X}", end="")
            if func_start:
                print(f" (function @ RVA 0x{func_start:08X} / VA 0x{base+func_start:08X})")
            else:
                print()
            pos += 5
        
        # Check MOV patterns too
        for mp in mov_patterns:
            pos = 0
            while pos < code_end:
                pos = exe_data.find(mp, pos, code_end)
                if pos == -1: break
                func_start = None
                for back in range(pos, max(pos - 0x400, 0), -1):
                    if exe_data[back:back+3] == b'\x55\x8B\xEC':
                        func_start = back
                        break
                print(f"  '{s.decode()}' (RVA 0x{str_rva:08X}) MOV ref at RVA 0x{pos:08X}", end="")
                if func_start:
                    print(f" (function @ RVA 0x{func_start:08X} / VA 0x{base+func_start:08X})")
                else:
                    print()
                pos += 5

kernel32.CloseHandle(hp)
