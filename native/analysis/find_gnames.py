"""Find GNames (chunked FNameEntry array) and the FName entry accessor.

UE3 stores names in a chunked array (FName::Names). GetEntry(Index) does:
    chunk = Index >> 14 ; elem = Index & 0x3FFF
    entry = Chunks[chunk][elem]
So the accessor contains the immediate 0x3FFF (mask) and a shift by 14.
We scan .text for the mask, then disassemble a window around each hit and
report the global pointer(s) referenced (candidate GNames chunk table).
"""
import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe"

pe = pefile.PE(EXE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.__data__
text = next(s for s in pe.sections if s.Name.rstrip(b"\x00") == b".text")
data_sec = next(s for s in pe.sections if s.Name.rstrip(b"\x00") == b".data")
text_raw = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
text_va = base + text.VirtualAddress
data_lo = base + data_sec.VirtualAddress
data_hi = data_lo + data_sec.Misc_VirtualSize

md = Cs(CS_ARCH_X86, CS_MODE_32)

# Find occurrences of the dword 0x00003FFF in .text (the mask immediate).
needle = struct.pack("<I", 0x00003FFF)
hits = []
start = 0
while True:
    i = text_raw.find(needle, start)
    if i < 0:
        break
    hits.append(i)
    start = i + 1

print(f"0x3FFF immediates in .text: {len(hits)}")

# For each hit, disassemble a window starting a bit before it and look for
# the pattern: a shift (shr/sar by 0x0E) + an AND 0x3FFF + a [global + reg*4] load.
seen_globals = {}
for off in hits:
    win_start = max(0, off - 0x40)
    win = text_raw[win_start:off + 0x40]
    addr = text_va + win_start
    insns = list(md.disasm(win, addr))
    has_shift14 = any(
        ins.mnemonic in ("shr", "sar") and ins.op_str.endswith("0xe")
        for ins in insns)
    has_and = any(ins.mnemonic == "and" and "0x3fff" in ins.op_str
                  for ins in insns)
    if not (has_shift14 and has_and):
        continue
    # collect global pointers referenced via mov reg,[imm32] within window
    for ins in insns:
        op = ins.op_str
        if ins.mnemonic == "mov" and "[0x" in op:
            try:
                g = int(op[op.index("[0x") + 1:op.index("]", op.index("[0x"))], 16)
            except ValueError:
                continue
            if data_lo <= g < data_hi:
                seen_globals.setdefault(g, []).append(ins.address)

print("\nCandidate GNames chunk-table globals (data ptrs near shift14+and0x3FFF):")
for g, addrs in sorted(seen_globals.items(), key=lambda kv: -len(kv[1])):
    print(f"  global 0x{g:08X} (rva 0x{g-base:X})  refs={len(addrs)}  "
          f"first@0x{addrs[0]:08X}")
