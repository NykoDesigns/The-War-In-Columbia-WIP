import struct, sys

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

def rva_to_file(rva):
    return 0x400 + (rva - 0x1000)

def dump(label, rva, nbytes=128):
    f = rva_to_file(rva)
    print(f'\n{label} @ RVA 0x{rva:X}:')
    for i in range(0, nbytes, 16):
        vals = ' '.join(f'{data[f+i+j]:02X}' for j in range(16))
        print(f'  0x{rva+i:06X} +{i:02X}: {vals}')

def find_call_target(call_rva):
    """Given RVA of a CALL E8 instruction, return target RVA"""
    f = rva_to_file(call_rva)
    if data[f] != 0xE8:
        return None
    rel32 = struct.unpack_from('<i', data, f + 1)[0]
    return call_rva + 5 + rel32

# Dump key functions
dump("XStartWeaponRadialMenu (DLC2)", 0x50A8E0, 96)
dump("XStopWeaponRadialMenu (DLC2)", 0x50A920, 96)
dump("XStartVigorRadialMenu (base)", 0x4FD1B0, 96)
dump("XStopVigorRadialMenu (base)", 0x4FD1F0, 96)

# Find the impl calls within each
print("\n--- Finding implementation calls ---")
for name, rva in [("StartWeaponRadial", 0x50A8E0), ("StopWeaponRadial", 0x50A920),
                   ("StartVigorRadial", 0x4FD1B0), ("StopVigorRadial", 0x4FD1F0)]:
    f = rva_to_file(rva)
    # Scan for E8 (CALL) instructions in first 64 bytes
    for i in range(64):
        if data[f+i] == 0xE8:
            tgt = find_call_target(rva + i)
            if tgt and 0x1000 < tgt < 0xC00000:
                print(f'  {name} +0x{i:02X}: CALL -> impl RVA 0x{tgt:X}')

# Dump implementations
dump("StartWeaponRadial IMPL (DLC2)", 0x8BDDB0, 256)
dump("StopWeaponRadial IMPL (DLC2)", 0x8BD710, 256)
dump("StopVigorRadial IMPL (base)", 0x574E30, 128)

# StartVigorRadial uses vtable call [vtable+0x344] — find what that resolves to
# for XPlayerController. Let's look at XPlayerController vtable.
print("\n--- StartVigorRadial uses vtable[0x344] on PlayerController ---")
# The exec stub: mov eax,[esi]; mov edx,[eax+0x344]; mov ecx,esi; call edx
# This is a virtual call. We need XPlayerController's vtable to find the target.

# Also look at what XWeaponRadialScreen class looks like
for needle in [b'XWeaponRadialScreen', b'WeaponRadialScreen']:
    idx = 0
    count = 0
    while count < 5:
        idx = data.find(needle, idx)
        if idx == -1: break
        start = max(0, idx - 20)
        end = min(len(data), idx + 60)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        rva = idx - 0x400 + 0x1000
        print(f'  0x{rva:X}: ...{printable}...')
        idx += 1
        count += 1

# Check for Scaleform/GFx weapon wheel SWF files
print("\n--- Searching for weapon wheel SWF/GFx references ---")
for needle in [b'WeaponWheel.swf', b'weaponwheel.swf', b'RadialMenu.swf', b'WeaponRadial.swf',
               b'weapon_radial', b'WeaponRadialMenu', b'WeaponWheelMenu']:
    idx = data.find(needle)
    if idx != -1:
        start = max(0, idx - 10)
        end = min(len(data), idx + 60)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f'  {needle.decode()}: ...{printable}...')

sys.exit(0)

# The DLCCPlayerController lookup table has CycleWeaponUp at table RVA 0xF3A588
# Scan a wide range around it to find all DLCCPlayerController exec functions
table_file_off = 0xF3A588 - 0x1000 + 0x400  # known entry for CycleWeaponUp
# Scan 200 entries backward and forward (8 bytes each)
for off in range(-200*8, 200*8, 8):
    pos = table_file_off + off
    if pos < 0 or pos + 8 > len(data):
        continue
    np = struct.unpack_from('<I', data, pos)[0]
    fp = struct.unpack_from('<I', data, pos + 4)[0]
    np_rva = np - 0x400000
    np_foff = np_rva - 0x1000 + 0x400
    fp_rva = fp - 0x400000
    # Check if name pointer points to a valid exec string
    if 0 < np_foff < len(data) - 30:
        ns = data[np_foff:np_foff+80].split(b'\x00')[0].decode('ascii', errors='replace')
        if 'exec' in ns.lower() and ('Weapon' in ns or 'Radial' in ns or 'Cycle' in ns or 'Vigor' in ns or 'DLCC' in ns or 'Carry' in ns or 'Inventory' in ns):
            entry_rva = (pos - 0x400 + 0x1000)
            print(f'  rva=0x{entry_rva:X} name="{ns}" func_rva=0x{fp_rva:X}')

# Also search for XStartWeaponRadialMenu and XStopWeaponRadialMenu directly
print("\n--- Searching for radial menu exec stubs ---")
for needle in [b'execXStartWeaponRadialMenu', b'execXStopWeaponRadialMenu']:
    idx = data.find(needle)
    if idx != -1:
        rva = idx - 0x400 + 0x1000
        va = 0x400000 + rva
        print(f'  {needle.decode()}: string_va=0x{va:X}')
        # Find references to this string's VA
        va_bytes = struct.pack('<I', va)
        ref = 0
        while True:
            ref = data.find(va_bytes, ref)
            if ref == -1: break
            # Check if next 4 bytes is a code pointer
            fp = struct.unpack_from('<I', data, ref + 4)[0]
            fp_rva = fp - 0x400000
            if 0x1000 <= fp_rva <= 0xC00000:
                ref_rva = ref - 0x400 + 0x1000
                print(f'    table entry @ rva=0x{ref_rva:X}: func_rva=0x{fp_rva:X}')
            ref += 1

# Also look for the DLCC2 versions (Burial at Sea Episode 2)
for needle in [b'execXStartWeaponRadialMenu', b'execXStopWeaponRadialMenu']:
    idx = 0
    while True:
        idx = data.find(needle, idx)
        if idx == -1: break
        # Get context before to see which class
        start = max(0, idx - 40)
        ctx = data[start:idx+len(needle)].decode('ascii', errors='replace')
        rva = idx - 0x400 + 0x1000
        print(f'  context @ rva=0x{rva:X}: ...{ctx}')
        idx += 1
