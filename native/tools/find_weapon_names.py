"""Search localization files and exe for BioShock weapon class/item names."""
import os, re, glob

game_dir = r'D:\SteamLibrary\steamapps\common\BioShock Infinite'

# Search localization files for weapon names
print("=== Localization files ===")
for pattern in ['**/*.int', '**/*.INT']:
    for f in glob.glob(os.path.join(game_dir, 'XGame', 'Localization', pattern), recursive=True):
        try:
            text = open(f, 'r', encoding='utf-16-le', errors='replace').read()
        except:
            try: text = open(f, 'r', errors='replace').read()
            except: continue
        for line in text.split('\n'):
            line = line.strip()
            if not line or line.startswith(';'):
                continue
            ll = line.lower()
            if any(w in ll for w in ['machine', 'gun', 'crank', 'gatling', 'repeater', 'pepper',
                                      'vigor', 'salt', 'crow', 'devil', 'shock', 'bucking',
                                      'carbine', 'pistol', 'shotgun', 'sniper', 'rpg',
                                      'volley', 'burst', 'hail', 'heater', 'barnstorm',
                                      'ammo', 'cost', 'fireinterval', 'damage']):
                fname = os.path.basename(f)
                print(f"  [{fname}] {line[:120]}")
        
# Search ini/config files
print("\n=== Config files ===")
for pattern in ['**/*.ini']:
    for f in glob.glob(os.path.join(game_dir, 'XGame', 'Config', pattern), recursive=True):
        try: text = open(f, 'r', errors='replace').read()
        except: continue
        for line in text.split('\n'):
            line = line.strip()
            ll = line.lower()
            if any(w in ll for w in ['machine', 'crank', 'gatling', 'fireinterval', 'firerate',
                                      'salt', 'ammocost', 'costper', 'damage']):
                fname = os.path.basename(f)
                print(f"  [{fname}] {line[:150]}")
