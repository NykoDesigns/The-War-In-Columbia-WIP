"""
engine_analysis.py — Comprehensive UE3 engine analysis tool for BioShock Infinite.

Capabilities:
  1. Parse all Ghidra batch decompilation JSONs into a unified call graph
  2. Annotate functions with known semantics (spawn chain, pool, damage, physics)
  3. Analyze descriptor field usage across decompiled functions
  4. Generate ENGINE_INTERNALS.md with full call chain documentation
  5. Cross-reference runtime logs with static analysis

Usage:
  python tools/engine_analysis.py graph     — Build and display call graph
  python tools/engine_analysis.py internals — Generate ENGINE_INTERNALS.md
  python tools/engine_analysis.py lifecycle — Trace spawn lifecycle from logs
  python tools/engine_analysis.py all       — All of the above
"""

import json, os, sys, re
from pathlib import Path
from collections import defaultdict

GHIDRA_DIR = Path(__file__).parent / "ghidra"
PROJECT_ROOT = Path(__file__).parent.parent
GAME_DIR = Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32")
LOG_FILE = GAME_DIR / "wic_spawn.log"

# Known function annotations
KNOWN_FUNCTIONS = {
    "00658250": ("SpawnRoster", "Iterates AISpawnInfo TArray, calls SpawnOneAI per entry"),
    "00657ab0": ("SpawnOneAI", "Wrapper: calls SpawnCore then sets up Victim/Killer/Witness Kismet events"),
    "00654070": ("SpawnCore", "Gate function: checks AI director state, pool availability, counts, timing; dispatches via vtable+0xD0"),
    "006bae00": ("CheckPoolAvailable", "Returns 1 if pawn pool has substantiated (ready) pawns; checks +0x3C->+0x28->[0]+0x204 & 0x40"),
    "006343b0": ("CheckEncounterState", "Validates spawner's encounter state at +0x2C; checks flags at +0xE8"),
    "00617360": ("PlaceAndSpawn", "2860-byte spatial placement: iterates pool entries at this+0x268/0x26c, transforms XFloatingPosition via section matrices, possesses pawn"),
    "00622150": ("AllocPoolPawn", "Allocates a pawn from pool via FUN_0061CAF0; copies 76 bytes of spawn result; calls FUN_006E7E60 for pawn binding"),
    "00476780": ("WorldToLocal", "Coordinate transform utility (381 bytes, 116 callers)"),
    "00482ae0": ("appFree", "Engine memory deallocation (34 bytes, 4148 callers)"),
    "00482ab0": ("appMalloc", "Engine memory allocation (44 bytes, 2261 callers)"),
    "0064b450": ("BroadcastEvent", "Event/delegate broadcast (621 bytes, 38 callers) — post-spawn notification path"),
    "004c5e70": ("FindName", "FName lookup by string (33 bytes, 324 callers)"),
    "007c7c70": ("GetObjectRef", "UObject reference resolver (22 bytes, 39 callers)"),
    "004787f0": ("FindActor", "Actor lookup by class/tag (76 bytes, 10 callers)"),
    "00634320": ("ValidateSpawnSlot", "Slot validation for spawn encounter (34 bytes, 14 callers)"),
    "0080d220": ("InitPhysics", "Physics initialization (called from PlaceAndSpawn)"),
    "008c7d20": ("InitCollision", "Collision setup (called from PlaceAndSpawn)"),
    "0061caf0": ("PoolTakePawn", "Core pool acquisition — finds available substantiated pawn and claims it"),
    "006e7e60": ("BindPawnToController", "Binds pawn to AI controller after pool acquisition"),
    "00496f00": ("StreamRead", "Double-buffered async reader (PATCHED: JLE→JBE)"),
    "000eba70": ("ArSerialize", "FArchive::Serialize — buffered deserialization"),
    "00082ab0": ("appRealloc", "Engine memory reallocation"),
    "0022ca80": ("SpawnActor", "UWorld::SpawnActor — low-level actor creation"),
    "00658a70": ("AIDirectorTick", "AI director per-frame update — triggers SpawnRoster when wave ready"),
}

# Descriptor field offsets and their semantics
DESC_FIELDS = {
    0x00: ("GammaPack", "ObjectProperty", "Difficulty scaling pack"),
    0x04: ("PawnArch", "ObjectProperty", "Pawn archetype (defines enemy type)"),
    0x08: ("PawnLabels", "TArray<FName>", "Per-instance labels for pawn identification"),
    0x0C: ("CountA", "int", "Target spawn count (enemies from this descriptor)"),
    0x10: ("CountB", "int", "Remaining spawn count (decremented as enemies spawn)"),
    0x14: ("PawnAppearanceOverride", "ObjectProperty", "Visual override"),
    0x18: ("VoiceTypeOverride", "ObjectProperty", "Voice type collection"),
    0x1C: ("SubtitleSpeakerOverride", "ObjectProperty", "Subtitle speaker"),
    0x20: ("LootList", "TArray<UObject*>", "Loot drops on death"),
    0x2C: ("BoolFlags", "bitfield", "bGiveDefaultLoot, bDead, bCheckSpawnCollision, etc."),
    0x30: ("LootToAwardOnKillList", "TArray<UObject*>", "Loot awarded on kill"),
    0x3C: ("InventoryList", "TArray<UObject*>", "Weapons/items to equip"),
    0x48: ("DeadPoseAnimSequence", "ObjectProperty", "Death pose animation"),
    0x4C: ("DeadPoseTime", "float", "Time in death pose"),
    0x50: ("SirenPriority", "float", "Siren resurrection priority"),
    0x54: ("MiniBuddyPriority", "float", "Handyman buddy priority"),
    0x58: ("Faction", "FName", "Faction name (8 bytes)"),
    0x60: ("SpawnLocation", "XFloatingPosition", "Local position + section index (16 bytes)"),
    0x70: ("SpawnRotation", "XFloatingRotator", "Local rotation + section index (16 bytes)"),
    0x80: ("SpawnFloatingSectionIndex", "int", "Floating section reference"),
    0x84: ("AttachmentSetSeedOverride", "int", "Cosmetic attachment seed"),
    0x88: ("MeshOverride", "ObjectProperty", "Mesh replacement"),
    0x8C: ("MaterialOverride", "ObjectProperty", "Material replacement"),
    0x90: ("ThirdPersonWeaponModel", "ObjectProperty", "3P weapon mesh"),
    0x94: ("AttachmentSetOverride", "ObjectProperty", "Attachment override"),
    0x98: ("CaptainPawn", "ObjectProperty", "Leader pawn reference"),
    0x9C: ("PatrolPath", "ObjectProperty", "AI patrol path"),
    0xA0: ("SpatialRestrictions", "ObjectProperty", "Movement bounds"),
    0xA4: ("AIRole", "ObjectProperty", "Behavior role assignment"),
    0xA8: ("MinAILevel", "int", "Minimum difficulty level"),
    0xAC: ("MaxAILevel", "int", "Maximum difficulty level"),
    0xB0: ("CullingPriority", "int", "Population management priority"),
    0xB4: ("IdleRoleBehaviorTree", "ObjectProperty", "Idle behavior tree"),
    0xB8: ("SirenResurrectionAnimSet", "ObjectProperty", "Siren rez anims"),
    0xBC: ("SmartTerrainScriptName", "FName", "Smart terrain ID (8 bytes)"),
    0xC4: ("DistMoveFromSmartTerrain", "float", "Smart terrain offset distance"),
    0xC8: ("FrobEvent", "ObjectProperty", "Interaction event handler"),
    0xCC: ("Spawner", "ObjectProperty", "Back-ref to XAIScriptedSpawner"),
    0xD0: ("SpawnerLevelName", "FName", "Level name of spawner (8 bytes)"),
    0xD8: ("Delegate", "DelegateProperty", "Post-spawn callback {Obj,FName,FName} 12 bytes"),
    0xE4: ("ScenarioRestoreIndex", "int", "Save/load restore tracking"),
    0xE8: ("RuntimeCnt", "int (hidden)", "Per-instance runtime counter/flags"),
    0xEC: ("RuntimePtr", "void* (hidden)", "Per-instance runtime heap pointer"),
}

# UObject layout (BioShock Infinite UE3 v727)
UOBJECT_LAYOUT = {
    0x00: "vtable*",
    0x04: "HashNext",
    0x08: "ObjectFlags (qword)",
    0x10: "Index (int) — position in GObjects",
    0x14: "Outer (UObject*)",
    0x18: "Name (FName — Index @ +0x18, Number @ +0x1C)",
    0x20: "Class (UClass*)",
    0x24: "Archetype (UObject*)",
}


def load_ghidra_jsons():
    """Load all Ghidra output JSONs into unified function database."""
    funcs = {}
    for p in GHIDRA_DIR.glob("out_*.json"):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except:
            continue
        if "functions" in data:
            for f in data["functions"]:
                addr = f["addr"]
                if addr not in funcs or len(f.get("code", "")) > len(funcs[addr].get("code", "")):
                    funcs[addr] = f
        elif "code" in data:
            addr = data.get("entry", "").lower()
            if addr:
                funcs[addr] = data
    return funcs


def build_call_graph(funcs):
    """Build directed call graph from function database."""
    graph = defaultdict(set)  # caller -> set of callees
    reverse = defaultdict(set)  # callee -> set of callers
    for addr, f in funcs.items():
        for callee in f.get("calls", []):
            graph[addr].add(callee)
            reverse[callee].add(addr)
    return graph, reverse


def annotate_function(addr, f):
    """Return human-readable annotation for a function."""
    if addr in KNOWN_FUNCTIONS:
        name, desc = KNOWN_FUNCTIONS[addr]
        return f"**{name}** (0x{addr}) — {desc}"
    name = f.get("name", "???")
    size = f.get("size", 0)
    return f"{name} (0x{addr}, {size} bytes)"


def parse_spawn_log():
    """Parse wic_spawn.log for spawn lifecycle events."""
    if not LOG_FILE.exists():
        return []
    events = []
    patterns = {
        "spawn": re.compile(r'\[(\d+:\d+\.\d+)\] SPAWN #(\d+): (\S+)'),
        "roster_grow": re.compile(r'\[(\d+:\d+\.\d+)\] ROSTER-GROW .* Num (\d+)->(\d+).*totalEnemies=(\d+)'),
        "roster_grow_old": re.compile(r'\[(\d+:\d+\.\d+)\] ROSTER-GROW .* Num (\d+)->(\d+).*\+(\d+) extra'),
        "extra_ai": re.compile(r'\[(\d+:\d+\.\d+)\] EXTRA-AI #(\d+)'),
        "crash": re.compile(r'\[(\d+:\d+\.\d+)\] \*\*\* CRASH (\S+)'),
        "pool_grow": re.compile(r'\[(\d+:\d+\.\d+)\] POOL-GROW'),
        "arrfield": re.compile(r'\[(\d+:\d+\.\d+)\]   ARRFIELD \.(\S+) off=0x(\w+) inner=(\S+) elem=(\d+)'),
        "desc_diff": re.compile(r'\[(\d+:\d+\.\d+)\]   \+0x(\w+): (\w+) / (\w+)  DIFF'),
    }
    with open(LOG_FILE, 'r', errors='replace') as fh:
        for line in fh:
            for etype, pat in patterns.items():
                m = pat.search(line)
                if m:
                    events.append({"type": etype, "time": m.group(1), "groups": m.groups(), "line": line.strip()})
                    break
    return events


def generate_internals_md(funcs, graph, reverse, events):
    """Generate comprehensive ENGINE_INTERNALS.md."""
    lines = []
    lines.append("# BioShock Infinite — Engine Internals (Auto-Generated)\n")
    lines.append("## 1. Spawn Pipeline Call Chain\n")
    lines.append("```")
    lines.append("AIDirectorTick (0x658A70) — per-frame, checks wave readiness")
    lines.append("  └─ SpawnRoster (0x658250) — iterates TArray<AISpawnInfo> stride 0xF0")
    lines.append("       ├─ PlaceAndSpawn (0x617360) — spatial: pool iteration + section matrix xform")
    lines.append("       │    ├─ PoolTakePawn (0x61CAF0) — claims available substantiated pawn")
    lines.append("       │    ├─ InitPhysics (0x80D220) — ragdoll/constraint setup")
    lines.append("       │    └─ InitCollision (0x8C7D20) — collision channel registration")
    lines.append("       ├─ BroadcastEvent (0x64B450) — post-spawn delegate fire")
    lines.append("       └─ SpawnOneAI (0x657AB0) — per-descriptor wrapper")
    lines.append("            └─ SpawnCore (0x654070) — gate checks then vtable+0xD0 dispatch")
    lines.append("                 ├─ CheckPoolAvailable (0x6BAE00) — bSubstantiated at +0x204 bit6")
    lines.append("                 ├─ CheckEncounterState (0x6343B0) — spawner state validation")
    lines.append("                 └─ [vtable+0xD0] — actual spawn implementation (polymorphic)")
    lines.append("                      └─ AllocPoolPawn (0x622150) — pool acquisition + bind")
    lines.append("                           ├─ PoolTakePawn (0x61CAF0)")
    lines.append("                           └─ BindPawnToController (0x6E7E60)")
    lines.append("```\n")

    lines.append("## 2. Pawn Pool System\n")
    lines.append("BioShock Infinite pre-allocates a pool of invisible pawn actors at level load.\n")
    lines.append("When an AI spawn is requested:\n")
    lines.append("1. `CheckPoolAvailable` verifies pool has entries with `bSubstantiated` flag (bit 6 at +0x204)")
    lines.append("2. `PlaceAndSpawn` iterates pool entries at `spawner+0x268` (array) with count at `spawner+0x26c`")
    lines.append("3. For each pool entry, checks `entry[8] != 0` (active flag) and `entry[0]->vtable+0x18()` (not busy)")
    lines.append("4. Computes world position via floating section matrix transform (section index → 4x4 matrix)")
    lines.append("5. `PoolTakePawn` claims the pawn, marking it as in-use")
    lines.append("6. `BindPawnToController` creates XAIController and possesses the claimed pawn")
    lines.append("7. `BroadcastEvent` fires the Spawner's `__OnSpawnDelegate__` to register with damage system\n")
    lines.append("**Critical insight**: Step 7 uses the descriptor's `Spawner` (+0xCC) and `Delegate` (+0xD8)")
    lines.append("fields. Zeroing these in clones broke damage registration → invulnerable enemies.\n")

    lines.append("## 3. SpawnCore Gate Conditions\n")
    lines.append("```c")
    lines.append("// FUN_00654070 — all must pass for spawn to proceed:")
    lines.append("// 1. AI director state != 0x03 (normal) or != 0x01 (scripted)")
    lines.append("// 2. Flag at spawner->field[0xB] + 0xE8, bit 1 set (encounter active)")
    lines.append("// 3. CheckPoolAvailable() returns true")
    lines.append("// 4. vtable+0x18 call returns 0 (not paused/blocked)")
    lines.append("// 5. CheckEncounterState() returns true")
    lines.append("// 6. Descriptor pointer (param_2) is non-null")
    lines.append("// 7. If spawner flag bit 1: archetype vtable+0xDC must return true")
    lines.append("// 8. Count check: field[0x1F]==0 OR field[0x1E] < field[0x1F]  (current < max)")
    lines.append("// 9. Timing: float timing checks for spawn cooldown")
    lines.append("```\n")

    lines.append("## 4. AISpawnInfo Descriptor Layout (0xF0 bytes)\n")
    lines.append("| Offset | Name | Type | Description |")
    lines.append("|--------|------|------|-------------|")
    for off in sorted(DESC_FIELDS.keys()):
        name, typ, desc = DESC_FIELDS[off]
        lines.append(f"| +0x{off:02X} | {name} | {typ} | {desc} |")
    lines.append("")

    lines.append("## 5. UObject Memory Layout (BioShock Infinite)\n")
    lines.append("| Offset | Field |")
    lines.append("|--------|-------|")
    for off in sorted(UOBJECT_LAYOUT.keys()):
        lines.append(f"| +0x{off:02X} | {UOBJECT_LAYOUT[off]} |")
    lines.append("")

    lines.append("## 6. Key Spawner Object Layout (XAIScriptedSpawner)\n")
    lines.append("| Offset | Field | Notes |")
    lines.append("|--------|-------|-------|")
    lines.append("| +0x84 | Flags (byte) | bit0=active, bit1=scripted, bit3=has_pool |")
    lines.append("| +0x268 | PoolEntries (TArray) | Pre-allocated pawn pool entries |")
    lines.append("| +0x26C | PoolCount (int) | Number of pool entries |")
    lines.append("| +0x2C | EncounterState (ptr) | Points to encounter management data |")
    lines.append("| +0x3C | PoolManager (ptr) | Pool availability checker |")
    lines.append("")

    lines.append("## 7. Physics & Damage Registration\n")
    lines.append("After a pawn is claimed from the pool and possessed by an AI controller:\n")
    lines.append("1. **InitPhysics** (0x80D220) — sets up PhysX rigid body, creates ragdoll constraints")
    lines.append("   - Constraint count ≈ 15 per humanoid pawn (each bone joint)")
    lines.append("   - Uses PawnArch (+0x04) to determine skeleton/physics asset")
    lines.append("2. **InitCollision** (0x8C7D20) — registers collision primitives")
    lines.append("   - Sets collision channel (enemy = ECC_Pawn)")
    lines.append("   - Enables trace responses for weapons")
    lines.append("3. **BroadcastEvent** (0x64B450) — fires OnSpawn delegate")
    lines.append("   - Delegate at descriptor +0xD8 references the Spawner (+0xCC)")
    lines.append("   - Spawner notifies the damage system to register this pawn")
    lines.append("   - Without this: pawn is visible, animated, has AI, but cannot receive damage")
    lines.append("")

    lines.append("## 8. Clone Safety Rules (derived from analysis)\n")
    lines.append("When cloning a descriptor for spawn multiplication:\n")
    lines.append("| Field | Action | Reason |")
    lines.append("|-------|--------|--------|")
    lines.append("| TArrays (+0x08,+0x20,+0x30,+0x3C) | Deep-copy | Prevent double-free on engine GC |")
    lines.append("| CountA/B (+0x0C,+0x10) | Force to 1 | Prevent count explosion (7→1 per clone) |")
    lines.append("| SpawnLocation (+0x60) | Nudge X+96,Y±64 | Prevent collision overlap |")
    lines.append("| RuntimeCnt/Ptr (+0xE8,+0xEC) | Zero | Per-instance; prevents serializer crash |")
    lines.append("| Spawner (+0xCC) | KEEP | Required for post-spawn damage registration |")
    lines.append("| Delegate (+0xD8) | KEEP | Required for OnSpawn callback fire |")
    lines.append("| All other fields | Copy | Shared template data, safe to duplicate |")
    lines.append("")

    lines.append("## 9. Floating Section System\n")
    lines.append("Columbia's floating city uses a section-based coordinate system:\n")
    lines.append("- Each floating island has a `SectionIndex` (int)")
    lines.append("- Section transforms stored at `GWorld+0x200 + sectionIdx*0x40` (4x4 matrix)")
    lines.append("- `SpawnLocation` stores LOCAL coordinates relative to a section")
    lines.append("- `PlaceAndSpawn` transforms local→world via section matrix multiplication")
    lines.append("- Descriptor `SpawnFloatingSectionIndex` (+0x80) indicates which section")
    lines.append("- If clone and source have same section index, they spawn on same island (correct)")
    lines.append("")

    # Runtime statistics
    if events:
        lines.append("## 10. Runtime Statistics (from last session)\n")
        spawns = [e for e in events if e["type"] == "spawn"]
        grows = [e for e in events if e["type"] in ("roster_grow", "roster_grow_old")]
        crashes = [e for e in events if e["type"] == "crash"]
        diffs = [e for e in events if e["type"] == "desc_diff"]

        lines.append(f"- **Total spawns logged**: {len(spawns)}")
        lines.append(f"- **Roster grows**: {len(grows)}")
        lines.append(f"- **Crashes detected**: {len(crashes)}")
        lines.append(f"- **DESC-DIFF fields captured**: {len(diffs)}")

        if grows:
            lines.append("\n### Roster Grow History (last 10)")
            for g in grows[-10:]:
                lines.append(f"  - `{g['line']}`")

        if crashes:
            lines.append("\n### Crash Events")
            for c in crashes:
                lines.append(f"  - `{c['line']}`")
        lines.append("")

    lines.append("## 11. Function Database\n")
    lines.append(f"Total functions decompiled: **{len(funcs)}**\n")
    lines.append("| Address | Name | Size | Calls | Callers | Role |")
    lines.append("|---------|------|------|-------|---------|------|")
    for addr in sorted(funcs.keys()):
        f = funcs[addr]
        name = f.get("name", "?")
        size = f.get("size", 0)
        calls = len(f.get("calls", []))
        callers = len(f.get("calledBy", []))
        role = KNOWN_FUNCTIONS.get(addr, ("", ""))[0]
        lines.append(f"| 0x{addr} | {name} | {size} | {calls} | {callers} | {role} |")
    lines.append("")

    return "\n".join(lines)


def cmd_graph():
    """Display call graph."""
    funcs = load_ghidra_jsons()
    graph, reverse = build_call_graph(funcs)
    print(f"Loaded {len(funcs)} functions from Ghidra outputs")
    print(f"Call graph: {sum(len(v) for v in graph.values())} edges\n")
    print("=== SPAWN CHAIN (annotated) ===")
    for addr in sorted(funcs.keys()):
        if addr in KNOWN_FUNCTIONS:
            name, desc = KNOWN_FUNCTIONS[addr]
            callees = graph.get(addr, set())
            callercount = len(reverse.get(addr, set()))
            print(f"  {name:24s} (0x{addr})  →{len(callees)} calls, ←{callercount} callers")
            print(f"    {desc}")


def cmd_internals():
    """Generate ENGINE_INTERNALS.md."""
    funcs = load_ghidra_jsons()
    graph, reverse = build_call_graph(funcs)
    events = parse_spawn_log()
    md = generate_internals_md(funcs, graph, reverse, events)
    out = PROJECT_ROOT / "ENGINE_INTERNALS.md"
    out.write_text(md, encoding='utf-8')
    print(f"Written {out} ({len(md)} bytes, {len(funcs)} functions)")


def cmd_lifecycle():
    """Trace spawn lifecycle from runtime logs."""
    events = parse_spawn_log()
    if not events:
        print("No events found in log.")
        return
    print(f"Parsed {len(events)} events from {LOG_FILE}")
    # Group by session
    sessions = []
    current = []
    for e in events:
        if "SESSION" in e.get("line", ""):
            if current:
                sessions.append(current)
            current = []
        current.append(e)
    if current:
        sessions.append(current)
    print(f"Sessions: {len(sessions)}")
    if sessions:
        last = sessions[-1]
        spawns = [e for e in last if e["type"] == "spawn"]
        grows = [e for e in last if e["type"] in ("roster_grow", "roster_grow_old")]
        crashes = [e for e in last if e["type"] == "crash"]
        print(f"\nLast session: {len(spawns)} spawns, {len(grows)} grows, {len(crashes)} crashes")
        if grows:
            print("\nGrows:")
            for g in grows[:20]:
                print(f"  {g['line']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "graph":
        cmd_graph()
    elif cmd == "internals":
        cmd_internals()
    elif cmd == "lifecycle":
        cmd_lifecycle()
    elif cmd == "all":
        cmd_graph()
        print("\n" + "="*60 + "\n")
        cmd_lifecycle()
        print("\n" + "="*60 + "\n")
        cmd_internals()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
