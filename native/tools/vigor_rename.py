"""Check what properties the Vigor Item entries have (XWeaponItem, XWeaponConsumableItem)
to find where display names come from."""
import sys, struct
sys.path.insert(0, r'z:\TheWarInColumbia')
from core.ue3_parser import UE3Package
from core.property_patcher import read_properties

pkg = UE3Package.from_file(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\CoalescedItems.xxx')

# Check the XWeaponItem for MurderOfCrows (unlock item) and XWeaponConsumableItem
targets = [
    (26340, 'Plasmid_Unlock_MurderOfCrows_Founder (XWeaponItem)'),
    (26315, 'Consumable_Plasmid_MurderofCrows_Founder (XWeaponConsumableItem)'),
    (1409, 'Plasmid_MurderOfCrowsBase (XWeaponMurderOfCrows)'),
    (26485, 'Plasmid_MurderOfCrowsFounder (XWeaponMurderOfCrows)'),
]

for idx, label in targets:
    e = pkg.exports[idx]
    print(f'\n=== [{idx}] {label} (sz={e.serial_size}) ===')
    props = read_properties(pkg, e)
    for p in props:
        val_repr = ''
        if p.type_name == 'FloatProperty' and len(p.value_bytes) >= 4:
            val_repr = f' = {struct.unpack_from("<f", p.value_bytes)[0]:.4f}'
        elif p.type_name == 'IntProperty' and len(p.value_bytes) >= 4:
            val_repr = f' = {struct.unpack_from("<i", p.value_bytes)[0]}'
        elif p.type_name == 'BoolProperty':
            val_repr = f' = {p.array_index != 0}'
        elif p.type_name == 'NameProperty' and len(p.value_bytes) >= 8:
            ni = struct.unpack_from('<i', p.value_bytes)[0]
            if 0 <= ni < len(pkg.names):
                val_repr = f' = "{pkg.names[ni].name}"'
        elif p.type_name == 'StrProperty' and len(p.value_bytes) >= 4:
            slen = struct.unpack_from('<i', p.value_bytes)[0]
            if slen > 0 and slen < 200:
                s = p.value_bytes[4:4+slen-1].decode('latin-1', errors='replace')
                val_repr = f' = "{s}"'
            elif slen < 0:
                chars = -slen
                s = p.value_bytes[4:4+(chars-1)*2].decode('utf-16-le', errors='replace')
                val_repr = f' = "{s}"'
        elif p.type_name == 'ObjectProperty' and len(p.value_bytes) >= 4:
            oi = struct.unpack_from('<i', p.value_bytes)[0]
            if oi > 0 and oi - 1 < len(pkg.exports):
                val_repr = f' -> {pkg.names[pkg.exports[oi-1].object_name].name}'
            elif oi < 0:
                imp_idx = -oi - 1
                if imp_idx < len(pkg.imports):
                    val_repr = f' -> {pkg.names[pkg.imports[imp_idx].object_name].name}'
        print(f'  {p.name:40s} ({p.type_name:15s} sz={p.size:3d}){val_repr}')
