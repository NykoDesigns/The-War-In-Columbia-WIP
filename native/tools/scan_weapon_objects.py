"""Scan the running game for weapon/vigor UObject instances and dump their properties.
Strategy: Search for the FName "MachineGun" and "FireInterval" near float values.
Also search for vigor salt cost patterns."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, re

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
print(f"PID={pid}")
hProcess = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)

# Search for weapon-related strings and dump surrounding floats
# The UE3 property serialization stores: FName PropertyName, then value data
# For float properties: the FName of the property, followed by the float value

search_terms = {
    'FireInterval': b'F\x00i\x00r\x00e\x00I\x00n\x00t\x00e\x00r\x00v\x00a\x00l\x00',
    'MachineGun': b'M\x00a\x00c\x00h\x00i\x00n\x00e\x00G\x00u\x00n\x00',
    'Repeater': b'R\x00e\x00p\x00e\x00a\x00t\x00e\x00r\x00',
    'VigorEnergy': b'V\x00i\x00g\x00o\x00r\x00E\x00n\x00e\x00r\x00g\x00y\x00',
    'ConsumeAmmo': b'C\x00o\x00n\x00s\x00u\x00m\x00e\x00A\x00m\x00m\x00o\x00',
    'AmmoCount_A': b'AmmoCount',
    'SpareAmmoCount_A': b'SpareAmmoCount',
    'FireInterval_A': b'FireInterval',
    'VigorEnergy_A': b'VigorEnergy',
}

mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)
addr = 0

results = {k: [] for k in search_terms}

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
                for name, needle in search_terms.items():
                    idx = 0
                    while True:
                        idx = data.find(needle, idx)
                        if idx == -1: break
                        abs_addr = read_addr + idx
                        # Get context: 64 bytes before and 128 bytes after
                        ctx_start = max(0, idx - 64)
                        ctx_end = min(len(data), idx + len(needle) + 128)
                        ctx = data[ctx_start:ctx_end]
                        results[name].append((abs_addr, ctx, idx - ctx_start))
                        idx += 1
    addr = region_end

kernel32.CloseHandle(hProcess)

for name, hits in results.items():
    if not hits: continue
    print(f"\n=== {name} ({len(hits)} hits) ===")
    for addr, ctx, rel_offset in hits[:8]:
        print(f"  @0x{addr:08X}:")
        # Try to find floats in the surrounding context
        floats_found = []
        for i in range(0, len(ctx) - 3, 4):
            try:
                val = struct.unpack('<f', ctx[i:i+4])[0]
                if 0.001 < abs(val) < 10000.0 and val == val:  # non-NaN, reasonable range
                    offset_from_match = i - rel_offset
                    floats_found.append((offset_from_match, val))
            except:
                pass
        # Show hex dump of surrounding area
        hex_start = max(0, rel_offset - 16)
        hex_end = min(len(ctx), rel_offset + len(search_terms[name]) + 48)
        hex_bytes = ' '.join(f'{ctx[i]:02X}' for i in range(hex_start, hex_end))
        print(f"    hex: {hex_bytes}")
        # Show nearby float values
        if floats_found:
            for off, val in floats_found[:10]:
                print(f"    float @+{off}: {val:.6f}")
