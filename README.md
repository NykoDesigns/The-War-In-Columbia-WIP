# The War In Columbia — BioShock Infinite Overhaul Mod

A comprehensive mod manager for **BioShock Infinite** that overhauls combat encounters, weapon damage, and enemy health — all configurable through a GUI with no manual file editing required.

---

## Features

### Combat & Encounters
- **Spawn Multipliers** — increase or decrease spawner density per level
- **Scripted Encounter Scaling** — multiply enemies in scripted combat events

### Weapons
- **Damage Values** — granular control over every weapon type
- **Weapon Properties** — fire rate, magazine size, spread adjustments

### Enemies
- **Health Tuning** — per-enemy-type health multipliers
- **Enemy Types** — Soldiers, Automatons (Patriots, Mosquitoes, Turrets), Handymen, Sirens, Firemen, Crows

---

## How It Works

BioShock Infinite uses **Unreal Engine 3** (modified, codename "Icarus"). Unlike BioShock 1/2 which store balance data in INI archives, Infinite stores gameplay data as serialized object properties inside cooked UE3 packages (`.xxx` files).

The mod operates by:

1. **Backing up** pristine copies of game packages on first run
2. **Parsing** UE3 packages to locate weapon/enemy/spawner objects
3. **Patching** serialized property values (damage floats, health integers, spawn counts)
4. **Duplicating** spawner export entries in level packages for density scaling
5. **Rewriting** packages with updated headers and data

### Technical Details

- **Package Format**: UE3 cooked packages, version 727, licensee 75
- **File Extension**: `.xxx` (cooked seek-free packages)
- **Data Location**: `XGame/CookedPCConsole_FR/`
- **Key Packages**:
  - `GlobalXItemDatabase_SF.xxx` — Item/weapon database
  - `Master_P.xxx` — Persistent level with global archetypes
  - `S_TWN_P.xxx`, `S_BW_P.xxx`, etc. — Level packages with spawners

---

## For Developers

### Project Structure

```
TheWarInColumbia/
├── war_in_columbia.py           # Main mod manager GUI (tkinter)
├── settings.json                # User configuration (game path)
├── README.md                    # This file
├── core/
│   ├── __init__.py              # Package init
│   ├── ue3_parser.py            # UE3 package format reader/writer
│   ├── property_patcher.py     # UE3 property value scanner/patcher
│   ├── spawn_patcher.py        # Spawner duplication in level packages
│   └── game_data.py            # BioShock Infinite specific data (maps, weapons, enemies)
├── backups/
│   └── pristine/               # Unmodified package copies (auto-created)
└── logs/                        # Operation logs
```

### Requirements

- **Python 3.10+**
- **tkinter** (included with standard Python on Windows)

### Running

```bash
python war_in_columbia.py
```

---

## Level Map Reference

| Internal Name | Location |
|--------------|----------|
| S_Light_P | Lighthouse |
| S_TWN_P | Town Center (Welcome Center, Fair, Streets) |
| S_TWN2_P | Town Center 2 (Rooftops, Monument) |
| S_TWN3_P | Town Center 3 (Gondola, Comstock Gate) |
| S_LizT_P | Monument Island (Elizabeth's Tower) |
| S_BW_P | Battleship Bay / Boardwalk |
| S_BW2_P | Soldier's Field / Hall of Heroes |
| S_BW3_P | Hall of Heroes Interior |
| S_Fink_P | Finkton Proper |
| S_Fink2_P | Finkton Docks / Shantytown |
| S_Fink3_P | Finkton Factory |
| S_Fink4_P | Finkton Hub / Bull Yard |
| S_EMP_P | Emporia |
| S_EMP2_P | Emporia 2 (Bank, Downtown) |
| S_DCOM_P | Comstock House |
| S_CHU_P | Hand of the Prophet / Final Battle |
| S_Lut_P | Sea of Doors / Ending |

---

## License

This project is provided as-is for modding purposes. BioShock Infinite is the property of 2K Games / Take-Two Interactive.
