"""
The War In Columbia — SDK-Level Data Dumper
============================================
Comprehensive tool for extracting and mapping game internals from:
  - UE3 packages (.xxx files in CookedPCConsole)
  - Ghidra decompilation (exe + DLLs)
  - Runtime logs (wic_spawn.log)

Outputs structured data to SDK_MAP.md for persistent reference.

Usage:
  python tools/sdk_dump.py packages   - Dump all combat map package structures
  python tools/sdk_dump.py spawners   - Find and analyze spawn-related exports
  python tools/sdk_dump.py classes    - Map class hierarchy from imports/exports
  python tools/sdk_dump.py physx      - Analyze PhysX-related actors and constraints
  python tools/sdk_dump.py runtime    - Parse runtime log for actor census
  python tools/sdk_dump.py all        - Run everything, update SDK_MAP.md
"""

import sys
import os
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from core.ue3_parser import UE3Package, read_i32, read_u32, read_u64

# ─── Paths ───────────────────────────────────────────────────────────────────

GAME_DIR = Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite")
COOKED_DIR = GAME_DIR / "XGame" / "CookedPCConsole_FR"
BIN_DIR = GAME_DIR / "Binaries" / "Win32"
LOG_FILE = BIN_DIR / "wic_spawn.log"
EXE_FILE = BIN_DIR / "BioShockInfinite.exe"
SDK_MAP_FILE = PROJECT_ROOT / "SDK_MAP.md"

# Map packages (main level files)
LEVEL_PACKAGES = [
    'S_TWN_P', 'S_TWN2_P', 'S_TWN3_P',
    'S_BW_P', 'S_BW2_P', 'S_BW3_P',
    'S_Fink_P', 'S_Fink2_P', 'S_Fink3_P', 'S_Fink4_P',
    'S_EMP_P', 'S_EMP2_P',
    'S_DCOM_P', 'S_CHU_P',
]

# Classes relevant to spawning and physics
SPAWN_CLASSES = [
    'XAISpawner', 'XAIScriptedSpawner', 'XAISquadSpawner',
    'XAISpawnRoster', 'XAISpawnDescriptor', 'XAIArchetypeDescriptor',
    'XAIController', 'XAIElizabethController',
    'XAIPawn', 'XGamePawn',
]

PHYSICS_CLASSES = [
    'RigidBodyBase', 'KAsset', 'KActorFromStatic', 'KActor',
    'RB_ConstraintActor', 'PhysicsVolume', 'RigidBodyComponent',
    'PhysXDestructible', 'PhysXEmitter',
]


# ─── Package Analysis ─────────────────────────────────────────────────────────

def find_package_file(name):
    """Find the .xxx package file on disk."""
    # Try multiple naming patterns
    for pattern in [f"{name}.xxx", f"{name}_Game.xxx", f"{name}_S.xxx"]:
        path = COOKED_DIR / pattern
        if path.exists():
            return path
    # Glob fallback
    matches = list(COOKED_DIR.glob(f"{name}*"))
    if matches:
        return matches[0]
    return None


def analyze_package(pkg_path):
    """Analyze a package and return structured data."""
    try:
        pkg = UE3Package.from_file(pkg_path)
    except Exception as e:
        return {'error': str(e), 'path': str(pkg_path)}

    # Build class index → name mapping from imports
    class_map = {}
    for i, imp in enumerate(pkg.imports):
        class_map[-(i + 1)] = pkg.get_name(imp.object_name)

    # Categorize exports by class
    exports_by_class = defaultdict(list)
    for exp in pkg.exports:
        if exp.class_index < 0:
            cls_name = class_map.get(exp.class_index, f'Import#{-exp.class_index-1}')
        elif exp.class_index > 0:
            # Points to another export (rare for class refs)
            cls_name = f'Export#{exp.class_index}'
        else:
            cls_name = 'Class'  # class_index=0 means this IS a class
        obj_name = pkg.get_name(exp.object_name)
        exports_by_class[cls_name].append({
            'name': obj_name,
            'index': exp.index,
            'size': exp.serial_size,
            'offset': exp.serial_offset,
        })

    return {
        'path': str(pkg_path),
        'name_count': len(pkg.names),
        'import_count': len(pkg.imports),
        'export_count': len(pkg.exports),
        'exports_by_class': dict(exports_by_class),
    }


def dump_spawn_info(pkg_path):
    """Extract spawn-related exports from a package."""
    try:
        pkg = UE3Package.from_file(pkg_path)
    except Exception as e:
        return {'error': str(e)}

    # Build class lookup
    class_map = {}
    for i, imp in enumerate(pkg.imports):
        class_map[-(i + 1)] = pkg.get_name(imp.object_name)

    spawners = []
    for exp in pkg.exports:
        cls_name = class_map.get(exp.class_index, '')
        obj_name = pkg.get_name(exp.object_name)
        # Match spawn-related classes
        if any(sc.lower() in cls_name.lower() for sc in SPAWN_CLASSES):
            spawners.append({
                'class': cls_name,
                'name': obj_name,
                'index': exp.index,
                'size': exp.serial_size,
                'offset': exp.serial_offset,
            })
    return spawners


def dump_physics_info(pkg_path):
    """Extract physics-related exports from a package."""
    try:
        pkg = UE3Package.from_file(pkg_path)
    except Exception as e:
        return {'error': str(e)}

    class_map = {}
    for i, imp in enumerate(pkg.imports):
        class_map[-(i + 1)] = pkg.get_name(imp.object_name)

    physics = []
    for exp in pkg.exports:
        cls_name = class_map.get(exp.class_index, '')
        obj_name = pkg.get_name(exp.object_name)
        if any(pc.lower() in cls_name.lower() for pc in PHYSICS_CLASSES):
            physics.append({
                'class': cls_name,
                'name': obj_name,
                'index': exp.index,
                'size': exp.serial_size,
            })
    return physics


# ─── Runtime Log Analysis ─────────────────────────────────────────────────────

def parse_runtime_log(log_path=None):
    """Parse wic_spawn.log for actor census and crash data."""
    if log_path is None:
        log_path = LOG_FILE
    if not Path(log_path).exists():
        return {'error': f'Log not found: {log_path}'}

    with open(log_path, 'r', errors='replace') as f:
        lines = f.readlines()

    spawns = []
    crashes = []
    roster_grows = []
    guards = {'memcpy': 0, 'ser': 0, 'serdisp': 0, 'streamread': 0, 'pool': 0}
    patches = []

    for line in lines:
        line = line.strip()
        if 'SPAWN #' in line:
            # Parse: [HH:MM.mmm] SPAWN #N: class='X' name='Y' vtbl_rva=0xZ
            try:
                parts = line.split("class='")[1]
                cls = parts.split("'")[0]
                name = line.split("name='")[1].split("'")[0]
                spawns.append({'class': cls, 'name': name})
            except (IndexError, ValueError):
                pass
        elif '*** CRASH' in line:
            crashes.append(line)
        elif 'ROSTER-GROW' in line:
            roster_grows.append(line)
        elif 'MEMCPY-GUARD' in line:
            guards['memcpy'] += 1
        elif 'SER-GUARD' in line:
            guards['ser'] += 1
        elif 'SERDISP-GUARD' in line:
            guards['serdisp'] += 1
        elif 'STREAMREAD-PATCH' in line:
            patches.append(line)
        elif 'POOL-GROW' in line:
            guards['pool'] += 1

    # Actor census
    class_counts = Counter(s['class'] for s in spawns)
    ai_controllers = [s for s in spawns if 'Controller' in s['class']]

    return {
        'total_spawns': len(spawns),
        'total_crashes': len(crashes),
        'roster_grows': len(roster_grows),
        'guards': guards,
        'patches': patches,
        'class_counts': dict(class_counts.most_common(30)),
        'ai_controller_count': len(ai_controllers),
        'crashes': crashes[-5:] if crashes else [],  # last 5 crashes
    }


# ─── Class Hierarchy Mapper ──────────────────────────────────────────────────

def map_class_hierarchy():
    """Build a class hierarchy from all combat map packages."""
    all_classes = defaultdict(lambda: {'count': 0, 'packages': set()})
    import_classes = defaultdict(lambda: {'packages': set(), 'class_package': set()})

    for pkg_name in LEVEL_PACKAGES:
        pkg_path = find_package_file(pkg_name)
        if not pkg_path:
            continue
        try:
            pkg = UE3Package.from_file(pkg_path)
        except Exception:
            continue

        for imp in pkg.imports:
            cls_pkg = pkg.get_name(imp.class_package)
            cls_name = pkg.get_name(imp.class_name)
            obj_name = pkg.get_name(imp.object_name)
            import_classes[obj_name]['packages'].add(pkg_name)
            import_classes[obj_name]['class_package'].add(cls_pkg)

        class_map = {}
        for i, imp in enumerate(pkg.imports):
            class_map[-(i + 1)] = pkg.get_name(imp.object_name)

        for exp in pkg.exports:
            cls_name = class_map.get(exp.class_index, 'Unknown')
            all_classes[cls_name]['count'] += 1
            all_classes[cls_name]['packages'].add(pkg_name)

    return {
        'export_classes': {k: {'count': v['count'], 'packages': sorted(v['packages'])}
                          for k, v in sorted(all_classes.items(), key=lambda x: -x[1]['count'])[:50]},
        'import_classes_spawn': {k: {'packages': sorted(v['packages']), 'class_package': sorted(v['class_package'])}
                                  for k, v in import_classes.items()
                                  if any(sc.lower() in k.lower() for sc in SPAWN_CLASSES + PHYSICS_CLASSES)},
    }


# ─── Descriptor Layout Analysis ──────────────────────────────────────────────

def analyze_descriptor_layout(pkg_name='S_TWN_P'):
    """Try to find XAISpawnDescriptor objects and dump their field layout."""
    pkg_path = find_package_file(pkg_name)
    if not pkg_path:
        return {'error': f'Package not found: {pkg_name}'}

    try:
        pkg = UE3Package.from_file(pkg_path)
    except Exception as e:
        return {'error': str(e)}

    class_map = {}
    for i, imp in enumerate(pkg.imports):
        class_map[-(i + 1)] = pkg.get_name(imp.object_name)

    descriptors = []
    for exp in pkg.exports:
        cls_name = class_map.get(exp.class_index, '')
        if 'Descriptor' in cls_name or 'Spawn' in cls_name:
            obj_name = pkg.get_name(exp.object_name)
            # Read serial data
            if exp.serial_size > 0 and exp.serial_offset > 0:
                serial_data = pkg._virtual_data[exp.serial_offset:exp.serial_offset + exp.serial_size]
                descriptors.append({
                    'class': cls_name,
                    'name': obj_name,
                    'size': exp.serial_size,
                    'offset': exp.serial_offset,
                    'hex_preview': serial_data[:128].hex() if serial_data else '',
                })
    return descriptors


# ─── SDK_MAP.md Generator ─────────────────────────────────────────────────────

def generate_sdk_map(results):
    """Generate the SDK_MAP.md knowledge base."""
    lines = []
    lines.append("# BioShock Infinite — SDK Data Map")
    lines.append(f"\n*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    lines.append("This file is a persistent knowledge base of game internals discovered")
    lines.append("through reverse engineering. Updated by `tools/sdk_dump.py`.\n")
    lines.append("---\n")

    # Runtime data
    if 'runtime' in results:
        rt = results['runtime']
        lines.append("## 1. Runtime Actor Census (from wic_spawn.log)\n")
        if 'error' in rt:
            lines.append(f"⚠️ {rt['error']}\n")
        else:
            lines.append(f"- **Total spawns logged**: {rt['total_spawns']}")
            lines.append(f"- **AI Controllers**: {rt['ai_controller_count']}")
            lines.append(f"- **Roster grows**: {rt['roster_grows']}")
            lines.append(f"- **Crashes**: {rt['total_crashes']}")
            lines.append(f"- **Guard triggers**: memcpy={rt['guards']['memcpy']}, "
                        f"pool={rt['guards']['pool']}")
            lines.append(f"\n### Patches Applied\n")
            for p in rt.get('patches', []):
                lines.append(f"- `{p}`")
            lines.append(f"\n### Actor Classes (top 20)\n")
            lines.append("| Class | Count |")
            lines.append("|-------|-------|")
            for cls, count in list(rt['class_counts'].items())[:20]:
                lines.append(f"| {cls} | {count} |")
            if rt['crashes']:
                lines.append(f"\n### Recent Crashes\n```")
                for c in rt['crashes']:
                    lines.append(c)
                lines.append("```")
        lines.append("\n---\n")

    # Package structures
    if 'packages' in results:
        lines.append("## 2. Package Structures\n")
        for pkg_name, info in results['packages'].items():
            if 'error' in info:
                lines.append(f"### {pkg_name}\n⚠️ {info['error']}\n")
                continue
            lines.append(f"### {pkg_name}\n")
            lines.append(f"- Names: {info['name_count']}, Imports: {info['import_count']}, "
                        f"Exports: {info['export_count']}")
            # Show top classes
            ebc = info['exports_by_class']
            top = sorted(ebc.items(), key=lambda x: -len(x[1]))[:15]
            lines.append(f"\n| Class | Export Count | Example |")
            lines.append(f"|-------|-------------|---------|")
            for cls, exports in top:
                example = exports[0]['name'] if exports else ''
                lines.append(f"| {cls} | {len(exports)} | {example} |")
            lines.append("")
        lines.append("---\n")

    # Spawner data
    if 'spawners' in results:
        lines.append("## 3. Spawn System Exports\n")
        for pkg_name, spawners in results['spawners'].items():
            if isinstance(spawners, dict) and 'error' in spawners:
                continue
            if not spawners:
                continue
            lines.append(f"### {pkg_name}\n")
            lines.append("| Class | Name | Size | Offset |")
            lines.append("|-------|------|------|--------|")
            for s in spawners[:30]:
                lines.append(f"| {s['class']} | {s['name']} | {s['size']} | 0x{s['offset']:X} |")
            lines.append("")
        lines.append("---\n")

    # Physics data
    if 'physics' in results:
        lines.append("## 4. Physics Actors\n")
        total_phys = sum(len(v) if isinstance(v, list) else 0
                        for v in results['physics'].values())
        lines.append(f"Total physics-related exports across combat maps: **{total_phys}**\n")
        for pkg_name, phys in results['physics'].items():
            if isinstance(phys, dict) and 'error' in phys:
                continue
            if not phys:
                continue
            lines.append(f"### {pkg_name} ({len(phys)} physics exports)\n")
            class_counts = Counter(p['class'] for p in phys)
            lines.append("| Physics Class | Count |")
            lines.append("|---------------|-------|")
            for cls, count in class_counts.most_common(10):
                lines.append(f"| {cls} | {count} |")
            lines.append("")
        lines.append("---\n")

    # Class hierarchy
    if 'classes' in results:
        lines.append("## 5. Class Hierarchy (Spawn + Physics)\n")
        cls_data = results['classes']
        if 'import_classes_spawn' in cls_data:
            lines.append("### Import Classes (Spawn/Physics related)\n")
            lines.append("| Class | Packages | Source Module |")
            lines.append("|-------|----------|---------------|")
            for cls, info in sorted(cls_data['import_classes_spawn'].items()):
                pkgs = ', '.join(info['packages'][:3])
                src = ', '.join(info['class_package'][:2])
                lines.append(f"| {cls} | {pkgs} | {src} |")
            lines.append("")
        lines.append("---\n")

    # Descriptor layout
    if 'descriptors' in results:
        lines.append("## 6. Spawn Descriptor Layout\n")
        lines.append("Descriptor objects found in packages (serial data preview):\n")
        for desc in results.get('descriptors', [])[:20]:
            lines.append(f"- **{desc['class']}** `{desc['name']}` — {desc['size']} bytes @ 0x{desc['offset']:X}")
            if desc.get('hex_preview'):
                lines.append(f"  ```\n  {desc['hex_preview'][:64]}...\n  ```")
        lines.append("\n---\n")

    # Known runtime offsets (from ue3_spawn.cpp)
    lines.append("## 7. Known Runtime Offsets (from native hook)\n")
    lines.append("### Spawn Descriptor (DESC_STRIDE bytes, cloned at runtime)\n")
    lines.append("| Offset | Field | Notes |")
    lines.append("|--------|-------|-------|")
    lines.append("| +0x00..+0x?? | TArray fields | Multiple embedded TArrays (inventory, etc) |")
    lines.append("| +0xCC | UObject* (Spawner) | Back-reference to XAIScriptedSpawner; zeroed in clones |")
    lines.append("| +0xD8 | Delegate{Obj,FName,FName} | 12 bytes; object pointer to spawner; zeroed |")
    lines.append("| +0xE8 | RuntimeCnt | Per-instance counter; zeroed in clones |")
    lines.append("| +0xEC | RuntimePtr | Per-instance heap pointer; zeroed in clones |")
    lines.append("| +OFF_DESC_PosX | float | Spawn X position; nudged +96 per clone |")
    lines.append("")
    lines.append("### Stream Reader Object (FUN_00496F00 this-pointer)\n")
    lines.append("| Offset | Field | Notes |")
    lines.append("|--------|-------|-------|")
    lines.append("| +0x00 | vtable* | Virtual table pointer |")
    lines.append("| +0xAC | curPos (int) | Current read position in buffer |")
    lines.append("| +0xB0 | remaining (int) | Bytes remaining before refill needed |")
    lines.append("| +0xBC | buf1_base | Buffer 1 base address |")
    lines.append("| +0xC0 | buf2_base | Buffer 2 base address |")
    lines.append("| +0xC8 | buf1_end | Buffer 1 end address (0 when freed!) |")
    lines.append("| +0xCC | buf2_end | Buffer 2 end address |")
    lines.append("| +0xD4 | buf1_data | Buffer 1 current data pointer |")
    lines.append("| +0xD8 | buf2_data | Buffer 2 current data pointer |")
    lines.append("| vtable+0x3C | Refill vfunc | __thiscall(this, curPos, count) → int |")
    lines.append("")
    lines.append("### Key RVAs (BioShockInfinite.exe, base 0x00400000)\n")
    lines.append("| RVA | Symbol | Notes |")
    lines.append("|-----|--------|-------|")
    lines.append("| 0x22CA80 | SpawnActor | UWorld::SpawnActor |")
    lines.append("| 0x658870 | SpawnRoster | Roster-based AI spawner |")
    lines.append("| 0x96F00 | StreamRead (FUN_00496F00) | Double-buffered async reader (PATCHED) |")
    lines.append("| 0x96F5E | StreamRead+0x5E | JLE→JBE patch site (buf1) |")
    lines.append("| 0x96FA7 | StreamRead+0xA7 | JLE→JBE patch site (buf2) |")
    lines.append("| 0x958C0 | PoolRefill | Object pool grow function |")
    lines.append("| 0xEBA70 | ArSerialize | FArchive::Serialize |")
    lines.append("| 0x80D00 | SerDispatch | Serialize dispatcher |")
    lines.append("| 0x4D455C | memcpy IAT | Import Address Table slot |")
    lines.append("")
    lines.append("---\n")

    # Mod config summary
    lines.append("## 8. Current Mod Configuration\n")
    lines.append("| Setting | Value | Notes |")
    lines.append("|---------|-------|-------|")
    lines.append("| g_RosterMult | 2 | Enemy wave multiplier |")
    lines.append("| g_MaxWaveTotal | 8 | Max enemies per wave |")
    lines.append("| MULT_MEM_GATE_MB | 500 | Min free memory to allow grow |")
    lines.append("| MULT_MEM_PER_ADD_MB | 60 | Extra headroom per added enemy |")
    lines.append("| ENABLE_SPAWN_MULT | true | Master spawn switch |")
    lines.append("| ENABLE_AUDIO_ENLARGE | true | Wwise pool 2x enlarger |")
    lines.append("| DESC_STRIDE | (from code) | Bytes per spawn descriptor |")
    lines.append("")

    return '\n'.join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    results = {}

    if cmd in ('runtime', 'all'):
        print("[*] Parsing runtime log...")
        results['runtime'] = parse_runtime_log()
        print(f"    → {results['runtime'].get('total_spawns', 0)} spawns, "
              f"{results['runtime'].get('total_crashes', 0)} crashes")

    if cmd in ('packages', 'all'):
        print("[*] Analyzing packages...")
        results['packages'] = {}
        for pkg_name in LEVEL_PACKAGES[:6]:  # First 6 for speed
            pkg_path = find_package_file(pkg_name)
            if pkg_path:
                print(f"    → {pkg_name} ({pkg_path.name})")
                results['packages'][pkg_name] = analyze_package(pkg_path)
            else:
                results['packages'][pkg_name] = {'error': 'File not found'}

    if cmd in ('spawners', 'all'):
        print("[*] Extracting spawn data...")
        results['spawners'] = {}
        for pkg_name in LEVEL_PACKAGES:
            pkg_path = find_package_file(pkg_name)
            if pkg_path:
                results['spawners'][pkg_name] = dump_spawn_info(pkg_path)

    if cmd in ('physx', 'all'):
        print("[*] Analyzing physics actors...")
        results['physics'] = {}
        for pkg_name in LEVEL_PACKAGES:
            pkg_path = find_package_file(pkg_name)
            if pkg_path:
                results['physics'][pkg_name] = dump_physics_info(pkg_path)

    if cmd in ('classes', 'all'):
        print("[*] Mapping class hierarchy...")
        results['classes'] = map_class_hierarchy()

    if cmd in ('descriptors', 'all'):
        print("[*] Analyzing descriptor layout...")
        results['descriptors'] = analyze_descriptor_layout('S_TWN_P')

    # Generate SDK_MAP.md
    if results:
        print("[*] Writing SDK_MAP.md...")
        md = generate_sdk_map(results)
        with open(SDK_MAP_FILE, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"    → {SDK_MAP_FILE}")
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
