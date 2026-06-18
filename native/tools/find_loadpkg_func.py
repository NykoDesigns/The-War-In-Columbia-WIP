"""Find function boundaries around the LoadPackage error message references."""
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
if not pid: sys.exit(1)
hp = kernel32.OpenProcess(0x1F0FFF, False, pid)

psapi = ctypes.windll.psapi
hMods = (ctypes.c_uint32 * 1024)()
cbNeeded = wt.DWORD()
psapi.EnumProcessModulesEx(hp, ctypes.byref(hMods), ctypes.sizeof(hMods), ctypes.byref(cbNeeded), 0x01)
base = hMods[0]
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

# Read a large chunk around the references
# Reference 1: RVA 0x00200326 (LoadPackage error)
# Reference 2: RVA 0x00202127 (LoadPackage error)
targets = [0x00200326, 0x00202127, 0x000FB59E]

for target_rva in targets:
    # Read 0x2000 bytes before and after to find function boundaries
    start = max(0, target_rva - 0x1000)
    data = read_mem(hp, base + start, 0x2000)
    if not data: continue
    
    print(f"\n=== Around RVA 0x{target_rva:08X} (VA 0x{base+target_rva:08X}) ===")
    
    # Find function start by looking for:
    # 1. push ebp; mov ebp, esp (55 8B EC)
    # 2. sub esp, XX (83 EC XX or 81 EC XX XX XX XX) 
    # 3. int3 padding (CC CC...) followed by non-CC byte
    # 4. ret (C3 or C2 XX XX) followed by alignment padding
    
    offset_in_chunk = target_rva - start
    
    # Search backwards for function prologue
    func_start = None
    for back in range(offset_in_chunk, 0, -1):
        b = data[back]
        # Standard prologue: push ebp; mov ebp, esp
        if data[back:back+3] == b'\x55\x8B\xEC':
            func_start = start + back
            break
        # Alternative: push esi/edi followed by sub esp or push
        if back > 0 and data[back-1] == 0xCC and b != 0xCC:
            func_start = start + back
            break
    
    if func_start:
        print(f"  Function likely starts at RVA 0x{func_start:08X} (VA 0x{base+func_start:08X})")
        # Dump first 32 bytes of the function
        func_data = read_mem(hp, base + func_start, 64)
        if func_data:
            print(f"  First 64 bytes: {func_data.hex()}")
    else:
        print("  Could not find function start")
    
    # Show the context around the PUSH instruction
    ctx_start = offset_in_chunk - 0x20
    ctx_end = offset_in_chunk + 0x20
    ctx = data[max(0,ctx_start):min(len(data),ctx_end)]
    print(f"  Context bytes around ref: {ctx.hex()}")

    # Also: look at CALL instructions near the PUSH to find what's being called
    # Pattern: PUSH str_addr; ... CALL target
    # Look for CALL (E8 XX XX XX XX) within 0x30 bytes after the PUSH
    for i in range(offset_in_chunk, min(offset_in_chunk + 0x40, len(data) - 5)):
        if data[i] == 0xE8:
            rel = struct.unpack_from('<i', data, i + 1)[0]
            call_target = start + i + 5 + rel
            print(f"  CALL at RVA 0x{start+i:08X} -> target RVA 0x{call_target:08X} (VA 0x{base+call_target:08X})")

# Also, let's look for the 'obj load' or 'OBJ LOAD' handler
# In UE3, this is in UObject::StaticExec, handling "obj load pkg=..."
print(f"\n=== Looking for 'obj' command handler ===")
exe_data = read_mem(hp, base, 0xD00000)  # Code section
if exe_data:
    # Search for "obj " as ASCII
    for search_str in [b"OBJ ", b"obj "]:
        pos = 0
        while True:
            pos = exe_data.find(search_str, pos)
            if pos == -1: break
            # Check context - is this in an "if ParseCommand matches 'obj'" block?
            ctx = exe_data[pos:pos+20]
            # Only show if near other identifiable strings
            if pos < 0xD00000:
                # Check if followed by LOAD or DUMP etc
                rest = exe_data[pos+4:pos+20]
                if rest[:4] in [b'LOAD', b'load', b'DUMP', b'dump', b'LIST', b'list']:
                    print(f"  '{search_str.decode()+rest[:4].decode()}' at RVA 0x{pos:08X}")
            pos += 1

kernel32.CloseHandle(hp)
