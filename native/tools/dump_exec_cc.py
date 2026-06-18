"""Dump the full execConsoleCommand function to find the actual implementation call."""
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

pid = find_pid('BioShockInfinite.exe')
if not pid: sys.exit(1)
hp = kernel32.OpenProcess(0x1F0FFF, False, pid)

# Dump execConsoleCommand at VA 0x00536070
print("=== execConsoleCommand @ VA 0x00536070 (512 bytes) ===")
code = read_mem(hp, 0x00536070, 512)
if code:
    # Print in 16-byte lines with hex and try simple disassembly for CALLs
    for i in range(0, min(len(code), 512)):
        if i % 16 == 0:
            print(f"  +0x{i:04X}: ", end="")
        print(f"{code[i]:02X} ", end="")
        if i % 16 == 15:
            print()
    print()
    
    # Find all CALL and indirect CALL instructions
    print("\nCALL instructions:")
    for i in range(len(code) - 5):
        b = code[i]
        # Direct CALL: E8 xx xx xx xx
        if b == 0xE8:
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = 0x00536070 + i + 5 + rel
            print(f"  +0x{i:04X}: CALL 0x{target:08X} (direct)")
        # Indirect CALL: FF /2 (CALL [reg] or CALL [reg+disp])
        if b == 0xFF:
            modrm = code[i+1]
            reg = (modrm >> 3) & 7
            if reg == 2:  # CALL indirect
                mod = (modrm >> 6) & 3
                rm = modrm & 7
                if mod == 0 and rm == 0:
                    print(f"  +0x{i:04X}: CALL [EAX]")
                elif mod == 0 and rm == 1:
                    print(f"  +0x{i:04X}: CALL [ECX]")
                elif mod == 1:
                    disp = struct.unpack_from('<b', code, i + 2)[0]
                    regs = ['EAX','ECX','EDX','EBX','ESP','EBP','ESI','EDI']
                    print(f"  +0x{i:04X}: CALL [{regs[rm]}+0x{disp&0xFF:02X}]")
                elif mod == 2:
                    disp = struct.unpack_from('<i', code, i + 2)[0]
                    regs = ['EAX','ECX','EDX','EBX','ESP','EBP','ESI','EDI']
                    print(f"  +0x{i:04X}: CALL [{regs[rm]}+0x{disp:08X}]")
        # RET
        if b == 0xC3:
            print(f"  +0x{i:04X}: RET")
            break
        if b == 0xC2:
            val = struct.unpack_from('<H', code, i + 1)[0]
            print(f"  +0x{i:04X}: RET {val}")
            break

# Also dump execServerCauseEvent
print("\n=== execServerCauseEvent @ VA 0x004CFD10 (512 bytes) ===")
code = read_mem(hp, 0x004CFD10, 512)
if code:
    print("CALL instructions:")
    for i in range(len(code) - 5):
        b = code[i]
        if b == 0xE8:
            rel = struct.unpack_from('<i', code, i + 1)[0]
            target = 0x004CFD10 + i + 5 + rel
            print(f"  +0x{i:04X}: CALL 0x{target:08X} (direct)")
        if b == 0xFF:
            modrm = code[i+1]
            reg = (modrm >> 3) & 7
            if reg == 2:
                mod = (modrm >> 6) & 3
                rm = modrm & 7
                regs = ['EAX','ECX','EDX','EBX','ESP','EBP','ESI','EDI']
                if mod == 0:
                    if rm == 0: print(f"  +0x{i:04X}: CALL [EAX]")
                    elif rm == 1: print(f"  +0x{i:04X}: CALL [ECX]")
                    else: print(f"  +0x{i:04X}: CALL [{regs[rm]}]")
                elif mod == 1:
                    disp = struct.unpack_from('<b', code, i + 2)[0]
                    print(f"  +0x{i:04X}: CALL [{regs[rm]}+0x{disp&0xFF:02X}]")
                elif mod == 2:
                    disp = struct.unpack_from('<i', code, i + 2)[0]
                    print(f"  +0x{i:04X}: CALL [{regs[rm]}+0x{disp:08X}]")
        if b == 0xC3:
            print(f"  +0x{i:04X}: RET")
            break
        if b == 0xC2:
            val = struct.unpack_from('<H', code, i + 1)[0]
            print(f"  +0x{i:04X}: RET {val}")
            break

kernel32.CloseHandle(hp)
