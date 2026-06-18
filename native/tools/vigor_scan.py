"""Scan game files for vigor name data and combo definitions."""
import struct

EXE = r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe'
ITEMDB = r'D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\GlobalXItemDatabase_SF.xxx'
COALESCED = r'D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\CoalescedItems.xxx'

exe = open(EXE, 'rb').read()
itemdb = open(ITEMDB, 'rb').read()

vigor_names = [
    'Murder of Crows', "Devil's Kiss", 'Shock Jockey', 'Bucking Bronco',
    'Possession', 'Charge', 'Undertow', 'Return to Sender',
]

print("=== Searching GlobalXItemDatabase_SF.xxx for vigor names ===")
for name in vigor_names:
    # Try UTF-16LE
    wide = name.encode('utf-16-le')
    idx = itemdb.find(wide)
    if idx != -1:
        print(f'  "{name}" (UTF-16) at offset 0x{idx:X}')
        # Show surrounding bytes
        start = max(0, idx - 20)
        end = min(len(itemdb), idx + len(wide) + 40)
        ctx = itemdb[start:end]
        # Decode as utf-16-le where possible
        try:
            snippet = itemdb[max(0,idx-40):idx+len(wide)+60].decode('utf-16-le', errors='replace')
            print(f'    Context: {repr(snippet[:100])}')
        except:
            pass
    # Try ASCII
    narrow = name.encode('ascii', errors='ignore')
    idx = itemdb.find(narrow)
    if idx != -1:
        print(f'  "{name}" (ASCII) at offset 0x{idx:X}')
        ctx = itemdb[max(0,idx-10):idx+len(narrow)+40]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f'    Context: {printable}')

print("\n=== Searching EXE for vigor names ===")
for name in vigor_names:
    wide = name.encode('utf-16-le')
    idx = exe.find(wide)
    if idx != -1:
        rva = idx - 0x400 + 0x1000
        print(f'  "{name}" (UTF-16) in EXE at RVA 0x{rva:X}')

print("\n=== Searching for MakeSoup / combo logic ===")
# Find all MakeSoup references
idx = 0
while True:
    idx = exe.find(b'MakeSoup', idx)
    if idx == -1: break
    rva = idx - 0x400 + 0x1000
    ctx = exe[max(0,idx-20):idx+60]
    printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
    print(f'  MakeSoup @ RVA 0x{rva:X}: {printable}')
    idx += 1

print("\n=== Searching CoalescedItems.xxx for vigor data ===")
coalesced = open(COALESCED, 'rb').read()
for needle in [b'MurderOfCrows', b'DevilsKiss', b'ShockJockey', b'BuckingBronco',
               b'Possession', b'Undertow', b'ReturnToSender', b'VigorCombo', b'MakeSoup']:
    idx = coalesced.find(needle)
    if idx != -1:
        ctx = coalesced[max(0,idx-10):idx+80]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f'  {needle.decode():20s} @ 0x{idx:06X}: {printable}')
    else:
        print(f'  {needle.decode():20s} — NOT FOUND')
