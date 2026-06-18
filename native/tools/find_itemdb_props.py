"""Search exe for all FName-like strings related to XItemDatabase, pricing, upgrades."""
import re

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

# Broader search: any null-terminated ASCII string containing these substrings
patterns = [
    b'Price', b'Cost', b'Upgrade', b'Silver', b'Money', b'Currency',
    b'ItemData', b'ItemDB', b'ItemList', b'Inventory',
    b'AmmoCount', b'MaxAmmo', b'ClipSize', b'SpareAmmo',
    b'Magazine', b'Clip', b'InitAmmo', b'StartAmmo',
    b'DefaultClip', b'MagazineCount',
]

seen = set()
for pat in patterns:
    # Find all null-terminated strings containing pat (reasonable length)
    regex = re.compile(b'(?<=\\x00)([A-Za-z_][A-Za-z0-9_]{2,60}' + pat + b'[A-Za-z0-9_]{0,30})(?=\\x00)')
    for m in regex.finditer(data):
        s = m.group(1)
        try:
            txt = s.decode('ascii')
            if txt not in seen and not txt.startswith('exec') and 'DEPRECATED' not in txt:
                seen.add(txt)
        except:
            pass
    # Also match if pat is at the start
    regex2 = re.compile(b'(?<=\\x00)(' + pat + b'[A-Za-z0-9_]{0,40})(?=\\x00)')
    for m in regex2.finditer(data):
        s = m.group(1)
        try:
            txt = s.decode('ascii')
            if txt not in seen and not txt.startswith('exec'):
                seen.add(txt)
        except:
            pass

for s in sorted(seen):
    print(f"  {s}")
