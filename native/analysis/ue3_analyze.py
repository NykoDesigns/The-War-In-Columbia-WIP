"""
UE3 static analyzer for BioShock Infinite (BioShockInfinite.exe).

Goal: locate the runtime addresses we need for the spawn-multiplier hook:
  - GNames   (global FName table)
  - GObjects (global UObject array)
  - UObject::ProcessEvent  (UnrealScript dispatch)
  - UWorld::SpawnActor / AActor::execSpawn  (spawn chokepoint)

Strategy: find anchor strings (ASCII + UTF-16), resolve their virtual
addresses, then find code/data cross-references and disassemble around them.

This file is a library of helpers; run with a subcommand.
"""
import sys
import re
import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe"


class Image:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = self.pe.__data__  # full file bytes (mmap)
        self.sections = []
        for s in self.pe.sections:
            name = s.Name.rstrip(b"\x00").decode("latin1", "replace")
            self.sections.append({
                "name": name,
                "va": self.base + s.VirtualAddress,
                "vsize": s.Misc_VirtualSize,
                "raw": s.PointerToRawData,
                "rsize": s.SizeOfRawData,
            })
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.md.detail = True

    def va_to_off(self, va):
        for s in self.sections:
            if s["va"] <= va < s["va"] + max(s["vsize"], s["rsize"]):
                delta = va - s["va"]
                if delta < s["rsize"]:
                    return s["raw"] + delta
        return None

    def off_to_va(self, off):
        for s in self.sections:
            if s["raw"] <= off < s["raw"] + s["rsize"]:
                return s["va"] + (off - s["raw"])
        return None

    def read(self, va, n):
        off = self.va_to_off(va)
        if off is None:
            return None
        return self.data[off:off + n]

    def section_bytes(self, name):
        for s in self.sections:
            if s["name"] == name:
                return s, self.data[s["raw"]:s["raw"] + s["rsize"]]
        return None, None


def find_ascii(data, needle):
    """Yield file offsets where a NUL-terminated ASCII needle occurs."""
    nb = needle.encode("ascii")
    start = 0
    while True:
        i = data.find(nb, start)
        if i < 0:
            break
        yield i
        start = i + 1


def find_utf16(data, needle):
    nb = needle.encode("utf-16-le")
    start = 0
    while True:
        i = data.find(nb, start)
        if i < 0:
            break
        yield i
        start = i + 1


def find_dword_refs(data, value):
    """Yield file offsets where the little-endian dword == value (pointer xref)."""
    vb = struct.pack("<I", value)
    start = 0
    while True:
        i = data.find(vb, start)
        if i < 0:
            break
        yield i
        start = i + 1


def cmd_info(img):
    print(f"ImageBase = 0x{img.base:08X}")
    print("Sections:")
    for s in img.sections:
        print(f"  {s['name']:8} VA=0x{s['va']:08X} vsize=0x{s['vsize']:X} "
              f"raw=0x{s['raw']:X} rsize=0x{s['rsize']:X}")


def cmd_strrefs(img, needle):
    """Find an ASCII string, then data xrefs (pointers) to it, then code xrefs to those."""
    print(f"=== ASCII string '{needle}' ===")
    hits = list(find_ascii(img.data, needle))
    print(f"occurrences: {len(hits)}")
    for off in hits[:10]:
        va = img.off_to_va(off)
        ctx = img.data[off:off+len(needle)+1]
        print(f"  off=0x{off:X} va={'0x%08X'%va if va else '?'} bytes={ctx!r}")
        if va:
            refs = list(find_dword_refs(img.data, va))
            print(f"    pointer xrefs: {len(refs)}")
            for r in refs[:8]:
                rva = img.off_to_va(r)
                # dump 24 bytes around the pointer (likely a struct entry)
                around = img.data[r-4:r+20]
                print(f"      ref off=0x{r:X} va={'0x%08X'%rva if rva else '?'} "
                      f"data={around.hex()}")


def cmd_nativetable(img, filt=None):
    """Scan .data for the native-function table: 8-byte {funcptr, nameptr} pairs
    where funcptr is in .text and nameptr points to an ASCII string."""
    text = next(s for s in img.sections if s["name"] == ".text")
    text_lo, text_hi = text["va"], text["va"] + text["vsize"]
    sec, dbytes = img.section_bytes(".data")
    if dbytes is None:
        print("no .data"); return
    base_va = sec["va"]
    entries = []
    n = len(dbytes) - 8
    i = 0
    # Layout is {char* name; void* func} (name FIRST), confirmed via
    # AActor::execSpawn == 0x642D90.
    while i <= n:
        name = struct.unpack_from("<I", dbytes, i)[0]
        func = struct.unpack_from("<I", dbytes, i + 4)[0]
        if text_lo <= func < text_hi:
            soff = img.va_to_off(name)
            if soff is not None:
                raw = img.data[soff:soff + 80]
                end = raw.find(b"\x00")
                if 3 <= end < 80 and all(32 <= b < 127 for b in raw[:end]):
                    s = raw[:end].decode("ascii")
                    entries.append((base_va + i, func, s))
        i += 4
    print(f"native table candidate entries: {len(entries)}")
    for va, func, s in entries:
        if filt is None or filt.lower() in s.lower():
            print(f"  entry@0x{va:08X}  func=0x{func:08X}  rva=0x{func-img.base:06X}  {s}")


def _parse_va(arg, img):
    v = int(arg, 16)
    # accept RVA or VA
    if v < img.base:
        v += img.base
    return v


def cmd_disasm(img, va_arg, count=60):
    va = _parse_va(va_arg, img)
    code = img.read(va, count * 8)
    if not code:
        print("cannot read"); return
    n = 0
    for ins in img.md.disasm(code, va):
        print(f"  0x{ins.address:08X} (rva 0x{ins.address-img.base:06X}): "
              f"{ins.mnemonic} {ins.op_str}")
        n += 1
        if n >= count:
            break


def cmd_calls(img, va_arg, count=200):
    """List direct call targets (call rel32) within the first `count` instructions."""
    va = _parse_va(va_arg, img)
    code = img.read(va, count * 8)
    if not code:
        print("cannot read"); return
    n = 0
    seen = []
    for ins in img.md.disasm(code, va):
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            tgt = int(ins.op_str, 16)
            seen.append((ins.address, tgt))
        if ins.mnemonic in ("ret", "retn"):
            break
        n += 1
        if n >= count:
            break
    print(f"call targets from 0x{va:08X}:")
    for addr, tgt in seen:
        print(f"  at 0x{addr:08X} -> 0x{tgt:08X} (rva 0x{tgt-img.base:06X})")


def cmd_funcstart(img, va_arg, window=0x800):
    """Scan backward from va for the function start: the byte after the last
    run of >=2 int3 (0xCC) padding bytes that precedes va. Then disassemble a
    few instructions from there to confirm a prologue."""
    va = _parse_va(va_arg, img)
    lo = va - window
    code = img.read(lo, window)
    if not code:
        print("cannot read"); return
    # Find the last occurrence of a 0xCC run in [lo, va).
    best = None
    i = 0
    while i < len(code) - 1:
        if code[i] == 0xCC and code[i + 1] == 0xCC:
            j = i
            while j < len(code) and code[j] == 0xCC:
                j += 1
            # function would start at lo+j
            best = lo + j
            i = j
        else:
            i += 1
    if best is None:
        print(f"no int3 padding found in [0x{lo:08X},0x{va:08X})"); return
    print(f"candidate function start: 0x{best:08X} (rva 0x{best-img.base:06X})")
    code2 = img.read(best, 32 * 8)
    n = 0
    for ins in img.md.disasm(code2, best):
        print(f"  0x{ins.address:08X} (rva 0x{ins.address-img.base:06X}): "
              f"{ins.mnemonic} {ins.op_str}")
        n += 1
        if n >= 32 or ins.address >= va:
            break


def cmd_rtti(img, va_arg):
    """Given a vtable VA (or RVA), resolve MSVC RTTI class name via [vtbl-4]."""
    vtbl = _parse_va(va_arg, img)
    col_ptr = img.read(vtbl - 4, 4)
    if not col_ptr:
        print(f"vtbl 0x{vtbl:08X}: cannot read [vtbl-4]"); return
    col = struct.unpack("<I", col_ptr)[0]
    # CompleteObjectLocator: +0x0C = pTypeDescriptor (VA in 32-bit)
    td_ptr = img.read(col + 0x0C, 4)
    if not td_ptr:
        print(f"vtbl 0x{vtbl:08X}: COL=0x{col:08X} (no TypeDescriptor)"); return
    td = struct.unpack("<I", td_ptr)[0]
    # TypeDescriptor: +0x00 vftable, +0x04 spare, +0x08 mangled name (".?AV...@@")
    raw = img.read(td + 0x08, 128)
    if not raw:
        print(f"vtbl 0x{vtbl:08X}: COL=0x{col:08X} TD=0x{td:08X} (no name)"); return
    end = raw.find(b"\x00")
    name = raw[:end].decode("latin1", "replace") if end > 0 else "<none>"
    print(f"vtbl 0x{vtbl:08X} (rva 0x{vtbl-img.base:X}): COL=0x{col:08X} TD=0x{td:08X}  {name}")


def main():
    if len(sys.argv) < 2:
        print("usage: ue3_analyze.py <info|strrefs|nativetable|disasm|calls|rtti> [args]")
        return
    img = Image(EXE)
    cmd = sys.argv[1]
    if cmd == "info":
        cmd_info(img)
    elif cmd == "strrefs":
        cmd_strrefs(img, sys.argv[2])
    elif cmd == "nativetable":
        cmd_nativetable(img, sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "disasm":
        cmd_disasm(img, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 60)
    elif cmd == "calls":
        cmd_calls(img, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 200)
    elif cmd == "funcstart":
        cmd_funcstart(img, sys.argv[2],
                      int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x800)
    elif cmd == "rtti":
        for a in sys.argv[2:]:
            cmd_rtti(img, a)
    else:
        print("unknown cmd")


if __name__ == "__main__":
    main()
