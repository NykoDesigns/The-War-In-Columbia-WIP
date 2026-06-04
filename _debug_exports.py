"""Debug export format in level packages vs item packages."""
import struct
import sys
sys.path.insert(0, r'Z:\TheWarInColumbia')
from core.ue3_parser import UE3Package, read_i32, read_u32, read_u64

# Load a level package
filepath = r"D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\S_TWN_P.xxx"
pkg = UE3Package.from_file(filepath)
vdata = pkg._virtual_data
exp_off = pkg.header.export_offset

print(f"S_TWN_P: export_offset={exp_off}, export_count={pkg.header.export_count}")
print(f"First export raw bytes (80 bytes):")
print(vdata[exp_off:exp_off+80].hex())

# Parse first few exports manually trying different formats
print("\n=== Standard 48-byte format ===")
off = exp_off
for i in range(5):
    start = off
    cls, off2 = read_i32(vdata, off); off = off2
    sup, off2 = read_i32(vdata, off); off = off2
    outer, off2 = read_i32(vdata, off); off = off2
    name_idx, off2 = read_i32(vdata, off); off = off2
    name_num, off2 = read_i32(vdata, off); off = off2
    arch, off2 = read_i32(vdata, off); off = off2
    flags, off2 = read_u64(vdata, off); off = off2
    sz, off2 = read_i32(vdata, off); off = off2
    serial_off, off2 = read_i32(vdata, off); off = off2
    exp_flags, off2 = read_u32(vdata, off); off = off2
    net_count, off2 = read_i32(vdata, off); off = off2
    name = pkg.get_name(name_idx) if 0 <= name_idx < len(pkg.names) else f"?{name_idx}"
    print(f"  [{i}] cls={cls} sup={sup} outer={outer} name='{name}'({name_idx}) num={name_num} arch={arch}")
    print(f"       flags=0x{flags:016X} size={sz} off={serial_off} eflags=0x{exp_flags:08X} net={net_count}")

# Check if the first valid export has size 0 (which was our issue in AIVO)
# Find first export with recognizable class (negative = import reference)
print("\n=== Searching for first export with negative (import) class index ===")
off = exp_off
for i in range(min(100, pkg.header.export_count)):
    cls = struct.unpack_from('<i', vdata, off)[0]
    if cls < 0 and cls > -len(pkg.imports):
        # This should be a valid import reference
        imp_idx = -cls - 1
        cls_name = pkg.get_name(pkg.imports[imp_idx].object_name)
        name_idx = struct.unpack_from('<i', vdata, off + 12)[0]
        name = pkg.get_name(name_idx) if 0 <= name_idx < len(pkg.names) else f"?{name_idx}"
        sz = struct.unpack_from('<i', vdata, off + 32)[0]
        serial = struct.unpack_from('<i', vdata, off + 36)[0]
        print(f"  [{i}] cls='{cls_name}' name='{name}' size={sz} serial_off={serial}")
        if i > 5:
            break
    off += 48

# Maybe the export entries have a different size in level packages
# Let's try to find where serial data starts and work backwards
# First export should have serial data at some known offset
print("\n=== Try to determine export entry size by checking serial offsets ===")
# Read several serial_offset values at stride=48 and see if they increase
print("  Stride=48:")
for i in range(10):
    serial = struct.unpack_from('<i', vdata, exp_off + i*48 + 36)[0]
    sz = struct.unpack_from('<i', vdata, exp_off + i*48 + 32)[0]
    print(f"    [{i}] serial_off={serial} size={sz}")

# Try stride=52 (maybe there's an extra field)
print("  Stride=52:")
for i in range(10):
    serial = struct.unpack_from('<i', vdata, exp_off + i*52 + 36)[0]
    sz = struct.unpack_from('<i', vdata, exp_off + i*52 + 32)[0]
    print(f"    [{i}] serial_off={serial} size={sz}")

# Try stride=56
print("  Stride=56:")
for i in range(10):
    serial = struct.unpack_from('<i', vdata, exp_off + i*56 + 36)[0]
    sz = struct.unpack_from('<i', vdata, exp_off + i*56 + 32)[0]
    print(f"    [{i}] serial_off={serial} size={sz}")
