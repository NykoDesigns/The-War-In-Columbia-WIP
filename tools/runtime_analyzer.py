"""
The War In Columbia — Runtime Analyzer
=======================================
Watches wic_spawn.log in real-time and provides:
  - Live actor census
  - Crash pattern detection
  - PhysX load estimation
  - Memory pressure tracking
  - Descriptor diff analysis from DESC-DIFF log entries

Usage:
  python tools/runtime_analyzer.py watch    - Tail log in real-time with analysis
  python tools/runtime_analyzer.py summary  - One-shot summary of current log
  python tools/runtime_analyzer.py physx    - PhysX load analysis
  python tools/runtime_analyzer.py desc     - Descriptor field analysis
"""

import sys
import os
import re
import time
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
LOG_FILE = Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\wic_spawn.log")


# ─── Log Patterns ─────────────────────────────────────────────────────────────

RE_TIMESTAMP = re.compile(r'\[(\d+:\d+\.\d+)\]')
RE_SPAWN = re.compile(r"SPAWN #(\d+): class='([^']+)' name='([^']+)'")
RE_ROSTER_GROW = re.compile(r'ROSTER-GROW array=0x([0-9A-Fa-f]+) Num (\d+)->(\d+)')
RE_CRASH = re.compile(r'\*\*\* CRASH code=0x([0-9A-Fa-f]+) fault=0x([0-9A-Fa-f]+).*?(READ|WRITE|EXEC)')
RE_MEMCPY_GUARD = re.compile(r'MEMCPY-GUARD #(\d+): BLOCKED count=(\d+)')
RE_POOL_GROW = re.compile(r'POOL-GROW #(\d+): pool=0x([0-9A-Fa-f]+)')
RE_PATCH = re.compile(r'STREAMREAD-PATCH: patched (JLE->JBE) at 0x([0-9A-Fa-f]+).*?\[(\w+)\]')
RE_BUILD_CONFIG = re.compile(r'BUILD CONFIG: SpawnMult=(\w+) x(\d+)')
RE_DESC_DIFF = re.compile(r'DESC-DIFF')
RE_AI_CONTROLLER = re.compile(r"class='(XAI\w*Controller\w*)'")

# Physics-relevant actor classes (actors that create PhysX constraints)
PHYSX_HEAVY_CLASSES = {
    'XGamePawn', 'XAIPawn', 'XGameNPC', 'XAIController',
    'KActor', 'KAsset', 'RigidBody', 'PhysXDestructible',
    'SkeletalMeshActor',  # ragdolls
}

# Estimated PhysX constraint count per class
PHYSX_WEIGHT = {
    'XAIPawn': 15,        # Ragdoll (15 constraints per skeleton)
    'XGamePawn': 15,
    'XGameNPC': 15,
    'XAIController': 0,   # No physics directly, but implies a pawn
    'KActor': 3,          # Simple rigid body
    'KAsset': 5,          # Physics prop
    'SkeletalMeshActor': 10,
}

# PhysX has internal limits around 4096 active constraints in 32-bit builds
PHYSX_CONSTRAINT_LIMIT = 4096


# ─── Analysis Functions ───────────────────────────────────────────────────────

def parse_log(log_path=None):
    """Full parse of the log file."""
    if log_path is None:
        log_path = LOG_FILE
    if not log_path.exists():
        return None

    with open(log_path, 'r', errors='replace') as f:
        lines = f.readlines()

    data = {
        'spawns': [],
        'ai_controllers': [],
        'crashes': [],
        'roster_grows': [],
        'memcpy_guards': 0,
        'pool_grows': 0,
        'patches': [],
        'build_config': None,
        'session_duration': None,
        'total_lines': len(lines),
    }

    last_timestamp = None
    for line in lines:
        # Timestamp
        ts_match = RE_TIMESTAMP.match(line)
        if ts_match:
            last_timestamp = ts_match.group(1)

        # Spawns
        m = RE_SPAWN.search(line)
        if m:
            data['spawns'].append({
                'num': int(m.group(1)),
                'class': m.group(2),
                'name': m.group(3),
                'time': last_timestamp,
            })
            if 'Controller' in m.group(2):
                data['ai_controllers'].append({
                    'class': m.group(2),
                    'name': m.group(3),
                    'time': last_timestamp,
                })
            continue

        # Roster grows
        m = RE_ROSTER_GROW.search(line)
        if m:
            data['roster_grows'].append({
                'array': m.group(1),
                'from': int(m.group(2)),
                'to': int(m.group(3)),
                'time': last_timestamp,
            })
            continue

        # Crashes
        m = RE_CRASH.search(line)
        if m:
            data['crashes'].append({
                'code': m.group(1),
                'fault': m.group(2),
                'type': m.group(3),
                'time': last_timestamp,
                'line': line.strip(),
            })
            continue

        # Guards
        if 'MEMCPY-GUARD' in line:
            data['memcpy_guards'] += 1
        elif 'POOL-GROW' in line:
            data['pool_grows'] += 1

        # Patches
        m = RE_PATCH.search(line)
        if m:
            data['patches'].append(f"{m.group(1)} @ 0x{m.group(2)} [{m.group(3)}]")

        # Build config
        m = RE_BUILD_CONFIG.search(line)
        if m:
            data['build_config'] = f"SpawnMult={m.group(1)} x{m.group(2)}"

    data['session_duration'] = last_timestamp
    return data


def estimate_physx_load(data):
    """Estimate PhysX constraint load from spawned actors."""
    class_counts = Counter(s['class'] for s in data['spawns'])
    total_constraints = 0
    breakdown = []

    for cls, count in class_counts.most_common():
        weight = PHYSX_WEIGHT.get(cls, 0)
        # Heuristic: if class name contains Pawn/NPC, assume ragdoll weight
        if weight == 0:
            if 'Pawn' in cls or 'NPC' in cls:
                weight = 15
            elif 'Actor' in cls and 'Camera' not in cls and 'Matinee' not in cls:
                weight = 2
        constraints = weight * count
        if constraints > 0:
            breakdown.append({
                'class': cls,
                'count': count,
                'weight': weight,
                'total_constraints': constraints,
            })
            total_constraints += constraints

    return {
        'total_estimated_constraints': total_constraints,
        'limit': PHYSX_CONSTRAINT_LIMIT,
        'usage_pct': (total_constraints / PHYSX_CONSTRAINT_LIMIT) * 100,
        'breakdown': sorted(breakdown, key=lambda x: -x['total_constraints']),
    }


def print_summary(data):
    """Print a formatted summary."""
    if not data:
        print("❌ No log data available")
        return

    print("=" * 60)
    print("  RUNTIME ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"\n  Session duration: {data['session_duration']}")
    print(f"  Build config: {data['build_config'] or 'Unknown'}")
    print(f"  Log lines: {data['total_lines']}")

    print(f"\n── Actor Census ──")
    print(f"  Total spawns: {len(data['spawns'])}")
    print(f"  AI Controllers: {len(data['ai_controllers'])}")
    class_counts = Counter(s['class'] for s in data['spawns'])
    print(f"\n  Top 15 classes:")
    for cls, count in class_counts.most_common(15):
        marker = " ⚠️" if cls in PHYSX_HEAVY_CLASSES else ""
        print(f"    {cls:40s} {count:4d}{marker}")

    print(f"\n── Spawn Multiplier ──")
    print(f"  Roster grows: {len(data['roster_grows'])}")
    if data['roster_grows']:
        total_added = sum(r['to'] - r['from'] for r in data['roster_grows'])
        print(f"  Total enemies added: {total_added}")
        print(f"  Grow events:")
        for r in data['roster_grows'][-5:]:
            print(f"    [{r['time']}] {r['from']}→{r['to']} (+{r['to']-r['from']})")

    print(f"\n── Stability ──")
    print(f"  Patches applied: {len(data['patches'])}")
    for p in data['patches']:
        print(f"    ✅ {p}")
    print(f"  Memcpy guards triggered: {data['memcpy_guards']}")
    print(f"  Pool grows: {data['pool_grows']}")
    print(f"  Crashes: {len(data['crashes'])}")
    for c in data['crashes'][-3:]:
        print(f"    ❌ [{c['time']}] {c['type']} @ 0x{c['fault']}")

    # PhysX analysis
    physx = estimate_physx_load(data)
    print(f"\n── PhysX Load Estimate ──")
    print(f"  Estimated constraints: {physx['total_estimated_constraints']} / {physx['limit']}")
    print(f"  Load: {physx['usage_pct']:.1f}%")
    if physx['usage_pct'] > 80:
        print(f"  ⚠️  HIGH PHYSX LOAD — crash risk!")
    print(f"\n  Top contributors:")
    for b in physx['breakdown'][:8]:
        print(f"    {b['class']:35s} {b['count']:3d} actors × {b['weight']:2d} = {b['total_constraints']:4d}")

    print("\n" + "=" * 60)


def watch_log():
    """Tail the log file and print live updates."""
    if not LOG_FILE.exists():
        print(f"Waiting for log file: {LOG_FILE}")
        while not LOG_FILE.exists():
            time.sleep(1)

    print(f"📡 Watching: {LOG_FILE}")
    print("   (Ctrl+C to stop)\n")

    with open(LOG_FILE, 'r', errors='replace') as f:
        # Seek to end
        f.seek(0, 2)
        spawn_count = 0
        controller_count = 0
        crash_count = 0

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue

            line = line.strip()
            # Colorize output based on type
            if 'SPAWN' in line:
                spawn_count += 1
                m = RE_SPAWN.search(line)
                if m and 'Controller' in m.group(2):
                    controller_count += 1
                    print(f"  🤖 AI#{controller_count}: {m.group(2)} '{m.group(3)}'")
                elif m and ('Pawn' in m.group(2) or 'NPC' in m.group(2)):
                    print(f"  👤 {m.group(2)} '{m.group(3)}'")
            elif 'ROSTER-GROW' in line:
                print(f"  📈 {line}")
            elif '*** CRASH' in line:
                crash_count += 1
                print(f"\n  ❌ CRASH #{crash_count}: {line}\n")
            elif 'MEMCPY-GUARD' in line:
                print(f"  🛡️ {line}")
            elif 'POOL-GROW' in line:
                print(f"  🔧 {line}")
            elif 'STREAMREAD-PATCH' in line:
                print(f"  ✅ {line}")
            elif 'FATAL' in line.upper() or 'ERROR' in line.upper():
                print(f"  ⚠️ {line}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'watch':
        watch_log()
    elif cmd == 'summary':
        data = parse_log()
        print_summary(data)
    elif cmd == 'physx':
        data = parse_log()
        if data:
            physx = estimate_physx_load(data)
            print(f"\nPhysX Constraint Estimate:")
            print(f"  Total: {physx['total_estimated_constraints']} / {physx['limit']} "
                  f"({physx['usage_pct']:.1f}%)")
            print(f"\n  Breakdown:")
            for b in physx['breakdown']:
                pct = (b['total_constraints'] / physx['limit']) * 100
                bar = '█' * int(pct / 2) + '░' * (50 - int(pct / 2))
                print(f"  {b['class']:35s} {b['total_constraints']:4d} ({pct:.1f}%) {bar}")
    elif cmd == 'desc':
        data = parse_log()
        if data:
            # Look for DESC-DIFF entries
            print("Descriptor diff entries from log (if available)...")
            with open(LOG_FILE, 'r', errors='replace') as f:
                for line in f:
                    if 'DESC-DIFF' in line or 'DESC_' in line or 'DESCRIPTOR' in line:
                        print(f"  {line.strip()}")
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
