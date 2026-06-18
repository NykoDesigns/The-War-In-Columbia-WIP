"""Check what format 'Murder of Crows' appears in within the loaded package files.
The game deserializes ANSI FStrings (positive length) into wchar_t, but the
original ASCII bytes still exist in the loaded package buffer.
Also check if there's a GFxUI.int localization file used by Scaleform."""
import os, glob

GAME_DIR = r'D:\SteamLibrary\steamapps\common\BioShock Infinite'

# Check for GFxUI localization files
print("=== Searching for GFxUI localization files ===")
for root, dirs, files in os.walk(os.path.join(GAME_DIR, 'XGame')):
    for f in files:
        if 'gfx' in f.lower() or 'scaleform' in f.lower():
            print(f'  {os.path.join(root, f)}')

# Check all .int files for vigor name references
print("\n=== Localization files (.int) with 'Murder' or 'Crows' ===")
for root, dirs, files in os.walk(os.path.join(GAME_DIR, 'XGame', 'Localization')):
    for f in files:
        if f.endswith('.int'):
            fpath = os.path.join(root, f)
            try:
                data = open(fpath, 'rb').read()
                text = data.decode('utf-16-le', errors='replace')
                if 'Murder' in text or 'Crows' in text or 'MurderOfCrows' in text:
                    # Count occurrences
                    count = text.count('Murder of Crows') + text.count('MurderOfCrows')
                    print(f'  {f}: {count} refs')
                    # Show matching lines
                    for line in text.split('\n'):
                        if 'Murder' in line or 'Crows' in line:
                            print(f'    {line.strip()[:120]}')
            except:
                pass

# Check for any .int file that has vigor-related item names
print("\n=== All .int files ===")
for root, dirs, files in os.walk(os.path.join(GAME_DIR, 'XGame', 'Localization')):
    for f in sorted(files):
        if f.endswith('.int'):
            print(f'  {os.path.join(root, f)}')
