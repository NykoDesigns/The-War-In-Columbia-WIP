"""Check whether .text is encrypted (SteamStub) and where the entry point is."""
import math
import struct
import pefile

EXE = r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe"

pe = pefile.PE(EXE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
ep = pe.OPTIONAL_HEADER.AddressOfEntryPoint
print(f"ImageBase=0x{base:08X}  EntryPoint RVA=0x{ep:08X} (VA=0x{base+ep:08X})")

for s in pe.sections:
    name = s.Name.rstrip(b"\x00").decode("latin1", "replace")
    rva = s.VirtualAddress
    end = rva + s.Misc_VirtualSize
    contains_ep = rva <= ep < end
    raw = pe.__data__[s.PointerToRawData:s.PointerToRawData + min(s.SizeOfRawData, 65536)]
    # entropy
    if raw:
        freq = [0]*256
        for b in raw:
            freq[b] += 1
        ent = 0.0
        n = len(raw)
        for c in freq:
            if c:
                p = c/n
                ent -= p*math.log2(p)
    else:
        ent = 0
    print(f"  {name:8} RVA=0x{rva:08X} vsize=0x{s.Misc_VirtualSize:X} "
          f"entropy={ent:.2f}{'  <-- ENTRY POINT' if contains_ep else ''}")

# Dump first bytes of .text to eyeball code vs noise
for s in pe.sections:
    name = s.Name.rstrip(b"\x00").decode("latin1", "replace")
    if name == ".text":
        first = pe.__data__[s.PointerToRawData:s.PointerToRawData+64]
        print(f".text first 64 bytes: {first.hex()}")
    if name == ".bind":
        first = pe.__data__[s.PointerToRawData:s.PointerToRawData+64]
        print(f".bind first 64 bytes: {first.hex()}")
