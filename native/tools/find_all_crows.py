"""Search for ALL variations of 'Murder of Crows' in process memory."""
import ctypes
import ctypes.wintypes as wt

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
PAGE_GUARD = 0x100

def find_pid(name):
    import subprocess
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for line in out.strip().split('\n'):
        if name.lower() in line.lower():
            return int(line.strip().split(',')[1].strip('"'))
    return None

pid = find_pid('BioShockInfinite.exe')
if not pid:
    print("Not running!"); exit(1)

hProcess = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)

# Search patterns — various encodings and cases
patterns = {
    'UTF16 "Murder of Crows"': "Murder of Crows".encode('utf-16-le'),
    'UTF16 "MURDER OF CROWS"': "MURDER OF CROWS".encode('utf-16-le'),
    'UTF16 "murder of crows"': "murder of crows".encode('utf-16-le'),
    'UTF16 "Murder Of Crows"': "Murder Of Crows".encode('utf-16-le'),
    'ASCII "Murder of Crows"': b"Murder of Crows",
    'ASCII "MURDER OF CROWS"': b"MURDER OF CROWS",
    'ASCII "MurderOfCrows"':   b"MurderOfCrows",
    'ASCII "MURDEROFCROWS"':   b"MURDEROFCROWS",
    'UTF16 "MurderOfCrows"':   "MurderOfCrows".encode('utf-16-le'),
    # Scaleform GFx uses UTF-8 internally in some builds
    'UTF8 "Murder of Crows"':  "Murder of Crows".encode('utf-8'),
    # Check if our rename worked
    'UTF16 "Carrion Call"':    "Carrion Call".encode('utf-16-le'),
    'ASCII "Carrion Call"':    b"Carrion Call",
}

results = {k: 0 for k in patterns}
mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)
addr = 0

while addr < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    base = mbi.BaseAddress or 0
    region_end = base + mbi.RegionSize
    if region_end <= addr: break

    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        region_size = mbi.RegionSize
        chunk_size = 0x10000
        for offset in range(0, region_size, chunk_size):
            read_addr = base + offset
            to_read = min(chunk_size, region_size - offset)
            buf = ctypes.create_string_buffer(to_read)
            if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                data = buf.raw[:bytes_read.value]
                for label, needle in patterns.items():
                    idx = 0
                    while True:
                        idx = data.find(needle, idx)
                        if idx == -1: break
                        results[label] += 1
                        idx += 1
    addr = region_end

kernel32.CloseHandle(hProcess)

print("=== String search results ===")
for label, count in sorted(results.items(), key=lambda x: -x[1]):
    marker = " <---" if count > 0 else ""
    print(f"  {count:4d}x  {label}{marker}")
