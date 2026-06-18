"""Dump properties of vigor weapon archetypes."""
import sys, struct
sys.path.insert(0, r'z:\TheWarInColumbia')
from core.ue3_parser import UE3Package
from core.property_patcher import read_properties

pkg = UE3Package.from_file(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR\CoalescedItems.xxx')

# Read properties of vigor weapons
vigor_exports = [
    (1409, 'Plasmid_MurderOfCrowsBase'),
    (1414, 'Plasmid_ReturnToSenderBase'),
    (1420, 'Plasmid_UndertowBase'),
    (26311, 'Plasmid_Charge'),
]

for export_idx, label in vigor_exports:
    e = pkg.exports[export_idx]
    name = pkg.names[e.object_name].name
    print(f'\n=== [{export_idx}] {name} (size={e.serial_size}) ===')

    props = read_properties(pkg, e)
    print(f'  Properties ({len(props)}):')
    for p in props:
        val_repr = ''
        if p.type_name == 'FloatProperty' and len(p.value_bytes) >= 4:
            val_repr = f' = {struct.unpack_from("<f", p.value_bytes)[0]:.4f}'
        elif p.type_name == 'IntProperty' and len(p.value_bytes) >= 4:
            val_repr = f' = {struct.unpack_from("<i", p.value_bytes)[0]}'
        elif p.type_name == 'BoolProperty':
            val_repr = f' = {p.array_index != 0}'
        elif p.type_name == 'NameProperty' and len(p.value_bytes) >= 4:
            ni = struct.unpack_from('<i', p.value_bytes)[0]
            if 0 <= ni < len(pkg.names):
                val_repr = f' = "{pkg.names[ni].name}"'
        elif p.type_name == 'ObjectProperty' and len(p.value_bytes) >= 4:
            oi = struct.unpack_from('<i', p.value_bytes)[0]
            if oi > 0 and oi - 1 < len(pkg.exports):
                val_repr = f' -> {pkg.names[pkg.exports[oi-1].object_name].name}'
            elif oi < 0:
                imp_idx = -oi - 1
                if imp_idx < len(pkg.imports):
                    val_repr = f' -> {pkg.names[pkg.imports[imp_idx].object_name].name}'
        print(f'    {p.name:40s} ({p.type_name:15s} sz={p.size:3d}){val_repr}')
