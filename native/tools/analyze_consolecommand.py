"""Analyze the internal ConsoleCommand implementation and find ProcessEvent vtable index."""
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
for mi in range(cbNeeded.value // 4):
    mod = hMods[mi]
    if not mod: continue
    mn = ctypes.create_string_buffer(260)
    psapi.GetModuleBaseNameA(hp, ctypes.c_void_p(mod), mn, 260)
    if b'BioShockInfinite' in mn.value: base = mod; break

# Read the function at VA 0x0049CB50 (called by execConsoleCommand)
print("=== Function at VA 0x0049CB50 ===")
code = read_mem(hp, 0x0049CB50, 128)
if code:
    print(f"First 64 bytes: {code[:64].hex()}")
    # Find CALL targets
    for i in range(len(code) - 5):
        if code[i] == 0xE8:
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = 0x0049CB50 + i + 5 + rel
            print(f"  +0x{i:02X}: CALL -> VA 0x{target:08X}")
    # Check if it's a simple wrapper (small, few instructions)
    for i in range(len(code)):
        if code[i] == 0xC3:  # RET
            print(f"  RET at +0x{i:02X} (function is {i} bytes)")
            break
        if code[i:i+2] == b'\xC2\x04':  # RET 4
            print(f"  RET 4 at +0x{i:02X} (function is {i} bytes)")
            break

# Also check the function at VA 0x00513BE0 (first call from execConsoleCommand)
print("\n=== Function at VA 0x00513BE0 ===")
code = read_mem(hp, 0x00513BE0, 128)
if code:
    print(f"First 64 bytes: {code[:64].hex()}")
    for i in range(min(len(code) - 5, 128)):
        if code[i] == 0xC3:
            print(f"  RET at +0x{i:02X}")
            break

# Now find ProcessEvent by a different approach:
# Search for the "ProcessEvent" FName, then find UFunction for ProcessEvent
# Then look for the native func pointer
gn_ptr = read32(hp, base + 0xF9DFEC)
def rfn(i):
    if i < 0 or i > 400000: return None
    ep = read32(hp, gn_ptr + i * 4)
    if not ep: return None
    fl = read32(hp, ep + 8)
    if fl & 1:
        d = read_mem(hp, ep + 0x10, 512)
        if not d: return None
        try: e = d.index(b'\x00\x00'); e += (e%2); return d[:e].decode('utf-16-le')
        except: return None
    else:
        d = read_mem(hp, ep + 0x10, 256)
        if not d: return None
        try: return d[:d.index(b'\x00')].decode('ascii')
        except: return None

print("\n=== Finding ProcessEvent FName and UFunction ===")
pe_fname = -1
for i in range(20000):
    n = rfn(i)
    if n == 'ProcessEvent':
        pe_fname = i
        print(f"  ProcessEvent FName index: {i}")
        break

# Now find the UFunction for ProcessEvent by walking UObject hierarchy
# Actually, ProcessEvent is not a UFunction - it's a C++ virtual function
# Let me try a different approach: find it by scanning for a known call pattern

# ProcessEvent is called when a UFunction is invoked on an object
# The pattern in the caller would be:
# PUSH params_ptr
# PUSH ufunc_ptr  
# MOV ECX, object_ptr
# CALL [vtable + offset]  (indirect call through vtable)

# Let's look for where ConsoleCommand UFunction (0x16824E0C) is referenced in code
print("\n=== Finding code references to ConsoleCommand UFunction ===")
cc_func_addr = 0x16824E0C
# This won't work for heap objects since their address isn't known at compile time

# Instead, let me try calling ConsoleCommand through a simpler mechanism
# In UE3, there's a function called CallFunctionByNameWithArguments
# Signature: bool CallFunctionByNameWithArguments(const TCHAR* Str, FOutputDevice& Ar, UObject* Executor)
# This takes a string like "ConsoleCommand Command=\"ce CheatShockJockey\""

# Find "CallFunctionByNameWithArguments" FName
for i in range(50000):
    n = rfn(i)
    if n and 'CallFunction' in n:
        print(f"  FName [{i}]: {n}")

# Also look for ProcessConsoleExec
for i in range(50000):
    n = rfn(i)
    if n and 'ProcessConsoleExec' in n:
        print(f"  FName [{i}]: {n}")

# Let's also try to find ProcessEvent by looking for all vtable entries that get called
# with a UFunction pointer as parameter (PUSH immediate or register that was loaded from
# a field known to hold a UFunction*)
# This is too complex for a script. Let me try the direct approach instead.

# The key insight: we found execServerCauseEvent at VA 0x004CFD10
# The internal function at VA 0x004CCFB0 (first CALL from execServerCauseEvent) 
# is likely the parameter parser
# The function at VA 0x004A10F0 (second CALL) is likely the actual CauseEvent implementation

print("\n=== Function at VA 0x004CCFB0 (ServerCauseEvent param parser?) ===")
code = read_mem(hp, 0x004CCFB0, 64)
if code:
    print(f"  First 64 bytes: {code[:64].hex()}")
    for i in range(min(len(code), 60)):
        if code[i] == 0xC3:
            print(f"  RET at +0x{i:02X}")
            break

print("\n=== Function at VA 0x004A10F0 (actual CauseEvent?) ===")
code = read_mem(hp, 0x004A10F0, 256)
if code:
    print(f"  First 64 bytes: {code[:64].hex()}")
    for i in range(len(code) - 5):
        if code[i] == 0xE8:
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = 0x004A10F0 + i + 5 + rel
            print(f"  +0x{i:02X}: CALL -> VA 0x{target:08X}")
    for i in range(len(code)):
        if code[i] == 0xC3:
            print(f"  RET at +0x{i:02X}")
            break

kernel32.CloseHandle(hp)
