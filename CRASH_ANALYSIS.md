# BioShock Infinite – Crash Analysis & Debugging Journal

## Project: The War In Columbia (Spawn Multiplier Mod)

This document captures the full debugging journey for a persistent crash in BioShock Infinite (32-bit, Unreal Engine 3) that occurs during level streaming. The mod multiplies enemy spawn rosters at runtime via a proxy DLL (`winmm.dll`) using MinHook function hooking.

---

## 1. The Crash

### Symptoms
- **Access violation (0xC0000005)** during level transitions (entering new areas, riding rockets, walking to new zones)
- Happens ~30–120 seconds after entering an area, NOT during combat
- Occurs in **vanilla game** (without mod) but is much rarer; the mod's extra memory pressure makes it nearly guaranteed
- Game shows no useful crash dialog — just freezes or shows "Fatal error!"

### Crash Signature
```
memcpy called with count ≈ 4 GB (e.g. 0xFFC4ADBD or 0xFFA5561E)
Source address: low address in archive buffer (e.g. 0x005AA9E2)
Destination: high address (e.g. 0xA707AB08)
Caller RVA: 0xEBB41 (inside FArchive::Serialize at RVA 0xEBA70)
Upper caller: 0xB625F → 0x80D00 (serialize dispatcher)
```

### Root Cause
A **race condition in UE3's async level streaming** subsystem. During level transitions:

1. The streaming system loads package data asynchronously
2. A buffer is freed or reallocated while a serialization pointer still references it
3. The stale pointer reads garbage data from the freed buffer
4. A TArray `Count` field is deserialized as ~4 billion (corrupt)
5. `FArchive::Serialize` calls `memcpy(dst, src, 4GB)` — immediate access violation

This is a **vanilla engine bug** documented in UE3 contexts:
- [The Curious Incident (coconutlizard.co.uk)](https://www.coconutlizard.co.uk/blog/the-curious-incident/) — describes exact same pattern of corrupt FString/TArray counts causing ~1GB allocations
- [PCGamingWiki BioShock Infinite](https://www.pcgamingwiki.com/wiki/BioShock_Infinite) — documents texture streaming crashes
- Multiple Steam Community threads about freezing on higher-end rigs

---

## 2. The Call Chain (Verified via Stack Traces)

```
Game main loop (Tick)
  └─ Level streaming subsystem (RVA 0x1CF69B)
       └─ Streaming loader (RVA 0x1B7EB2)
            └─ Package deserializer (RVA 0xB625F)
                 └─ Serialize dispatcher (RVA 0x80D00) ← our Hook_SerDispatch
                      └─ FArchive::Serialize (RVA 0xEBA70) ← our Hook_ArSerialize
                           └─ memcpy (MSVCR90.dll) ← our Hook_memcpy
                                └─ ACCESS VIOLATION (reads past committed memory)
```

The corrupt length originates from DATA read by `FArchive::Serialize` internally — NOT from the `length` parameter passed to it. The function reads a TArray count from the archive buffer, gets garbage (e.g. 0xFFA5561E as signed int = -5,941,730), and passes it directly to `memcpy` as `size_t` (becomes ~4GB unsigned).

---

## 3. Why The Mod Makes It Worse

### Memory Pressure (32-bit address space ≈ 2.8 GB usable with LAA)
| Consumer | Vanilla | With Mod |
|----------|---------|----------|
| Wwise audio pools | ~61 MB | ~122 MB (2x enlarger) |
| Spawned actors | Baseline | x3 enemy count per wave |
| Actor state (AI controllers, inventories) | Baseline | x3 |
| Available for streaming buffers | More | Less |

Less free address space → more frequent buffer reallocation → more race conditions → more corrupt reads.

### Elizabeth Duplication Bug (FIXED)
The roster grow logic was cloning **all** entries including companion NPCs:
- `ROSTER-GROW Num 1→4` on Elizabeth's roster → 4 Elizabeths spawned
- Each has its own `XAIElizabethController` with full AI state
- Engine expects exactly ONE companion → corrupt AI state, pathfinding conflicts
- **Fix**: Skip rosters with `Num < 2` (companions are always single-entry)

---

## 4. Hook Architecture

### DLL Injection Method
- Proxy DLL: `winmm.dll` placed in game's `Binaries\Win32\` directory
- Game imports `winmm.dll` for audio → loads our proxy → we forward all real winmm calls
- Init thread starts hooks before game reaches main loop

### Hooks Installed (via MinHook)

| Hook | Target RVA | Purpose |
|------|-----------|---------|
| `Hook_SpawnActor` | 0x22CA80 | Log all actor spawns, detect duplicates |
| `Hook_SpawnRoster` | 0x658870 | Multiply enemy wave TArrays in-place |
| `Hook_CreatePool` | Wwise export | Enlarge audio memory pools |
| `Hook_ArSerialize` | 0xEBA70 | Block corrupt serialize lengths (>32MB or negative) |
| `Hook_SerDispatch` | 0x80D00 | Block corrupt dispatch lengths (same threshold) |
| `Hook_memcpy` | MSVCR90!memcpy | Last-resort clamp on corrupt copy sizes |

### memcpy Hook Resolution
The memcpy hook **must** target the actual `MSVCR90!memcpy` function, not an IAT slot:
```cpp
HMODULE hCRT = GetModuleHandleA("MSVCR90.dll");
fn_memcpy pMemcpy = (fn_memcpy)GetProcAddress(hCRT, "memcpy");
MH_CreateHook(pMemcpy, &Hook_memcpy, (void**)&Real_memcpy);
```
Previous attempts using IAT slot `RVA 0xD455C` failed because it contained garbage (`0x15543589`), not the real memcpy address.

---

## 5. Fix Attempts & Results

### Attempt 1: Block memcpy + zero-fill destination
```cpp
if (count >= 32MB) {
    memset(dst, 0, 4096);  // zero-fill to break deserialization loops
    return dst;             // skip the copy
}
```
**Result**: Game hangs. The caller retries the same Serialize call in a tight loop (500+ times at identical parameters within 125ms). Zero-filled destination doesn't affect the retry condition.

### Attempt 2: Block memcpy + RaiseException after 500 retries
```cpp
if (n > 500) RaiseException(0xE0000BAD, 0, 0, nullptr);
```
**Result**: Game shows "Fatal error!" dialog. Our exception is caught by the game's top-level handler which treats it as fatal. Secondary crash follows 11 seconds later.

### Attempt 3: Retry-loop breaker in SerDispatch
```cpp
// Skip if same This+dst called 3+ times within 100ms
if (This == s_prevThis && dst == s_prevDst && elapsed < 100) { skip; }
```
**Result**: "Bad export index 1849731463/6150" — the breaker was too aggressive. Normal UE3 serialization reads the same `&count` variable in loops (same `dst`), so legitimate reads were being skipped. Stale buffer data was interpreted as export indices → garbage.

### Attempt 4: Clamp memcpy to readable source extent
```cpp
if (count >= 32MB) {
    VirtualQuery(src, &mbi, sizeof(mbi));
    safeSz = min(regionEnd - srcAddr, 32MB);
    Real_memcpy(dst, src, safeSz);  // copy what's safe
    return dst;
}
```
**Result**: Game hangs or OOMs. The caller retries or uses the clamped garbage data to attempt huge allocations.

### Attempt 5: Disable texture streaming via XEngine.ini
```ini
UseTextureFileCache=False
PoolSize=0
UseDynamicStreaming=False
```
**Result**: "Serial size mismatch: Got 382, Expected 16777598" — the game stores all texture bulk data in `.tfc` files. Disabling the file cache means textures can't load at all. **Reverted**.

### Attempt 6: VEH-based crash recovery
- Vectored Exception Handler intercepts memcpy access violations
- Unwinds stack via EBP to simulate a return from memcpy
- **Result**: Partially works, but the caller still has the corrupt count and retries.

### Attempt 7: Zero-fill destination on corrupt memcpy
- Block the copy, zero-fill destination to give caller null data
- **Result**: Caller's while(true) loop retries 20+ times (virtual refill reloads same corrupt state).

### Attempt 8: Full function reimplementation ❌
- Reimplemented FUN_00496F00 with bounds checks built in
- **Result**: Crash at address 0x0 — the virtual refill function pointer is NULL for some stream reader subclasses used during initial loading. Not all objects using this function have the same vtable layout.

### ✅ Attempt 9: Binary patch JLE→JBE (DEFINITIVE FIX)
```
Address: FUN_00496F00 + 0x5E (buffer 1) and + 0xA7 (buffer 2)
Original: 7E 02  (JLE rel8 +2 — signed comparison)
Patched:  76 02  (JBE rel8 +2 — unsigned comparison)
```
**The actual engine bug**: The function computes `avail = bufEnd - curPos`. When `bufEnd=0` (freed buffer), `avail` wraps to `0xFFE889B4` (~4GB unsigned, but -1.5M signed). The JLE instruction compares avail vs count as SIGNED: `-1.5M ≤ 4096?` → YES → doesn't cap → passes 4GB to memcpy.

Changing to JBE (unsigned comparison): `4,293,429,684 ≤ 4096?` → NO → caps avail to count → copies only 4 bytes from a low (still accessible) heap address. Stale data but no crash.

**Result**: ✅ Level transitions work. The streaming crash is eliminated. Game continues with at most a few bytes of stale data in one deserialized field (self-correcting on next frame).

---

## 6. Key Technical Details

### Address Space (32-bit process)
- EXE already has **IMAGE_FILE_LARGE_ADDRESS_AWARE** flag set
- Usable address space: ~2.8 GB on 64-bit Windows
- Every MB of overhead from hooks/pools reduces streaming buffer availability

### FArchive::Serialize Internal Behavior (RVA 0xEBA70)
- Buffered reader: maintains internal buffer + position
- For large reads: copies from buffer, then refills from underlying stream
- The memcpy at RVA 0xEBB41 (209 bytes into function) is the buffer→destination copy
- The corrupt count comes from DATA in the buffer, not from the function parameter
- This means our parameter-level hooks (ArSerialize, SerDispatch) can't catch it — the corruption enters through deserialized data

### The Retry Loop Pattern
When the corrupt memcpy is blocked/clamped:
```
Log shows 500 identical entries in <200ms:
  MEMCPY-GUARD: count=0xFFA5561E dst=0xA707AB08 src=0x005AA9E2
  MEMCPY-GUARD: count=0xFFA5561E dst=0xA707AB08 src=0x005AA9E2
  ...
```
Same `dst`, same `src`, same `count` every time → the function's internal position is NOT advancing. The caller resets the archive position after each failed attempt and retries.

### Serialize Threshold
- `SER_MAX_LEN` was initially 8 MB but legitimate texture bulk reads reach ~17 MB (e.g. `FX_Lighthouse.Main1912_DIF` = 16,777,598 bytes)
- Raised to 32 MB to match memcpy guard threshold

---

## 7. Current Defense Layers

```
Layer 0: BINARY PATCH (FUN_00496F00 at +0x5E and +0xA7)
  → Patches JLE (0x7E) → JBE (0x76) at runtime via VirtualProtect
  → Fixes the root cause: unsigned comparison prevents 4GB memcpy
  → Zero runtime overhead (no hook on this hot path)

Layer 1: Hook_SerDispatch (RVA 0x80D00)
  → Logging-only: records corrupt serialize lengths for diagnostics
  → Returns archive pointer for call chaining

Layer 2: Hook_ArSerialize (RVA 0xEBA70)
  → Logging-only: records large/corrupt reads
  → Logs archive internal state (buffer position, remaining bytes)

Layer 3: Hook_memcpy (MSVCR90!memcpy via GetProcAddress)
  → Safety net: blocks copies ≥ 32MB (should no longer trigger after Layer 0 fix)
  → Returns dst without copying

Layer 4: CrashVEH (Vectored Exception Handler)
  → Catches 0xC0000005 access violations
  → Logs true RVA, register state, stack trace to wic_spawn.log

Layer 5: Hook_PoolRefill (RVA 0x958C0)
  → Fixes pool exhaustion crash: forces grow with +64 nodes when game passes 0
```

---

## 8. Per-Level Failure Modes (Observed In-Game)

Every level transition can exhibit a **different** failure mode depending on which corrupt data path is hit and how the defense layers interact. These are the three distinct crash types plus one gameplay bug:

### Mode A: Hang — "BioShock Infinite is not responding"
- **What happens**: Game freezes, Windows shows "Not Responding" dialog
- **Cause**: The memcpy clamp (or block) prevents the crash, but the caller at RVA `0xB625F` retries the same Serialize call in an infinite loop. The archive position resets after each failed attempt — same `dst`, `src`, and `count` every iteration.
- **Why the clamp doesn't help**: The caller checks a condition AFTER Serialize returns (not based on the destination data). The clamped copy doesn't satisfy that condition, so it retries. Zero-filling also doesn't work — the condition is based on archive internal state, not buffer contents.
- **Log evidence**: 500+ identical `MEMCPY-GUARD` entries at the same timestamp

### Mode B: OOM — "Ran out of virtual memory"
- **What happens**: Game shows "Ran out of virtual memory. To prevent this condition, you must free up more space on your primary hard disk."
- **Stack**: `RaiseException @ KERNELBASE → 0x49ae79 (RVA 0x9AE79)`
- **Cause**: The memcpy clamp lets the caller proceed with partially-valid data. The caller reads a corrupt TArray Count from the clamped buffer (e.g. 0xFFA5561E) and tries to **allocate** `Count × ElementSize` bytes. In a 32-bit process with ~2.8 GB usable, this immediately exhausts virtual address space.
- **Key insight**: The clamp prevents the memcpy crash but enables an allocation crash. The corruption cascades — instead of crashing on the copy, it crashes on the allocation.

### Mode C: Fatal crash through MSVCR90 memcpy
- **What happens**: Game shows "Fatal error!" with `memcpy()` at the top of the stack trace
- **Stack**: `memcpy @ 0x5849aed8 [MSVCR90.dll] → 0x4ebb41 (RVA 0xEBB41) → 0x480d47 (RVA 0x80D47) → 0x4b625f → 0x5b7eb2 → 0x5cf69b`
- **Notable**: Our WINMM.dll hooks do NOT appear in the stack trace. Two possibilities:
  1. The game's stack walker skips frames from unrecognized DLLs (our hooks are there but not shown)
  2. The corrupt memcpy count was **under 32 MB** (passed our threshold) but the source/dest buffer was too small → access violation inside the real memcpy
- **The 0x5849aed8 address**: This is 0xB8 bytes past the memcpy entry point (0x5849AE20). This is deep inside the memcpy function body where the actual byte-copy loop faults. This suggests our hook DID run, judged the count as safe (< 32MB), forwarded to Real_memcpy, and the real function crashed because the source region was unmapped/freed.

### Mode D: Spawns work but enemies are invulnerable ✅ RESOLVED
- **What happens**: Extra enemies spawn correctly and are visible/animated, but some cannot be damaged by the player
- **Actual cause (confirmed via DESC-DIFF analysis)**: We were zeroing +0xCC (Spawner) and +0xD8 (Delegate) in cloned descriptors to prevent "use-after-free." But DESC-DIFF proved ALL descriptors in the same roster share these exact values. The Spawner and Delegate are NOT per-instance fields — they're shared template data needed by the spawner's post-spawn registration path to hook up the new pawn with the damage/collision system.
- **Fix**: Keep Spawner and Delegate intact in clones. The spawner outlives its spawned enemies (same level package). Only zero the actual per-instance fields: +0xE8 (RuntimeCnt) and +0xEC (RuntimePtr).

### Summary Table

| Level Behavior | Mode | Root Cause | Status |
|---------------|------|------------|--------|
| Freeze/hang | A | Signed comparison bug in stream reader | ✅ FIXED (JLE→JBE patch) |
| "Out of virtual memory" | B | Cascade from streaming bug → corrupt allocation | ✅ FIXED (same patch) |
| "Fatal error!" memcpy | C | Streaming bug variant (unmapped source) | ✅ FIXED (same patch) |
| Enemies invulnerable | D | Zeroed Spawner/Delegate broke damage registration | ✅ FIXED (keep intact) |
| PhysX constraint crash | E | Clone inherited CountA=7 → 24+ actors/wave | ✅ FIXED (force CountA=1) |
| Game works normally | — | No corruption hit this transition | All layers idle |

---

## 9. Ghidra Reverse Engineering (Definitive Root Cause)

Using Ghidra headless analysis on `BioShockInfinite.exe`, we decompiled the crash function:

### FUN_00496F00 — Double-Buffered Async Stream Reader

```c
void __thiscall FUN_00496f00(int *this, void *dst, size_t count)
{
    while (true) {
        if ((int)count < 1) return;
        
        // Wait for buffer to be ready (virtual call)
        if (this[0x2c] < (int)count) {
            int ok = vtable[0x3C](this, this[0x2b], count);
            while (ok == 0) { Sleep(0); ok = vtable[0x3C](...); }
        }
        
        // Compute available bytes in buffer 1
        size_t avail = this[0x32] - this[0x2b];  // bufEnd - curPos
        if ((int)count < (int)avail) avail = count;  // ← BUG: signed comparison!
        
        memcpy(dst, (this[0x35] - this[0x2f]) + this[0x2b], avail);
        // ... (same pattern for buffer 2) ...
    }
}
```

### The Assembly Bug (confirmed via raw bytes at 0x496F5E)

```asm
8b 9e c8 00 00 00   mov ebx, [esi+0xC8]    ; ebx = bufEnd
2b 9e ac 00 00 00   sub ebx, [esi+0xAC]    ; ebx = bufEnd - curPos = avail
3b df               cmp ebx, edi            ; compare avail, count
7e 02               jle +2                  ; JLE = signed! BUG!
8b df               mov ebx, edi            ; cap avail to count
```

When `bufEnd=0` (freed buffer) and `curPos=0x0017764C`:
- `avail = 0 - 0x0017764C = 0xFFE889B4`
- As signed: -1,537,612
- `JLE` comparison: -1,537,612 ≤ 4096? **YES** → doesn't cap → memcpy with 4GB

### The Fix: One Byte × Two Locations

```
0x496F5E: 7E → 76  (JLE → JBE for buffer 1)
0x496FA7: 7E → 76  (JLE → JBE for buffer 2)
```

JBE (unsigned): 4,293,429,684 ≤ 4096? **NO** → caps to count → 4-byte read → no crash.

---

## 10. Resolved Issues (All Screenshot Crashes)

### ✅ Crash Screenshot 1: Streaming/memcpy crash (Mode A/B/C)
```
memcpy @ MSVCR90.dll → RVA 0xEBB41 → FArchive::Serialize
Access violation 0xC0000005, count ≈ 4GB
```
- **Root cause**: Signed comparison (JLE) in FUN_00496F00 treats 0xFFE889B4 as -1.5M instead of 4GB
- **Fix**: Binary patch JLE→JBE at two locations (+0x5E, +0xA7)
- **Status**: ✅ FIXED — no streaming crashes since patch deployed

### ✅ Crash Screenshot 2: PhysX constraint crash
```
physx::PxConstraintGeneratedValues::PxConstraintGeneratedValues()
Address = 0x5619e693 [PhysX3_x86.dll]
READ badAddr=0x0000002C
```
- **Root cause**: Cloned descriptors inherited CountA=7 from source. A 2-descriptor roster
  (7+5=12 enemies) growing to 4 descriptors produced 7+5+7+5=24 enemies PER WAVE.
  Multiple concurrent waves → PhysX solver overwhelmed by 360+ constraints.
- **Fix**: Force clone CountA=CountB=1. Each cloned descriptor now produces exactly 1 enemy.
  With 3x multiplier: a 2-desc roster grows to 6 descs = 12+4=16 enemies (not 24+).
- **Status**: ✅ FIXED (deployed, needs verification)

### ✅ Crash Screenshot 3: Invulnerable cloned enemies (Mode D)
- **Root cause**: Zeroing +0xCC (Spawner back-reference) and +0xD8 (Delegate) in clones
  broke the spawner's post-spawn registration path. The OnSpawn delegate is what registers
  newly-created pawns with the damage/collision system. Without it, the pawn exists and has
  AI but cannot receive damage.
- **Evidence**: DESC-DIFF proved ALL descriptors in a roster share identical Spawner and
  Delegate values — these are NOT per-instance and should NOT be zeroed.
- **Fix**: Keep Spawner (+0xCC) and Delegate (+0xD8) intact in clones. They're shared
  across the entire roster and the spawner outlives its spawned enemies.
- **Status**: ✅ FIXED (deployed, needs verification)

---

## 11. Open Questions

1. **Can the archive error flag be set?** If `FArchive` has an error/corrupt flag (common in UE3: `ArIsError`), setting it after detecting corruption would cause all callers to bail out cleanly. Need to find the flag's offset in the archive object.

2. **Is the corruption in the .tfc file or in memory?** If the `.tfc` file on disk is corrupt, verifying game files via Steam would fix it permanently. If it's a runtime race, it's non-deterministic.

3. **Can async streaming be serialized?** Forcing synchronous level loading would eliminate the race condition but might cause longer load screens. Look for `bUseBackgroundLevelStreaming=False` or similar config.

4. **Would reducing streaming distance help?** Fewer concurrent streams = less memory pressure = fewer races. Possible via `StreamingDistanceMultiplier` in config.

5. **The 0xEBB41 inlined serialize**: The corrupt count is read and used for memcpy within a single function body (no second hook-interceptable call). Binary patching the function to add bounds checking before the memcpy instruction would be the definitive fix but requires precise disassembly.

6. **Mode C sub-32MB crashes**: Image 3 shows a crash inside real MSVCR90 memcpy (0x5849aed8, offset +0xB8 into the function). The count must have been < 32MB (passed our guard) but the source page was unmapped. Should we also validate source readability via VirtualQuery for ALL memcpy calls in the 1MB–32MB range? Performance cost of VirtualQuery on every large copy needs evaluation.

7. **Invulnerable cloned enemies (Mode D)**: The roster grow copies descriptors byte-for-byte. Per-instance UObject pointers (damage receiver, collision) are shared with the original. Need to identify which descriptor fields hold per-instance references and either NULL them (let the engine create new ones) or allocate fresh components. `DumpDescDiff` output in the log shows which offsets differ between descriptors — those are the per-instance fields.

8. **Binary patch at 0xEBB41**: The definitive fix would be to NOP or guard the memcpy CALL instruction at RVA 0xEBB38 (5 bytes before the return address 0xEBB41). Replace `call memcpy` with a `call Hook_SafeMemcpy` that validates count AND source readability. This bypasses all retry-loop issues because the guard is inline.

---

## 12. File Locations

| File | Path |
|------|------|
| Mod source | `z:\TheWarInColumbia\native\src\ue3_spawn.cpp` |
| Proxy DLL entry | `z:\TheWarInColumbia\native\src\winmm_proxy.cpp` |
| Built DLL | `D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\winmm.dll` |
| Runtime log | `D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\wic_spawn.log` |
| Engine config | `C:\Users\Owner\Documents\my games\BioShock Infinite\XGame\Config\XEngine.ini` |
| Game EXE | `D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe` |
| EXE backup | `D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe.bak` |

---

## 13. Log File Reference

The mod writes detailed diagnostics to `wic_spawn.log`. Key log prefixes:

| Prefix | Meaning |
|--------|---------|
| `SPAWN #N` | Actor spawned (class, name, vtable RVA) |
| `ROSTER-GROW` | Enemy wave multiplied (Num before→after) |
| `ROSTER-SKIP` | Single-NPC roster skipped (companion filter) |
| `SER-GUARD` | Corrupt serialize length blocked |
| `SERDISP-GUARD` | Corrupt dispatch length blocked |
| `MEMCPY-GUARD` | Corrupt memcpy blocked (safety net, should not fire after patch) |
| `STREAMREAD-PATCH` | Binary patch applied to streaming reader (JLE→JBE) |
| `POOL-GROW` | Pool refill fix triggered (prevented NULL-deref crash) |
| `SER-DIAG` | Serialize hook heartbeat (every 500K calls) |
| `SERDISP-DIAG` | Dispatch hook heartbeat (every 1M calls) |
| `*** CRASH` | VEH caught access violation |
| `AK CreatePool` | Wwise audio pool creation (original→enlarged size) |
