"""
Investigate how BioShock Infinite cooked packages describe enemy spawners.

Goal: discover the REAL spawner classes and the REAL count/spawn-list property
names present in the cooked .xxx packages, so we can decide what to patch
(static path) and what to hook (runtime path). Read-only; never writes.

Usage:
  python tools/investigate_spawners.py <package.xxx> [package2.xxx ...]
  python tools/investigate_spawners.py --auto   # auto-pick a few combat _Game pkgs
"""

import sys
import os
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.ue3_parser import UE3Package
from core.property_patcher import read_properties

COOKED = Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite\XGame\CookedPCConsole_FR")

# Keywords that hint a name relates to spawning / AI population.
NAME_KEYWORDS = [
    'spawn', 'spawner', 'encounter', 'aiwave', 'wave', 'squad', 'population',
    'substantiat', 'reinforce', 'numto', 'maxalive', 'maxspawn', 'spawncount',
    'roster', 'aigamma', 'aidirector', 'aigroup', 'aispawn',
]

# Class names (UE3) that are likely spawner / encounter actors.
SPAWNER_CLASS_HINTS = [
    'spawner', 'spawnai', 'encounter', 'aigamma', 'aiwave', 'aidirector',
    'aigroup', 'substantiat', 'aiscripted', 'population',
]


def dump_package(path):
    print("=" * 78)
    print(f"PACKAGE: {path.name}")
    pkg = UE3Package.from_file(path)
    print(pkg.summary())

    # 1) Name-table entries that look spawn/AI related.
    hits = []
    for i, e in enumerate(pkg.names):
        low = e.name.lower()
        if any(k in low for k in NAME_KEYWORDS):
            hits.append(e.name)
    print(f"\n-- Spawn/AI-related NAMES ({len(hits)}) --")
    for n in sorted(set(hits)):
        print(f"    {n}")

    # 2) Class histogram for all exports (so we see what actor types exist).
    cls_counts = Counter()
    for exp in pkg.exports:
        cls_counts[pkg.resolve_class_name(exp)] += 1
    print(f"\n-- Export CLASS histogram (spawn/AI-relevant) --")
    for cls, cnt in cls_counts.most_common():
        low = cls.lower()
        if any(h in low for h in SPAWNER_CLASS_HINTS) or 'ai' in low or 'spawn' in low:
            print(f"    {cnt:5d}  {cls}")

    # 3) For spawner-like exports, dump their int/bool/object properties.
    spawner_exports = []
    for exp in pkg.exports:
        low = pkg.resolve_class_name(exp).lower()
        if any(h in low for h in SPAWNER_CLASS_HINTS):
            spawner_exports.append(exp)
    print(f"\n-- SPAWNER-like exports: {len(spawner_exports)} --")
    prop_name_counter = Counter()
    for exp in spawner_exports[:25]:
        cls = pkg.resolve_class_name(exp)
        name = pkg.get_name(exp.object_name)
        try:
            props = read_properties(pkg, exp)
        except Exception as ex:
            print(f"    [{exp.index}] {name} ({cls}) <props error: {ex}>")
            continue
        interesting = [p for p in props
                       if p.type_name in ('IntProperty', 'BoolProperty',
                                           'ByteProperty', 'ObjectProperty',
                                           'ArrayProperty')]
        for p in props:
            prop_name_counter[p.name] += 1
        shown = ", ".join(repr(p) for p in interesting[:10])
        print(f"    [{exp.index}] {name} ({cls}) [{len(props)} props]: {shown}")

    if prop_name_counter:
        print(f"\n-- Property-name frequency on spawner exports --")
        for pn, c in prop_name_counter.most_common(40):
            print(f"    {c:4d}  {pn}")

    # 4) Targeted dump of the Kismet spawn-action classes (the real lever).
    TARGET_CLASSES = [
        'XSeqAct_SpawnAI', 'XSeqAct_SpawnScriptedAI', 'XAIScriptedSpawner',
        'XSeqAct_DespawnAI', 'XAIGammaSpawner', 'XAIGammaSpawningVolume',
        'XAIScriptedSpawningVolume',
    ]
    for tc in TARGET_CLASSES:
        exps = pkg.find_exports_by_class(tc)
        if not exps:
            continue
        print(f"\n== CLASS {tc}: {len(exps)} export(s) ==")
        for exp in exps[:12]:
            name = pkg.get_name(exp.object_name)
            try:
                props = read_properties(pkg, exp)
            except Exception as ex:
                print(f"    [{exp.index}] {name} <props error: {ex}>")
                continue
            print(f"    [{exp.index}] {name} [{len(props)} props, {exp.serial_size}B]")
            for p in props:
                print(f"          {p!r}")

    return pkg


CANDIDATE_COUNT_NAMES = [
    'SpawnCount', 'SpawnInfo', 'AISpawnInfo', 'SpawnedAIsList', 'Spawners',
    'NumToSpawn', 'MaxAlive', 'MaxSpawned', 'TotalToSpawn', 'WaveSize',
    'SmallWaveSize1', 'MedWaveSize', 'MedWaveSize1', 'LargeWaveSize',
    'LargeWaveSize1', 'InitialWave', 'RespawnIfDead', 'MaxTriggerCount',
]


def scan_property_usage(path):
    """For each candidate name, find exports that carry it as a property and
    report the property type + value. Class-agnostic; this is what we'd patch."""
    print("=" * 78)
    print(f"PROPERTY-USAGE SCAN: {path.name}")
    pkg = UE3Package.from_file(path)

    want = set(CANDIDATE_COUNT_NAMES)
    # export class -> Counter of (propname,type) ; plus sample values
    by_class = defaultdict(Counter)
    samples = defaultdict(list)
    scanned = 0
    errors = 0
    for exp in pkg.exports:
        if exp.serial_size <= 8:
            continue
        try:
            props = read_properties(pkg, exp)
        except Exception:
            errors += 1
            continue
        scanned += 1
        cls = pkg.resolve_class_name(exp)
        for p in props:
            if p.name in want:
                key = (p.name, p.type_name)
                by_class[cls][key] += 1
                if len(samples[(cls, p.name)]) < 4:
                    if p.type_name == 'IntProperty':
                        v = p.int_value
                    elif p.type_name == 'FloatProperty':
                        v = round(p.float_value, 3)
                    else:
                        v = f'{p.size}B'
                    samples[(cls, p.name)].append(v)

    print(f"  scanned {scanned} exports ({errors} prop-parse errors)")
    if not by_class:
        print("  No candidate spawn-count properties found as tagged props.")
    for cls, counter in sorted(by_class.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"\n  CLASS {cls}:")
        for (pn, tn), c in counter.most_common():
            sv = samples.get((cls, pn), [])
            print(f"      {c:4d}x  {pn} ({tn})  samples={sv}")
    return pkg


def auto_pick():
    # A handful of combat encounter sub-packages likely to hold spawners.
    candidates = [
        'S_TWN_FairStreet_Game', 'S_TWN_Alley_Game', 'S_BW_Middletown_Game',
        'S_Fink_Hub_Game', 'S_EMP_Street_Game', 'S_DCOM_Atrium_Game',
    ]
    out = []
    for c in candidates:
        p = COOKED / f"{c}.xxx"
        if p.exists():
            out.append(p)
    if not out:
        # fall back: any _Game package
        for p in sorted(COOKED.glob("*_Game*.xxx"))[:4]:
            out.append(p)
    return out


def main():
    args = sys.argv[1:]
    mode = dump_package
    if args and args[0] == '--props':
        mode = scan_property_usage
        args = args[1:]
    if not args or args[0] == '--auto':
        paths = auto_pick()
        args = [a for a in args if a != '--auto']
    else:
        paths = [Path(a) if os.path.isabs(a) else COOKED / a for a in args]
    if not paths:
        print("No packages found to inspect.")
        return
    for p in paths:
        if not p.exists():
            print(f"MISSING: {p}")
            continue
        try:
            mode(p)
        except Exception as ex:
            import traceback
            print(f"ERROR parsing {p.name}: {ex}")
            traceback.print_exc()


if __name__ == '__main__':
    main()
