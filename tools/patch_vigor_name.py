"""
Patch vigor display names in GlobalXItemDatabase_SF.xxx
Strategy: Replace FString content in-place, padding shorter names with null bytes.
UE3 FString uses C-string semantics, so embedded nulls effectively truncate the display.
"""
import sys, struct, shutil
from pathlib import Path

sys.path.insert(0, r'z:\TheWarInColumbia')
from core.ue3_parser import UE3Package

GAME_DIR = Path(r'D:\SteamLibrary\steamapps\common\BioShock Infinite')
ITEMDB_PATH = GAME_DIR / 'XGame' / 'CookedPCConsole_FR' / 'GlobalXItemDatabase_SF.xxx'
BACKUP_PATH = ITEMDB_PATH.with_suffix('.xxx.bak')
UI_PATH = GAME_DIR / 'XGame' / 'Localization' / 'INT' / 'UserInterface.int'
UI_BACKUP = UI_PATH.with_suffix('.int.bak')

# ─── Rename mapping ──────────────────────────────────────────────────────────
RENAMES = {
    'Murder of Crows': 'Carrion Call',
}


def patch_itemdb():
    """Patch FString instances in GlobalXItemDatabase_SF.xxx"""
    print(f'Loading {ITEMDB_PATH.name}...')
    pkg = UE3Package.from_file(ITEMDB_PATH)

    # Find the ItemDatabase export (the big one)
    e = pkg.exports[377]
    db_start = e.serial_offset
    db_end = db_start + e.serial_size
    data = pkg._virtual_data

    patches_applied = 0
    for old_name, new_name in RENAMES.items():
        old_bytes = old_name.encode('latin-1') + b'\x00'  # FString content (with null)
        new_bytes = new_name.encode('latin-1') + b'\x00'  # New content (with null)

        # Pad new_bytes to match old_bytes length
        if len(new_bytes) < len(old_bytes):
            new_bytes = new_bytes + b'\x00' * (len(old_bytes) - len(new_bytes))
        elif len(new_bytes) > len(old_bytes):
            print(f'  ERROR: "{new_name}" ({len(new_bytes)}b) is longer than "{old_name}" ({len(old_bytes)}b)!')
            print(f'         Cannot do in-place patch. Choose a shorter name.')
            continue

        # Search for FString instances (preceded by i32 length = len(old_bytes))
        expected_len = len(old_bytes)  # This is the FString length value
        section = data[db_start:db_end]

        idx = 0
        while True:
            idx = section.find(old_name.encode('latin-1'), idx)
            if idx == -1:
                break

            # Check if this is an FString (preceded by matching length)
            if idx >= 4:
                fstr_len = struct.unpack_from('<i', section, idx - 4)[0]
                if fstr_len == expected_len:
                    # This is an FString! Patch it.
                    abs_offset = db_start + idx
                    print(f'  Patching FString "{old_name}" -> "{new_name}" at offset 0x{abs_offset:X}')
                    pkg.patch_bytes(abs_offset, new_bytes)
                    patches_applied += 1
            idx += 1

    if patches_applied > 0:
        # Backup original
        if not BACKUP_PATH.exists():
            print(f'  Creating backup: {BACKUP_PATH.name}')
            shutil.copy2(ITEMDB_PATH, BACKUP_PATH)
        print(f'  Saving patched package ({patches_applied} patches)...')
        pkg.save(ITEMDB_PATH)
        print(f'  Done! Saved to {ITEMDB_PATH}')
    else:
        print('  No FString patches applied.')

    return patches_applied


def patch_ui_localization():
    """Patch UserInterface.int (UTF-16LE) to replace vigor names in tooltips."""
    print(f'\nLoading {UI_PATH.name}...')
    data = open(UI_PATH, 'rb').read()
    text = data.decode('utf-16-le')

    patches = 0
    for old_name, new_name in RENAMES.items():
        count = text.count(old_name)
        if count > 0:
            text = text.replace(old_name, new_name)
            print(f'  Replaced "{old_name}" -> "{new_name}" ({count} occurrences)')
            patches += count

    if patches > 0:
        if not UI_BACKUP.exists():
            print(f'  Creating backup: {UI_BACKUP.name}')
            shutil.copy2(UI_PATH, UI_BACKUP)
        new_data = text.encode('utf-16-le')
        open(UI_PATH, 'wb').write(new_data)
        print(f'  Saved {UI_PATH.name} ({patches} replacements)')
    else:
        print('  No UI text replacements needed.')

    return patches


if __name__ == '__main__':
    print('=== Vigor Name Patcher ===')
    print(f'Renames: {RENAMES}')
    print()

    n1 = patch_itemdb()
    n2 = patch_ui_localization()

    print(f'\n=== Summary: {n1} DB patches + {n2} UI patches applied ===')
    if n1 + n2 > 0:
        print('Restart the game to see changes.')
