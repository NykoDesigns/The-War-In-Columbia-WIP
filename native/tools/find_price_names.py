"""Search exe for FName strings related to prices, ammo, clips, vending."""
import re

data = open(r'D:\SteamLibrary\steamapps\common\BioShock Infinite\Binaries\Win32\BioShockInfinite.exe', 'rb').read()

keywords = [b'Price', b'SilverEagle', b'ItemPrice', b'UpgradePrice', b'AmmoCost', b'AmmoPrice',
            b'BaseCost', b'VendingItem', b'VendorItem', b'ShopItem', b'BuyPrice', b'SellPrice',
            b'MaxAmmo', b'ClipSize', b'MagazineSize', b'AmmoCount', b'SpareAmmo', b'InitialAmmo',
            b'ClipCount', b'MagSize', b'AmmoPerClip', b'StartingAmmo', b'DefaultAmmo',
            b'Vending', b'DollarBill', b'XItemDatabase']

for kw in keywords:
    pat = re.compile(b'[A-Za-z_]*' + kw + b'[A-Za-z0-9_]*(?=\\x00)')
    matches = pat.findall(data)
    if matches:
        unique = sorted(set(matches))
        for u in unique[:15]:
            try:
                print(f"  {u.decode('ascii')}")
            except:
                pass
