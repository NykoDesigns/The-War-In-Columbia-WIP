"""Patch ALL 'Murder of Crows' strings in live BioShock process memory."""
import ctypes
import ctypes.wintypes as wt
import struct

kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
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
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READWRITE = 0x40

def find_pid(name):
    import subprocess
    out = subprocess.check_output(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], text=True)
    for line in out.strip().split('\n'):
        if name.lower() in line.lower():
            parts = line.strip().split(',')
            return int(parts[1].strip('"'))
    return None

OLD_NAME = "Murder of Crows"
NEW_NAME = "Carrion Call"

pid = find_pid('BioShockInfinite.exe')
if not pid:
    print("BioShock Infinite is not running!")
    exit(1)

print(f"PID={pid}")
hProcess = kernel32.OpenProcess(
    PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION,
    False, pid)
if not hProcess:
    print("Failed to open process! Run as Administrator.")
    exit(1)

# Build search/replace patterns
old_utf16 = OLD_NAME.encode('utf-16-le')
new_utf16 = NEW_NAME.encode('utf-16-le')
# Pad new to same length as old
new_utf16_padded = new_utf16 + b'\x00' * (len(old_utf16) - len(new_utf16))

old_ascii = OLD_NAME.encode('ascii')
new_ascii = NEW_NAME.encode('ascii')
new_ascii_padded = new_ascii + b'\x00' * (len(old_ascii) - len(new_ascii))

mbi = MEMORY_BASIC_INFORMATION()
bytes_read = ctypes.c_size_t(0)
bytes_written = ctypes.c_size_t(0)
addr = 0
utf16_patched = 0
ascii_patched = 0

while addr < 0x7FFF0000:
    if kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
        break
    
    base = mbi.BaseAddress or 0
    region_end = base + mbi.RegionSize
    if region_end <= addr:
        break
    
    if mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD):
        region_size = mbi.RegionSize
        chunk_size = 0x10000
        for offset in range(0, region_size, chunk_size):
            read_addr = base + offset
            to_read = min(chunk_size, region_size - offset)
            buf = ctypes.create_string_buffer(to_read)
            if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(read_addr), buf, to_read, ctypes.byref(bytes_read)):
                data = buf.raw[:bytes_read.value]
                
                # Patch UTF-16
                idx = 0
                while True:
                    idx = data.find(old_utf16, idx)
                    if idx == -1: break
                    write_addr = read_addr + idx
                    # Make writable if needed
                    old_prot = wt.DWORD(0)
                    kernel32.VirtualProtectEx(hProcess, ctypes.c_void_p(write_addr),
                                             len(new_utf16_padded), PAGE_READWRITE, ctypes.byref(old_prot))
                    result = kernel32.WriteProcessMemory(hProcess, ctypes.c_void_p(write_addr),
                                                        new_utf16_padded, len(new_utf16_padded),
                                                        ctypes.byref(bytes_written))
                    kernel32.VirtualProtectEx(hProcess, ctypes.c_void_p(write_addr),
                                             len(new_utf16_padded), old_prot.value, ctypes.byref(old_prot))
                    if result:
                        print(f"  UTF16 patched @ 0x{write_addr:08X}")
                        utf16_patched += 1
                    idx += 2
                
                # Patch ASCII
                idx = 0
                while True:
                    idx = data.find(old_ascii, idx)
                    if idx == -1: break
                    write_addr = read_addr + idx
                    old_prot = wt.DWORD(0)
                    kernel32.VirtualProtectEx(hProcess, ctypes.c_void_p(write_addr),
                                             len(new_ascii_padded), PAGE_READWRITE, ctypes.byref(old_prot))
                    result = kernel32.WriteProcessMemory(hProcess, ctypes.c_void_p(write_addr),
                                                        new_ascii_padded, len(new_ascii_padded),
                                                        ctypes.byref(bytes_written))
                    kernel32.VirtualProtectEx(hProcess, ctypes.c_void_p(write_addr),
                                             len(new_ascii_padded), old_prot.value, ctypes.byref(old_prot))
                    if result:
                        print(f"  ASCII patched @ 0x{write_addr:08X}")
                        ascii_patched += 1
                    idx += 1
    
    addr = region_end

kernel32.CloseHandle(hProcess)
print(f"\nDone: {utf16_patched} UTF-16 + {ascii_patched} ASCII = {utf16_patched+ascii_patched} total patches")
print("Now open the vigor radial menu in-game to check!")
