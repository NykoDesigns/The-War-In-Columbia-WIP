"""Count ALL instances of 'Murder of Crows' in a running BioShock process memory.
Run while the game is running to see how many copies exist and in what format."""
import ctypes
import ctypes.wintypes as wt
import struct

kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]

MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40
PAGE_WRITECOPY = 0x08
PAGE_GUARD = 0x100

def find_pid(name):
    import subprocess
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for line in out.strip().split('\n'):
        if name.lower() in line.lower():
            parts = line.strip().split(',')
            return int(parts[1].strip('"'))
    return None

pid = find_pid('BioShockInfinite.exe')
if not pid:
    print("BioShock Infinite is not running!")
    exit(1)

print(f"Found BioShockInfinite.exe PID={pid}")
hProcess = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not hProcess:
    print("Failed to open process!")
    exit(1)

# Search patterns
needle_utf16 = "Murder of Crows".encode('utf-16-le')
needle_ascii = b"Murder of Crows"

utf16_hits = []
ascii_hits = []

mbi = MEMORY_BASIC_INFORMATION()
addr = 0
buf = ctypes.create_string_buffer(0x10000)
bytes_read = ctypes.c_size_t(0)

while addr < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    
    base = mbi.BaseAddress or 0
    region_end = base + mbi.RegionSize
    if region_end <= addr:
        break
    
    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        # Read the region in chunks
        region_size = mbi.RegionSize
        chunk_size = 0x10000
        for offset in range(0, region_size, chunk_size):
            read_addr = base + offset
            to_read = min(chunk_size, region_size - offset)
            buf2 = ctypes.create_string_buffer(to_read)
            if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf2, to_read, ctypes.byref(bytes_read)):
                data = buf2.raw[:bytes_read.value]
                # Search UTF-16
                idx = 0
                while True:
                    idx = data.find(needle_utf16, idx)
                    if idx == -1: break
                    abs_addr = read_addr + idx
                    prot_str = f"0x{mbi.Protect:X}"
                    if mbi.Protect & PAGE_READWRITE: prot_str += " RW"
                    elif mbi.Protect & PAGE_READONLY: prot_str += " RO"
                    elif mbi.Protect & PAGE_EXECUTE_READ: prot_str += " RX"
                    utf16_hits.append((abs_addr, prot_str))
                    idx += 2
                # Search ASCII
                idx = 0
                while True:
                    idx = data.find(needle_ascii, idx)
                    if idx == -1: break
                    abs_addr = read_addr + idx
                    prot_str = f"0x{mbi.Protect:X}"
                    if mbi.Protect & PAGE_READWRITE: prot_str += " RW"
                    elif mbi.Protect & PAGE_READONLY: prot_str += " RO"
                    elif mbi.Protect & PAGE_EXECUTE_READ: prot_str += " RX"
                    ascii_hits.append((abs_addr, prot_str))
                    idx += 1
    
    addr = region_end

kernel32.CloseHandle(hProcess)

print(f"\n=== UTF-16LE 'Murder of Crows' ({len(utf16_hits)} hits) ===")
for a, p in utf16_hits:
    print(f"  0x{a:08X} [{p}]")

print(f"\n=== ASCII 'Murder of Crows' ({len(ascii_hits)} hits) ===")
for a, p in ascii_hits:
    print(f"  0x{a:08X} [{p}]")

print(f"\nTotal: {len(utf16_hits)} UTF-16 + {len(ascii_hits)} ASCII = {len(utf16_hits)+len(ascii_hits)} copies")
