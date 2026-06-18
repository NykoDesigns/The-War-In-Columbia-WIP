"""Find vigor display name strings in GlobalXItemDatabase."""
import sys, struct
sys.path.insert(0, r'z:\TheWarInColumbia')
from core.ue3_parser import UE3Package

pkg = UE3Package.from_file(
    r'D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\GlobalXItemDatabase_SF.xxx')

e = pkg.exports[377]
print(f'ItemDatabase: serial_offset=0x{e.serial_offset:X}, size={e.serial_size}')

data = pkg._virtual_data
db_start = e.serial_offset
db_end = db_start + e.serial_size
section = data[db_start:db_end]

# Search for vigor name strings
needles = [b'Murder of Crows', b'Murder Of Crows', b'MurderOfCrows',
           b"Devil's Kiss", b'Shock Jockey', b'Bucking Bronco',
           b'Possession', b'Undertow', b'Return to Sender', b'Charge']

for needle in needles:
    idx = 0
    count = 0
    while count < 5:
        idx = section.find(needle, idx)
        if idx == -1:
            break
        abs_off = db_start + idx
        # Check if preceded by FString length
        if idx >= 4:
            slen = struct.unpack_from('<i', section, idx - 4)[0]
        else:
            slen = -1
        ctx = section[max(0, idx - 6):idx + len(needle) + 20]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        is_fstring = (slen == len(needle) + 1)
        marker = ' <-- FString!' if is_fstring else ''
        print(f'  "{needle.decode()}" @ db+0x{idx:05X} (abs 0x{abs_off:06X}) len_prefix={slen}{marker}')
        print(f'    {printable}')
        idx += 1
        count += 1
    if count == 0:
        print(f'  "{needle.decode()}" — NOT FOUND in ItemDatabase')
