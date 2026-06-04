"""Given crash VAs, find the nearest PRECEDING exported symbol in
BioShockInfinite.exe so we know what code is really crashing (the in-game crash
dialog only shows the nearest export name, which can be far away/misleading).

Also dumps the AK::SoundEngine::Init address and a few audio-tunable exports.
"""
import pefile

EXE = r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe"
pe = pefile.PE(EXE)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
base = pe.OPTIONAL_HEADER.ImageBase
exp = pe.DIRECTORY_ENTRY_EXPORT

# (rva, name) sorted
syms = []
for s in exp.symbols:
    if s.name:
        syms.append((s.address, s.name.decode("latin1", "replace")))
syms.sort()

def nearest(va):
    rva = va - base
    best = None
    for addr, name in syms:
        if addr <= rva:
            best = (addr, name)
        else:
            break
    return rva, best

# Crash addresses from the dialog (ASLR off this session: VA == base+RVA)
crash_vas = [0xa0e694, 0xb13c8c, 0xb07593, 0xb0759a, 0xa0ed64, 0xa0f698]
print("=== nearest preceding export to each crash address ===")
for va in crash_vas:
    rva, best = nearest(va)
    if best:
        off = rva - best[0]
        print(f"  VA=0x{va:08X} RVA=0x{rva:06X}  <- {best[1]}  (+0x{off:X})")
    else:
        print(f"  VA=0x{va:08X} RVA=0x{rva:06X}  <- (none)")

print("\n=== Init / Monitor / Queue related exports ===")
for addr, name in syms:
    if any(k in name for k in ("Init@SoundEngine", "Monitor", "SetMonitoring",
                                "PostEvent", "RenderAudio", "Suspend")):
        print(f"  RVA=0x{addr:06X} VA=0x{base+addr:08X}  {name}")
