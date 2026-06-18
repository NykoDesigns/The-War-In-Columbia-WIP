"""Analyze the function at RVA 0x000FB540 (contains 'Failed to load package header' ref)
and trace callers to find LoadPackage."""
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

# Read the entire code section
print("Reading code section...")
code = read_mem(hp, base, 0xD00000)
if not code: print("Failed!"); sys.exit(1)

# Function at RVA 0x000FB540 — contains "Failed to load package header:" ref
# This looks like ULinkerLoad::Load() or similar
# Let's find ALL callers of this function

# The function VA is base + 0x000FB540
func_rva = 0x000FB540
print(f"\n=== Finding callers of function at RVA 0x{func_rva:08X} ===")

callers = []
for i in range(0, len(code) - 5):
    if code[i] == 0xE8:  # CALL rel32
        rel = struct.unpack_from('<i', code, i + 1)[0]
        target = i + 5 + rel
        if target == func_rva:
            # Find this caller's function start
            func_start = None
            for back in range(i, max(i - 0x2000, 0), -1):
                if code[back:back+3] == b'\x55\x8B\xEC':
                    func_start = back
                    break
                if back > 0 and code[back-1] == 0xCC and code[back] != 0xCC:
                    func_start = back
                    break
            callers.append((i, func_start))
            fs = f"0x{func_start:08X}" if func_start else "?"
            print(f"  CALL at RVA 0x{i:08X} (caller func @ {fs})")

# Also check the functions at RVA 0x002002F0 and 0x00202016
# These reference "Failed to load package '%s'"
# Find their callers
for func_rva_check in [0x002002F0, 0x00202016]:
    # This is mid-function - find the actual function start
    func_start = None
    for back in range(func_rva_check, max(func_rva_check - 0x2000, 0), -1):
        if code[back:back+3] == b'\x55\x8B\xEC':
            func_start = back
            break
        if back > 0 and code[back-1] == 0xCC and code[back] != 0xCC:
            func_start = back
            break
    if func_start:
        print(f"\n=== Function containing RVA 0x{func_rva_check:08X} starts at 0x{func_start:08X} ===")
        # Find callers of this function
        for i in range(0, len(code) - 5):
            if code[i] == 0xE8:
                rel = struct.unpack_from('<i', code, i + 1)[0]
                target = i + 5 + rel
                if target == func_start:
                    caller_fs = None
                    for back in range(i, max(i - 0x2000, 0), -1):
                        if code[back:back+3] == b'\x55\x8B\xEC':
                            caller_fs = back; break
                        if back > 0 and code[back-1] == 0xCC and code[back] != 0xCC:
                            caller_fs = back; break
                    cfs = f"0x{caller_fs:08X}" if caller_fs else "?"
                    print(f"  CALL at RVA 0x{i:08X} (caller func @ {cfs})")

# The MAIN LoadPackage function is likely the one that:
# 1. Takes a filename/package name as parameter
# 2. Calls the function at 0x000FB540 (which handles the file loading)
# 3. Returns a UPackage*
# Let's examine the caller(s) of 0x000FB540

if callers:
    print(f"\n=== Examining top caller of 0x{0x000FB540:08X} ===")
    for call_rva, caller_start in callers[:3]:
        if not caller_start: continue
        print(f"\n  Caller function at RVA 0x{caller_start:08X} (VA 0x{base+caller_start:08X})")
        # Dump first 128 bytes
        func_bytes = code[caller_start:caller_start+128]
        print(f"  First 128 bytes: {func_bytes.hex()}")
        # Count CALL instructions in this function (to gauge complexity)
        call_count = 0
        for j in range(caller_start, min(caller_start + 0x2000, len(code) - 5)):
            if code[j] == 0xE8:
                call_count += 1
            if code[j] == 0xC3 or code[j:j+2] == b'\xC2\x04':  # RET or RET 4
                func_size = j - caller_start
                print(f"  Approx function size: {func_size} bytes, {call_count} CALL instructions")
                break

kernel32.CloseHandle(hp)
