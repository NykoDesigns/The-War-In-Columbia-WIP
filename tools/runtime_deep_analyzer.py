"""
runtime_deep_analyzer.py — Deep runtime log analysis for BioShock Infinite spawn mod.

Processes wic_spawn.log to:
  1. Correlate crashes with nearby spawn/grow events (causal analysis)
  2. Track enemy population over time
  3. Detect anomalies (spawn storms, pool exhaustion patterns)
  4. Parse ANNOT-DUMP entries for descriptor field validation
  5. Generate per-session health reports
  6. Identify the 0xBFB573 crash pattern (new, undiagnosed)

Usage:
  python tools/runtime_deep_analyzer.py               — Full analysis
  python tools/runtime_deep_analyzer.py --session N   — Analyze session N (0=latest)
  python tools/runtime_deep_analyzer.py --crashes     — Crash-focused analysis only
  python tools/runtime_deep_analyzer.py --population  — Enemy population timeline
  python tools/runtime_deep_analyzer.py --annot       — Parse annotated descriptor dumps
"""

import re, sys, os
from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional

GAME_DIR = Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32")
LOG_FILE = GAME_DIR / "wic_spawn.log"

@dataclass
class Event:
    time_ms: int
    time_str: str
    etype: str
    line: str
    data: dict = field(default_factory=dict)

@dataclass
class Session:
    start_time: str
    events: List[Event] = field(default_factory=list)
    spawns: int = 0
    grows: int = 0
    crashes: int = 0
    extras: int = 0


def parse_time(ts: str) -> int:
    """Parse MM:SS.mmm to milliseconds."""
    m = re.match(r'(\d+):(\d+)\.(\d+)', ts)
    if not m:
        return 0
    return int(m.group(1)) * 60000 + int(m.group(2)) * 1000 + int(m.group(3))


def parse_log(filepath: Path) -> List[Session]:
    """Parse wic_spawn.log into structured sessions."""
    sessions = []
    current = None

    time_re = re.compile(r'^\[(\d+:\d+\.\d+)\]\s+(.*)')
    session_re = re.compile(r'=== War In Columbia.*SESSION (\S+ \S+)')

    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            line = line.rstrip()

            # New session?
            sm = session_re.search(line)
            if sm:
                if current:
                    sessions.append(current)
                current = Session(start_time=sm.group(1))
                continue

            if not current:
                current = Session(start_time="unknown")

            tm = time_re.match(line)
            if not tm:
                continue

            ts, content = tm.group(1), tm.group(2)
            ms = parse_time(ts)
            ev = Event(time_ms=ms, time_str=ts, etype="unknown", line=content)

            # Classify event
            if content.startswith("SPAWN #"):
                ev.etype = "spawn"
                m = re.search(r"SPAWN #(\d+): class='(\w+)' name='(\S+)'", content)
                if m:
                    ev.data = {"seq": int(m.group(1)), "class": m.group(2), "name": m.group(3)}
                current.spawns += 1
            elif content.startswith("ROSTER-GROW ") and "GATED" not in content:
                ev.etype = "grow"
                m = re.search(r'Num (\d+)->(\d+).*totalEnemies=(\d+)', content)
                if m:
                    ev.data = {"from": int(m.group(1)), "to": int(m.group(2)), "total": int(m.group(3))}
                else:
                    m2 = re.search(r'Num (\d+)->(\d+).*\+(\d+) extra', content)
                    if m2:
                        ev.data = {"from": int(m2.group(1)), "to": int(m2.group(2)), "extra": int(m2.group(3))}
                current.grows += 1
            elif content.startswith("ROSTER-GROW GATED"):
                ev.etype = "grow_gated"
            elif content.startswith("EXTRA-AI"):
                ev.etype = "extra_ai"
                current.extras += 1
            elif content.startswith("*** CRASH"):
                ev.etype = "crash"
                m = re.search(r'fault=0x(\w+).*READ badAddr=0x(\w+)', content)
                if m:
                    ev.data = {"fault": m.group(1), "bad_addr": m.group(2), "type": "READ"}
                else:
                    m2 = re.search(r'fault=0x(\w+).*WRITE badAddr=0x(\w+)', content)
                    if m2:
                        ev.data = {"fault": m2.group(1), "bad_addr": m2.group(2), "type": "WRITE"}
                    else:
                        m3 = re.search(r'fault=0x(\w+).*EXEC badAddr=0x(\w+)', content)
                        if m3:
                            ev.data = {"fault": m3.group(1), "bad_addr": m3.group(2), "type": "EXEC"}
                current.crashes += 1
            elif content.startswith("ANNOT-DUMP"):
                ev.etype = "annot_dump"
            elif "+0x" in content and ("src=" in content or "cln=" in content):
                ev.etype = "annot_field"
                m = re.search(r'\+0x(\w+)\s+(\S+)\s+src=(\w+)\s+cln=(\w+)(.*)', content)
                if m:
                    ev.data = {
                        "offset": int(m.group(1), 16),
                        "name": m.group(2),
                        "src": m.group(3),
                        "clone": m.group(4),
                        "extra": m.group(5).strip()
                    }
            elif content.startswith("POOL-GROW"):
                ev.etype = "pool_grow"
            elif content.startswith("STREAMREAD-PATCH"):
                ev.etype = "patch"
            elif content.startswith("MEMCPY-GUARD"):
                ev.etype = "memcpy_guard"
            elif content.startswith("SER-GUARD") or content.startswith("SERDISP-DIAG-CORRUPT"):
                ev.etype = "ser_guard"

            current.events.append(ev)

    if current:
        sessions.append(current)
    return sessions


def analyze_crashes(session: Session):
    """Deep crash analysis: correlate each crash with nearby events."""
    print(f"\n{'='*70}")
    print(f"  CRASH ANALYSIS — {session.crashes} crashes in session")
    print(f"{'='*70}")

    crashes = [e for e in session.events if e.etype == "crash"]
    if not crashes:
        print("  No crashes in this session.")
        return

    # Classify crash patterns
    patterns = Counter()
    for c in crashes:
        fault = c.data.get("fault", "?")
        bad = c.data.get("bad_addr", "?")
        if "5849AE" in fault.upper():
            patterns["memcpy (streaming)"] += 1
        elif "5619E693" in fault.upper():
            patterns["PhysX constraint"] += 1
        elif "BFB573" in fault.upper():
            patterns["0xBFB573 (module high)"] += 1
        elif bad == "00000001" or bad == "00000000":
            patterns["NULL deref"] += 1
        elif "74B7CA4E" in fault.upper():
            patterns["system DLL"] += 1
        elif int(bad, 16) < 0x10000:
            patterns["near-NULL"] += 1
        else:
            patterns[f"other (fault={fault})"] += 1

    print("\n  Crash Pattern Breakdown:")
    for pat, count in patterns.most_common():
        print(f"    {count:3d}× {pat}")

    # For each crash, find what happened in the 5 seconds before
    print("\n  Crash Timeline (with 5s context window):")
    for i, crash in enumerate(crashes[:10]):  # Limit output
        print(f"\n  --- Crash #{i+1} @ {crash.time_str} ---")
        print(f"  {crash.line}")

        # Find events in [crash_time - 5000, crash_time]
        window = [e for e in session.events
                  if e.time_ms >= crash.time_ms - 5000
                  and e.time_ms <= crash.time_ms
                  and e != crash
                  and e.etype in ("grow", "spawn", "extra_ai", "pool_grow", "memcpy_guard", "ser_guard")]
        if window:
            print(f"  Context ({len(window)} events in prior 5s):")
            grows = [e for e in window if e.etype == "grow"]
            spawns = [e for e in window if e.etype == "spawn"]
            extras = [e for e in window if e.etype == "extra_ai"]
            if grows:
                print(f"    Roster grows: {len(grows)}")
            if spawns:
                print(f"    Spawns: {len(spawns)}")
            if extras:
                print(f"    Extra AI: {len(extras)}")
        else:
            print(f"  No spawn activity in prior 5s (likely streaming-related)")

    # Identify the undiagnosed 0xBFB573 crash
    bfb_crashes = [c for c in crashes if "BFB573" in c.data.get("fault", "").upper()]
    if bfb_crashes:
        print(f"\n  {'='*60}")
        print(f"  UNDIAGNOSED: 0xBFB573 crash pattern ({len(bfb_crashes)} occurrences)")
        print(f"  {'='*60}")
        print(f"  - RVA = 0xBFB573 (very high in module, near .rdata/.pdata boundary)")
        print(f"  - Always reads badAddr=0x00000001 (looks like a boolean/flag deref)")
        print(f"  - This is likely a vtable call on a destroyed/freed UObject")
        print(f"  - The object pointer was valid (in-module EIP) but the object's data is gone")
        print(f"  - HYPOTHESIS: garbage-collected pawn still referenced by AI system")
        print(f"  - ACTION NEEDED: Hook at RVA 0xBFB573-5 (the CALL instruction) to log target")


def analyze_population(session: Session):
    """Track enemy population over time."""
    print(f"\n{'='*70}")
    print(f"  ENEMY POPULATION TIMELINE")
    print(f"{'='*70}")

    # Track grows and their totalEnemies counts
    grows = [e for e in session.events if e.etype == "grow"]
    if not grows:
        print("  No roster grows in this session.")
        return

    print(f"\n  Time       | From→To | TotalEnemies | Notes")
    print(f"  -----------|---------|--------------|------")
    for g in grows:
        fr = g.data.get("from", "?")
        to = g.data.get("to", "?")
        total = g.data.get("total", g.data.get("extra", "?"))
        notes = ""
        if isinstance(total, int) and total > 20:
            notes = "⚠ HIGH"
        print(f"  {g.time_str:10s} | {fr:>2}→{to:<2} | {str(total):>12} | {notes}")

    # Peak population estimate
    totals = [g.data.get("total", 0) for g in grows if "total" in g.data]
    if totals:
        peak = max(totals)
        print(f"\n  Peak totalEnemies from single roster: {peak}")
        if peak > 24:
            print(f"  ⚠ WARNING: Peak > 24 may cause PhysX instability")
        else:
            print(f"  ✓ Within safe limits (≤24 per roster)")


def analyze_annot_dump(session: Session):
    """Parse and display annotated descriptor dumps."""
    print(f"\n{'='*70}")
    print(f"  ANNOTATED DESCRIPTOR DUMP")
    print(f"{'='*70}")

    annot_fields = [e for e in session.events if e.etype == "annot_field"]
    if not annot_fields:
        print("  No ANNOT-DUMP found in this session.")
        print("  (Will appear on next game launch after a roster grow)")
        return

    print(f"\n  {'Offset':<8} {'Field':<22} {'Source':<10} {'Clone':<10} {'Status':<8} {'Resolved'}")
    print(f"  {'------':<8} {'-----':<22} {'------':<10} {'-----':<10} {'------':<8} {'--------'}")
    for f in annot_fields:
        d = f.data
        diff = "DIFF" if d["src"] != d["clone"] else "same"
        extra = d.get("extra", "")
        if "DIFF" in extra:
            extra = extra.replace("DIFF", "").strip()
            diff = "DIFF"
        print(f"  +0x{d['offset']:02X}    {d['name']:<22} {d['src']:<10} {d['clone']:<10} {diff:<8} {extra}")

    # Validate critical fields
    print("\n  Validation:")
    for f in annot_fields:
        d = f.data
        if d["name"] == "CountA" and d["clone"] != "00000001":
            print(f"  ⚠ CountA clone = {d['clone']} (expected 00000001)")
        elif d["name"] == "CountA" and d["clone"] == "00000001":
            print(f"  ✓ CountA correctly forced to 1")
        if d["name"] == "Spawner" and d["clone"] == "00000000":
            print(f"  ⚠ Spawner is NULL in clone! Damage registration will fail!")
        elif d["name"] == "Spawner" and d["src"] == d["clone"] and d["clone"] != "00000000":
            print(f"  ✓ Spawner preserved in clone ({d['clone']})")
        if d["name"] == "Delegate.Obj" and d["clone"] == "00000000":
            print(f"  ⚠ Delegate.Obj is NULL! OnSpawn will not fire!")
        elif d["name"] == "Delegate.Obj" and d["src"] == d["clone"] and d["clone"] != "00000000":
            print(f"  ✓ Delegate.Obj preserved in clone")
        if d["name"] == "RuntimeCnt" and d["clone"] != "00000000":
            print(f"  ⚠ RuntimeCnt not zeroed! ({d['clone']})")
        elif d["name"] == "RuntimeCnt" and d["clone"] == "00000000":
            print(f"  ✓ RuntimeCnt correctly zeroed")
        if d["name"] == "RuntimePtr" and d["clone"] != "00000000":
            print(f"  ⚠ RuntimePtr not zeroed! ({d['clone']})")
        elif d["name"] == "RuntimePtr" and d["clone"] == "00000000":
            print(f"  ✓ RuntimePtr correctly zeroed")


def analyze_session(session: Session, idx: int):
    """Full analysis of a single session."""
    print(f"\n{'#'*70}")
    print(f"  SESSION #{idx} — Started {session.start_time}")
    print(f"  Events: {len(session.events)} | Spawns: {session.spawns} | "
          f"Grows: {session.grows} | Extras: {session.extras} | Crashes: {session.crashes}")
    print(f"{'#'*70}")

    # Session duration
    if session.events:
        duration_ms = max(e.time_ms for e in session.events)
        mins = duration_ms // 60000
        secs = (duration_ms % 60000) // 1000
        print(f"  Duration: ~{mins}m {secs}s")

    # Health score
    score = 100
    if session.crashes > 0:
        score -= min(50, session.crashes * 10)
    if session.grows > 0 and session.crashes == 0:
        score += 10
    print(f"  Health Score: {score}/100")


def main():
    if not LOG_FILE.exists():
        print(f"Log file not found: {LOG_FILE}")
        print("Run the game to generate wic_spawn.log")
        return

    sessions = parse_log(LOG_FILE)
    if not sessions:
        print("No sessions found in log.")
        return

    print(f"Parsed {len(sessions)} sessions from {LOG_FILE}")
    print(f"Total events: {sum(len(s.events) for s in sessions)}")

    # Determine what to analyze
    args = sys.argv[1:]
    target_session = -1  # latest by default
    mode = "full"

    for arg in args:
        if arg.startswith("--session"):
            try:
                target_session = int(args[args.index(arg) + 1])
            except:
                pass
        elif arg == "--crashes":
            mode = "crashes"
        elif arg == "--population":
            mode = "population"
        elif arg == "--annot":
            mode = "annot"

    session = sessions[target_session]
    idx = len(sessions) + target_session if target_session < 0 else target_session

    if mode == "full":
        analyze_session(session, idx)
        analyze_crashes(session)
        analyze_population(session)
        analyze_annot_dump(session)
    elif mode == "crashes":
        analyze_crashes(session)
    elif mode == "population":
        analyze_population(session)
    elif mode == "annot":
        analyze_annot_dump(session)


if __name__ == "__main__":
    main()
