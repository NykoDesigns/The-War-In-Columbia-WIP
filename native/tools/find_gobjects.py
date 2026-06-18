"""Find GObjObjects RVA in the BioShock exe by scanning for patterns.
GObjObjects is a static TArray<UObject*> = { UObject** Data, int Num, int Max }
We find it by looking for xrefs from known code patterns."""
import struct

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()
image_base = 0x00400000

# GNames is at RVA 0xF9DFEC (known). GObjObjects is typically nearby in .data/.bss.
# Search for the string "GObjObjects" in the exe
idx = data.find(b'GObjObjects')
if idx != -1:
    print(f"String 'GObjObjects' found at file offset 0x{idx:08X}")

# In UE3, UObject::GObjObjects is typically accessed via a static address.
# The pattern to find it: look for instructions that reference it.
# A common pattern is: mov eax, [GObjObjects_Data]; cmp index, [GObjObjects_Num]

# Let's search for the GNames reference pattern and look nearby for GObjObjects
# GNames is at RVA 0xF9DFEC. In the PE, this maps to some VA.
# Let's find where GNames pointer is referenced in code, and look nearby for
# another similar global pointer pattern that would be GObjObjects.

# Actually, let's try a different approach: search the exe for patterns like
# "StaticAllocateObject" or "AddObject" near GObjObjects references

# For now, let's search the data section for TArray-sized structures
# near where GNames lives (they're often in the same data section)
gnames_rva = 0xF9DFEC
gnames_file_off = None

# Parse PE to find sections
pe_off = struct.unpack_from('<I', data, 0x3C)[0]
num_sections = struct.unpack_from('<H', data, pe_off + 6)[0]
opt_hdr_size = struct.unpack_from('<H', data, pe_off + 20)[0]
section_off = pe_off + 24 + opt_hdr_size

print(f"\nPE sections:")
sections = []
for i in range(num_sections):
    s = section_off + i * 40
    name = data[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
    vsize = struct.unpack_from('<I', data, s+8)[0]
    va = struct.unpack_from('<I', data, s+12)[0]
    rawsize = struct.unpack_from('<I', data, s+16)[0]
    rawoff = struct.unpack_from('<I', data, s+20)[0]
    flags = struct.unpack_from('<I', data, s+36)[0]
    print(f"  {name:8s} VA=0x{va:08X} VSize=0x{vsize:08X} Raw=0x{rawoff:08X} RawSz=0x{rawsize:08X} Flags=0x{flags:08X}")
    sections.append((name, va, vsize, rawoff, rawsize, flags))
    if va <= gnames_rva < va + vsize:
        gnames_file_off = rawoff + (gnames_rva - va)
        print(f"    ^ GNames (RVA 0x{gnames_rva:X}) is in this section at file offset 0x{gnames_file_off:X}")

# Read the GNames pointer value from the exe (will be different at runtime due to ASLR)
if gnames_file_off:
    val = struct.unpack_from('<I', data, gnames_file_off)[0]
    print(f"\nGNames initial value at file: 0x{val:08X}")

# Search for references to RVA 0xF9DFEC in code (as an absolute address 0x400000 + 0xF9DFEC)
gnames_va = image_base + gnames_rva
print(f"\nSearching for code references to GNames VA 0x{gnames_va:08X}...")
gnames_bytes = struct.pack('<I', gnames_va)
refs = []
for i in range(len(data) - 4):
    if data[i:i+4] == gnames_bytes:
        # Check if this is in a code section
        for name, va, vsize, rawoff, rawsize, flags in sections:
            if rawoff <= i < rawoff + rawsize:
                rva = va + (i - rawoff)
                if flags & 0x20000000:  # executable
                    refs.append((rva, name))
                break
if refs:
    print(f"Found {len(refs)} code references to GNames:")
    for rva, sec in refs[:10]:
        print(f"  RVA 0x{rva:08X} (section {sec})")

# Now search for GObjObjects. In UE3, it's typically referenced near GNames.
# It's a TArray<UObject*> = 12 bytes: {Data ptr, Num, Max}
# Let's search for a pattern: GObjObjects.Data is accessed with [addr], 
# GObjObjects.Num is at [addr+4]

# Actually, let's search the exe for the string reference to find where
# GObjObjects is initialized
idx = data.find(b'G\x00O\x00b\x00j\x00O\x00b\x00j\x00e\x00c\x00t\x00s\x00')  # UTF-16
if idx != -1:
    print(f"\nUTF-16 'GObjObjects' at file offset 0x{idx:08X}")

# Search for common patterns in data section near GNames
# GObjObjects should be a 12-byte TArray: {ptr, int, int} in .data
# Look at the data section containing GNames
print(f"\n=== Searching .data for likely GObjObjects (TArray near GNames) ===")
for name, va, vsize, rawoff, rawsize, flags in sections:
    if not (flags & 0x40000000):  # not readable data
        continue
    if flags & 0x20000000:  # skip executable
        continue
    # Search this section
    if va <= gnames_rva < va + vsize:
        print(f"Searching {name} section (RVA 0x{va:X}-0x{va+vsize:X})...")
        # Look for TArray patterns: {non-zero ptr, positive count, count >= count}
        # near the GNames location
        gn_off_in_sec = gnames_rva - va
        for delta in range(-0x100, 0x100, 4):
            off = rawoff + gn_off_in_sec + delta
            if off < 0 or off + 12 > len(data): continue
            dptr, num, mx = struct.unpack_from('<III', data, off)
            rva_here = gnames_rva + delta
            # At load time, Data will be 0 (uninitialized). But Num/Max might also be 0.
            # Let's just print what's near GNames
            if abs(delta) <= 64:
                print(f"  RVA 0x{rva_here:08X} (+{delta:+d}): [{dptr:08X}, {num}, {mx}]")
