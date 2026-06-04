"""List exported AK (Wwise) symbols + their RVAs/addresses from BioShockInfinite.exe.
We need the audio init + memory pool functions so winmm.dll can resolve them via
GetProcAddress and enlarge the Wwise pool (fix the AK::MemoryMgr crash under heavy
combat) without lowering the spawn multiplier.
"""
import pefile

EXE = r"D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe"

pe = pefile.PE(EXE)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
base = pe.OPTIONAL_HEADER.ImageBase

exp = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
if not exp:
    print("NO EXPORT DIRECTORY")
    raise SystemExit

print(f"ImageBase=0x{base:08X}  total exports={len(exp.symbols)}")
KEYS = ("Init@", "Term@", "MemSettings", "PlatformInitSettings", "InitSettings",
        "PoolSize", "MemoryMgr", "DefaultPool", "uMax", "Pool")
WANT = ("Init@MemoryMgr", "Init@SoundEngine", "Init@StreamMgr", "GetDefaultSettings",
        "GetDefaultPlatformInitSettings", "GetDefaultInitSettings", "GetDefaultMemSettings",
        "CreatePool", "SetPoolName", "Init@AkMemSettings")

def show(sym):
    name = sym.name.decode("latin1", "replace") if sym.name else f"<ord {sym.ordinal}>"
    print(f"  RVA=0x{sym.address:06X}  VA=0x{base+sym.address:08X}  {name}")

print("\n=== AK init / settings / pool symbols ===")
for sym in exp.symbols:
    if not sym.name:
        continue
    n = sym.name.decode("latin1", "replace")
    if "@AK@" not in n and "AK@@" not in n:
        continue
    if any(k in n for k in WANT):
        show(sym)
