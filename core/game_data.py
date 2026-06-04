"""
The War In Columbia — BioShock Infinite Game Data
==================================================
Maps, weapons, enemies, and other game-specific data for BioShock Infinite.
"""

from collections import OrderedDict


# ─── Level Maps ───────────────────────────────────────────────────────────────

MAP_NAMES = OrderedDict([
    ('S_Light_P',   'Lighthouse'),
    ('S_TWN_P',     'Town Center — Welcome Center & Fair'),
    ('S_TWN2_P',    'Town Center — Rooftops & Monument Tower'),
    ('S_TWN3_P',    'Town Center — Gondola & Comstock Gate'),
    ('S_LizT_P',    "Monument Island — Elizabeth's Tower"),
    ('S_OFB_P',     'Office Flashback'),
    ('S_BW_P',      'Battleship Bay / Soldier\'s Field'),
    ('S_BW2_P',     "Soldier's Field / Hall of Heroes"),
    ('S_BW3_P',     'Hall of Heroes Interior'),
    ('S_Fink_P',    'Finkton Proper'),
    ('S_Fink2_P',   'Finkton Docks / Shantytown'),
    ('S_Fink3_P',   'Finkton Factory / Good Time Club'),
    ('S_Fink4_P',   'Finkton Hub / Bull Yard'),
    ('S_EMP_P',     'Emporia — Downtown'),
    ('S_EMP2_P',    'Emporia — Bank of the Prophet'),
    ('S_DCOM_P',    'Comstock House'),
    ('S_CHU_P',     'Hand of the Prophet / Final Battle'),
    ('S_Lut_P',     'Sea of Doors / Ending'),
])

# Maps that contain significant combat encounters (skip non-combat maps)
COMBAT_MAPS = [
    'S_TWN_P', 'S_TWN2_P', 'S_TWN3_P',
    'S_BW_P', 'S_BW2_P', 'S_BW3_P',
    'S_Fink_P', 'S_Fink2_P', 'S_Fink3_P', 'S_Fink4_P',
    'S_EMP_P', 'S_EMP2_P',
    'S_DCOM_P', 'S_CHU_P',
]


# ─── Enemy Types ──────────────────────────────────────────────────────────────

ENEMY_TYPES = OrderedDict([
    # Founders (Blue)
    ('FounderSoldier',      'Founder Soldier'),
    ('FounderSniper',       'Founder Sniper'),
    ('FounderRPG',          'Founder RPG'),
    ('FounderShotgunner',   'Founder Shotgunner'),
    ('FounderPistol',       'Founder Pistol'),
    ('FounderMelee',        'Founder Melee'),
    # Vox Populi (Red)
    ('VoxSoldier',          'Vox Soldier'),
    ('VoxSniper',           'Vox Sniper'),
    ('VoxRPG',              'Vox RPG'),
    ('VoxShotgunner',       'Vox Shotgunner'),
    ('VoxPistol',           'Vox Pistol'),
    ('VoxMelee',            'Vox Melee'),
    # Heavy Units
    ('Fireman',             'Fireman'),
    ('Crow',                'Crow (Zealot of the Lady)'),
    ('Handyman',            'Handyman'),
    ('Siren',               'Siren (Lady Comstock)'),
    # Automatons
    ('PatriotMech',         'Motorized Patriot'),
    ('MosquitoMech',        'Mosquito (Zeppelin Drone)'),
    ('Turret',              'Machine Gun Turret'),
    ('RocketTurret',        'Rocket Turret'),
    ('VolleyGunTurret',     'Volley Gun Turret'),
    # Boys of Silence (Comstock House)
    ('BoyOfSilence',        'Boy of Silence'),
])


# ─── Weapons ──────────────────────────────────────────────────────────────────

WEAPONS = OrderedDict([
    # Pistols
    ('Broadsider',          'Broadsider Pistol'),
    ('Mauser',              'Mauser Pistol (Vox)'),
    # Rifles
    ('Carbine',             'Triple R Machine Gun'),
    ('Burstgun',            'Burstgun (Vox)'),
    ('Sniper',              'Bird\'s Eye Sniper Rifle'),
    # Shotguns
    ('Shotgun',             'China Broom Shotgun'),
    ('Heater',              'Heater (Vox)'),
    # Heavy
    ('RPG',                 'RPG'),
    ('Volley',              'Volley Gun'),
    ('Crank',               'Hand Cannon (Crank Gun)'),
    ('Peppermill',          'Peppermill Crank Gun (Patriot)'),
    # Special
    ('Hailfire',            'Hail Fire'),
    ('Barnstormer',         'Barnstormer RPG (Vox)'),
    # Melee
    ('Skyhook',             'Sky-Hook'),
])


# ─── Vigors ──────────────────────────────────────────────────────────────────

VIGORS = OrderedDict([
    ('Possession',          'Possession'),
    ('DevilsKiss',          "Devil's Kiss"),
    ('MurderOfCrows',       'Murder of Crows'),
    ('Bucking Bronco',      'Bucking Bronco'),
    ('ShockJockey',         'Shock Jockey'),
    ('Charge',              'Charge'),
    ('Undertow',            'Undertow'),
    ('ReturnToSender',      'Return to Sender'),
])


# ─── Known Property Names (for scanning) ─────────────────────────────────────

# Properties commonly found on weapon archetypes
WEAPON_PROPERTIES = [
    'Damage', 'BaseDamage', 'DamagePerShot', 'DamageMultiplier',
    'FireRate', 'RateOfFire', 'ReloadTime', 'MagazineSize',
    'MaxAmmo', 'AmmoPerShot', 'Spread', 'SpreadMin', 'SpreadMax',
    'HeadshotMultiplier', 'CritMultiplier', 'Range', 'MaxRange',
]

# Properties commonly found on NPC/Pawn archetypes
ENEMY_PROPERTIES = [
    'Health', 'MaxHealth', 'HealthMax', 'BaseHealth',
    'ShieldHealth', 'ShieldMaxHealth', 'ShieldRechargeRate',
    'MeleeDamage', 'MeleeDamageBase',
    'MovementSpeed', 'RunSpeed', 'WalkSpeed',
]

# Properties commonly found on spawner actors
SPAWNER_PROPERTIES = [
    'MaxAlive', 'MaxSpawned', 'SpawnRate', 'SpawnDelay',
    'MinSpawnDelay', 'MaxSpawnDelay', 'SpawnCount',
    'bEnabled', 'bActive',
]


# ─── Game Sub-Packages (encounter data) ──────────────────────────────────────

# Each combat map has sub-level *_Game*.xxx packages containing encounter logic.
# These are the packages that need patching for spawn scaling.
COMBAT_GAME_PACKAGES = {
    'S_TWN_P': [
        'S_TWN_Lottery_Game', 'S_TWN_Lottery_Game2',
        'S_TWN_Alley_Game', 'S_TWN_FairStreet_Game',
        'S_TWN_Skywalk_Game', 'S_TWN_CrowRoof_Game',
    ],
    'S_TWN2_P': [
        'S_TWN_Lottery_Game2', 'S_TWN_Skywalk_Game',
    ],
    'S_TWN3_P': [
        'S_TWN_Gondola_Game',
    ],
    'S_BW_P': [
        'S_BW_Sherman_Game', 'S_BW_Sherman_AL_Game',
        'S_BW_Sherman_Out_Game', 'S_BW_Sherman_Out_AL_Game',
        'S_BW_Middletown_A_Game', 'S_BW_Middletown_Game',
        'S_BW_Skyhook_Game', 'S_BW_Skyhook_Game_A', 'S_BW_Skyhook_Game_B',
        'S_BW_Skyline_Training_Game',
    ],
    'S_BW2_P': [
        'S_BW_Madison_Game', 'S_BW_Madison_A_Game', 'S_BW_Madison_B_Game',
        'S_BW_Hotel_in_game', 'S_BW_Hotel_Wing_BR_Game',
        'S_BW_Hotel_Wing_Game', 'S_BW_Hotel_Wing_WK_Game',
        'S_BW_Wonder_Game',
    ],
    'S_BW3_P': [
        'S_BW_Hotel_in_game', 'S_BW_Hotel_center_Game',
    ],
    'S_Fink_P': [
        'S_Fink_Hub_Game', 'S_Fink_Hub_Game01', 'S_Fink_Hub_Game01Handy',
        'S_Fink_Hub_Game02', 'S_Fink_Hub_Game03',
        'S_Fink_Hub_Elevator_Game', 'S_Fink_Terr_Game', 'S_Fink_Terr_Ext_Game',
    ],
    'S_Fink2_P': [
        'S_Fink_Docks_Game', 'S_Fink_Docks_B_Game', 'S_Fink_Docks_Gate_Game',
        'S_Fink_Shanty_Hub_Game', 'S_Fink_Shanty_Bar_Ext_Game',
        'S_Fink_Shanty_Bar_Int_Game', 'S_Fink_Shanty_EnterStreet_Game',
        'S_Fink_Shanty_Voxed_Game', 'S_Fink_Shanty_Underpass_Game',
        'S_Fink_Lockup_Game',
    ],
    'S_Fink3_P': [
        'S_Fink_Bar_Game', 'S_Fink_Bar_Game2',
        'S_Fink_Factory_Game', 'S_Fink_FactoryBoss_Game',
        'S_Fink_Basement_Game', 'S_Fink_BasementStairs_Game',
    ],
    'S_Fink4_P': [
        'S_Fink_Hub_Game01', 'S_Fink_Hub_Game01Handy',
        'S_Fink_Hub_Game02', 'S_Fink_Hub_Game03',
    ],
    'S_EMP_P': [
        'S_EMP_Station_Game', 'S_EMP_StationA_Game', 'S_EMP_StationC_Game',
        'S_EMP_Street_Game', 'S_EMP_Statue_Game',
        'S_EMP_Market_Game', 'S_EMP_PatriotPark_Game',
        'S_EMP_Funicular_Game',
    ],
    'S_EMP2_P': [
        'S_EMP_Bank_Game', 'S_EMP_BankInt_Game', 'S_EMP_Bank2Mrkt_Game',
        'S_EMP_Manor_Game', 'S_EMP_ALock_Siren_Game',
    ],
    'S_DCOM_P': [
        'S_DCOM_Foyer_Game', 'S_DCOM_Atrium_Game',
        'S_DCOM_AtriumSkirmish_Game', 'S_DCOM_OR_Game',
        'S_DCOM_SecOffice_Game',
    ],
    'S_CHU_P': [
        'S_DCOM_AtriumSkirmish_Game', 'S_DCOM_OR_Game',
    ],
}


# ─── File Paths ───────────────────────────────────────────────────────────────

def get_cooked_dir(game_root):
    """Get the path to the cooked content directory."""
    from pathlib import Path
    return Path(game_root) / 'XGame' / 'CookedPCConsole_FR'


def get_package_path(game_root, package_name):
    """Get the full path to a specific .xxx package."""
    cooked = get_cooked_dir(game_root)
    return cooked / f'{package_name}.xxx'


def get_level_packages(game_root):
    """Get all level package paths that exist on disk."""
    from pathlib import Path
    cooked = get_cooked_dir(game_root)
    packages = []
    for name in MAP_NAMES.keys():
        path = cooked / f'{name}.xxx'
        if path.exists():
            packages.append((name, path))
    return packages


def get_combat_packages(game_root):
    """Get combat-relevant level package paths."""
    from pathlib import Path
    cooked = get_cooked_dir(game_root)
    packages = []
    for name in COMBAT_MAPS:
        path = cooked / f'{name}.xxx'
        if path.exists():
            packages.append((name, path))
    return packages
