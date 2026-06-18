"""Patch uppercase 'MURDER OF CROWS' and lowercase 'murder of crows' to 'CARRION CALL' / 'carrion call'."""
import ctypes
import ctypes.wintypes as wt

kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_READWRITE = 0x04

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

hProcess = kernel32.OpenProcess(
    PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION,
    False, pid)

# Pairs: (old_utf16, new_utf16)
pairs = [
    ("MURDER OF CROWS".encode('utf-16-le'), "CARRION CALL".encode('utf-16-le')),
    ("murder of crows".encode('utf-16-le'), "carrion call".encode('utf-16-le')),
]

mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)
bytes_written = ctypes.c_size_t(0)
total = 0

for old_pat, new_pat in pairs:
    # Pad replacement to same length
    new_padded = new_pat + b'\x00' * (len(old_pat) - len(new_pat))
    count = 0
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
                    idx = 0
                    while True:
                        idx = data.find(old_pat, idx)
                        if idx == -1: break
                        w = read_addr + idx
                        old_prot = wt.DWORD(0)
                        kernel32.VirtualProtectEx(hProcess, ctypes.c_void_p(w), len(new_padded), PAGE_READWRITE, ctypes.byref(old_prot))
                        r = kernel32.WriteProcessMemory(hProcess, ctypes.c_void_p(w), new_padded, len(new_padded), ctypes.byref(bytes_written))
                        kernel32.VirtualProtectEx(hProcess, ctypes.c_void_p(w), len(new_padded), old_prot.value, ctypes.byref(old_prot))
                        if r:
                            print(f"  Patched @ 0x{w:08X}")
                            count += 1
                        idx += 2
        addr = region_end
    label = old_pat[:30].decode('utf-16-le')
    print(f'"{label}": {count} patched')
    total += count

kernel32.CloseHandle(hProcess)
print(f"\nTotal: {total} patches. Check radial menu now!")
