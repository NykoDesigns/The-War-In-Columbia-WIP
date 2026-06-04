"""
The War In Columbia: BioShock Infinite — Mod Manager
=====================================================
Main launcher for The War In Columbia BioShock Infinite mod.
Provides a graphical UI for:

  Tab 1 - Spawns:   Spawn density scaling per-level
  Tab 2 - Weapons:  Weapon damage and property values
  Tab 3 - Enemies:  Enemy health multipliers

The mod works by:
  1. Backing up pristine game files on first run.
  2. Restoring pristine files before each apply (clean slate).
  3. Parsing UE3 .xxx packages to locate gameplay objects.
  4. Patching serialized property values (damage, health, spawn counts).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import sys
import os
import shutil
import json
import logging
import datetime
from pathlib import Path

BIOMOD_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(BIOMOD_DIR))

# ─── Settings / Paths ────────────────────────────────────────────────────────
SETTINGS_FILE = BIOMOD_DIR / "settings.json"
DEFAULT_GAME_ROOT = Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite")

_GAME_SEARCH_PATHS = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\BioShock Infinite"),
    Path(r"C:\Program Files\Steam\steamapps\common\BioShock Infinite"),
    Path(r"D:\SteamLibrary\steamapps\common\BioShock Infinite"),
    Path(r"E:\SteamLibrary\steamapps\common\BioShock Infinite"),
    Path(r"F:\SteamLibrary\steamapps\common\BioShock Infinite"),
    Path(r"G:\SteamLibrary\steamapps\common\BioShock Infinite"),
]

def _load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def _detect_game_root():
    settings = _load_settings()
    saved = settings.get('game_root')
    if saved and Path(saved).exists() and (Path(saved) / 'XGame' / 'CookedPCConsole_FR').exists():
        return Path(saved)
    for p in _GAME_SEARCH_PATHS:
        if p.exists() and (p / 'XGame' / 'CookedPCConsole_FR').exists():
            settings['game_root'] = str(p)
            _save_settings(settings)
            return p
    return DEFAULT_GAME_ROOT

GAME_ROOT = _detect_game_root()
COOKED_DIR = GAME_ROOT / "XGame" / "CookedPCConsole_FR"
PRISTINE_DIR = BIOMOD_DIR / "backups" / "pristine"
LOG_DIR = BIOMOD_DIR / "logs"

def _update_game_root(new_root):
    global GAME_ROOT, COOKED_DIR
    GAME_ROOT = Path(new_root)
    COOKED_DIR = GAME_ROOT / "XGame" / "CookedPCConsole_FR"
    settings = _load_settings()
    settings['game_root'] = str(GAME_ROOT)
    _save_settings(settings)


# ─── Import core modules ─────────────────────────────────────────────────────
from core.ue3_parser import UE3Package
from core.property_patcher import (
    read_properties, find_property, patch_float_property,
    patch_int_property, scan_export_properties, scan_package_for_property
)
from core.spawn_patcher import (
    find_spawner_exports, scale_spawn_counts, scale_spawn_rate,
    scan_level_spawners
)
from core.game_data import (
    MAP_NAMES, COMBAT_MAPS, COMBAT_GAME_PACKAGES, ENEMY_TYPES, WEAPONS, VIGORS,
    get_cooked_dir, get_package_path, get_combat_packages
)


# ─── Scrollable Frame helper ────────────────────────────────────────────────

def make_scrollable(parent):
    canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0, bg='#1e1e2e')
    scrollbar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.create_window((0, 0), window=inner, anchor='nw')
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')

    def _on_mousewheel(event):
        try:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass
    canvas.bind_all('<MouseWheel>', _on_mousewheel, add='+')
    canvas.bind('<Destroy>', lambda e: canvas.unbind_all('<MouseWheel>'), add='+')
    return canvas, inner


# ─── Main UI ─────────────────────────────────────────────────────────────────

class WarInColumbiaMod:
    def __init__(self, root):
        self.root = root
        self.root.title("The War In Columbia \u2014 BioShock Infinite Mod Manager")
        self.root.geometry("1050x900")
        self.root.minsize(900, 700)

        self.msg_queue = queue.Queue()
        self.working = False

        # Spawn multiplier vars per map
        self.spawn_vars = {}  # map_stem -> DoubleVar

        # Weapon damage multiplier vars
        self.weapon_vars = {}  # weapon_key -> DoubleVar

        # Enemy health multiplier vars
        self.enemy_vars = {}  # enemy_key -> DoubleVar

        self._build_ui()
        self._poll_queue()
        self._start_analysis()

    # ══════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        BG       = '#1e1e2e'
        BG2      = '#252536'
        BG3      = '#2e2e42'
        FG       = '#cdd6f4'
        FG_DIM   = '#7f849c'
        FG_HEAD  = '#89b4fa'
        FG_TITLE = '#cba6f7'
        BORDER   = '#45475a'
        SELECT   = '#45475a'
        ACCENT   = '#89b4fa'
        ACCENT_FG= '#1e1e2e'
        TAB_BG   = '#313244'
        TAB_SEL  = '#45475a'

        self.root.configure(bg=BG)

        style = ttk.Style()
        style.theme_use('clam')

        style.configure('.', background=BG, foreground=FG, bordercolor=BORDER,
                        font=('Segoe UI', 9))
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=FG)
        style.configure('TLabelframe', background=BG, foreground=FG,
                        bordercolor=BORDER)
        style.configure('TLabelframe.Label', background=BG, foreground=FG_HEAD,
                        font=('Segoe UI', 10, 'bold'))
        style.configure('TNotebook', background=BG, bordercolor=BORDER)
        style.configure('TNotebook.Tab', background=TAB_BG, foreground=FG_DIM,
                        padding=[12, 4], font=('Segoe UI', 9))
        style.map('TNotebook.Tab',
                  background=[('selected', TAB_SEL)],
                  foreground=[('selected', FG)])
        style.configure('TButton', background=ACCENT, foreground=ACCENT_FG,
                        bordercolor=BORDER, focuscolor=ACCENT,
                        font=('Segoe UI', 9, 'bold'), padding=[8, 3])
        style.map('TButton',
                  background=[('active', '#a6d0fb'), ('disabled', '#45475a')],
                  foreground=[('disabled', '#585b70')])
        style.configure('TEntry', fieldbackground=BG3, foreground=FG,
                        insertcolor=FG, bordercolor=BORDER)
        style.configure('TSpinbox', fieldbackground=BG3, foreground=FG,
                        arrowcolor=FG_DIM, bordercolor=BORDER)
        style.configure('TScrollbar', background=BG2, troughcolor=BG,
                        bordercolor=BORDER, arrowcolor=FG_DIM)
        style.configure('TSeparator', background=BORDER)
        style.configure('TScale', background=BG, troughcolor=BG3)

        self.root.option_add('*TCombobox*Listbox.background', BG3)
        self.root.option_add('*TCombobox*Listbox.foreground', FG)

        style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'),
                        foreground=FG_TITLE, background=BG)
        style.configure('Header.TLabel', font=('Segoe UI', 9, 'bold'),
                        foreground=FG_HEAD, background=BG)
        style.configure('Small.TLabel', font=('Segoe UI', 8),
                        foreground=FG_DIM, background=BG)
        style.configure('MapName.TLabel', font=('Segoe UI', 10, 'bold'),
                        foreground=FG_TITLE, background=BG)

        self._colors = {
            'bg': BG, 'bg2': BG2, 'bg3': BG3, 'fg': FG, 'fg_dim': FG_DIM,
            'accent': ACCENT, 'border': BORDER, 'select': SELECT,
        }

        # Main layout
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill='both', expand=True)

        # Title bar
        title_frame = ttk.Frame(main)
        title_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(title_frame, text="The War In Columbia",
                  style='Title.TLabel').pack(side='left')

        # Game path indicator
        self._path_var = tk.StringVar(value=str(GAME_ROOT))
        path_frame = ttk.Frame(title_frame)
        path_frame.pack(side='right')
        ttk.Label(path_frame, textvariable=self._path_var,
                  style='Small.TLabel').pack(side='left', padx=(0, 5))
        ttk.Button(path_frame, text="Browse...",
                   command=self._browse_game).pack(side='left')

        # Notebook (tabs)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill='both', expand=True, pady=(0, 10))

        self._build_spawns_tab()
        self._build_weapons_tab()
        self._build_enemies_tab()

        # Bottom bar
        bottom = ttk.Frame(main)
        bottom.pack(fill='x')

        ttk.Button(bottom, text="Apply Mod", command=self._apply_mod).pack(side='left', padx=5)
        ttk.Button(bottom, text="Restore All", command=self._restore_all).pack(side='left', padx=5)
        ttk.Button(bottom, text="Scan Packages", command=self._scan_packages).pack(side='left', padx=5)

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self._status_var,
                  style='Small.TLabel').pack(side='right', padx=5)

        # Log area
        log_frame = ttk.LabelFrame(main, text="Log", padding=5)
        log_frame.pack(fill='x', pady=(5, 0))
        self.log_text = tk.Text(log_frame, height=6, bg=BG3, fg=FG,
                                font=('Consolas', 8), wrap='word',
                                insertbackground=FG, selectbackground=SELECT,
                                borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill='x')

    def _build_spawns_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text='  Spawns  ')

        canvas, inner = make_scrollable(tab)

        ttk.Label(inner, text="Spawn Density Multiplier Per Level",
                  style='Header.TLabel').pack(anchor='w', padx=10, pady=(10, 5))
        ttk.Label(inner, text="Multiplies MaxAlive/MaxSpawned/SpawnCount in spawner actors. "
                  "1.0 = vanilla, 2.0 = double enemies.",
                  style='Small.TLabel').pack(anchor='w', padx=10, pady=(0, 10))

        for map_stem, friendly_name in MAP_NAMES.items():
            if map_stem not in COMBAT_MAPS:
                continue
            frame = ttk.Frame(inner)
            frame.pack(fill='x', padx=10, pady=2)

            ttk.Label(frame, text=friendly_name, width=40).pack(side='left')

            var = tk.DoubleVar(value=1.0)
            self.spawn_vars[map_stem] = var

            spinbox = ttk.Spinbox(frame, from_=0.5, to=10.0, increment=0.5,
                                  textvariable=var, width=6)
            spinbox.pack(side='left', padx=5)

            ttk.Label(frame, text=f"({map_stem})",
                      style='Small.TLabel').pack(side='left', padx=5)

        # Global spawn rate multiplier
        ttk.Separator(inner).pack(fill='x', padx=10, pady=10)
        rate_frame = ttk.Frame(inner)
        rate_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(rate_frame, text="Global Spawn Rate Multiplier:",
                  style='Header.TLabel').pack(side='left')
        self.spawn_rate_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(rate_frame, from_=0.5, to=5.0, increment=0.25,
                    textvariable=self.spawn_rate_var, width=6).pack(side='left', padx=5)
        ttk.Label(rate_frame, text="(Higher = faster respawns)",
                  style='Small.TLabel').pack(side='left', padx=5)

    def _build_weapons_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text='  Weapons  ')

        canvas, inner = make_scrollable(tab)

        ttk.Label(inner, text="Weapon Damage Multipliers",
                  style='Header.TLabel').pack(anchor='w', padx=10, pady=(10, 5))
        ttk.Label(inner, text="Multiplies base damage values for each weapon type. "
                  "1.0 = vanilla, 2.0 = double damage.",
                  style='Small.TLabel').pack(anchor='w', padx=10, pady=(0, 10))

        for weapon_key, friendly_name in WEAPONS.items():
            frame = ttk.Frame(inner)
            frame.pack(fill='x', padx=10, pady=2)

            ttk.Label(frame, text=friendly_name, width=35).pack(side='left')

            var = tk.DoubleVar(value=1.0)
            self.weapon_vars[weapon_key] = var

            spinbox = ttk.Spinbox(frame, from_=0.1, to=10.0, increment=0.25,
                                  textvariable=var, width=6)
            spinbox.pack(side='left', padx=5)

        # Global weapon multiplier
        ttk.Separator(inner).pack(fill='x', padx=10, pady=10)
        global_frame = ttk.Frame(inner)
        global_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(global_frame, text="Set All Weapons To:",
                  style='Header.TLabel').pack(side='left')
        self._global_weapon_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(global_frame, from_=0.1, to=10.0, increment=0.25,
                    textvariable=self._global_weapon_var, width=6).pack(side='left', padx=5)
        ttk.Button(global_frame, text="Apply To All",
                   command=self._set_all_weapons).pack(side='left', padx=5)

    def _build_enemies_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text='  Enemies  ')

        canvas, inner = make_scrollable(tab)

        ttk.Label(inner, text="Enemy Health Multipliers",
                  style='Header.TLabel').pack(anchor='w', padx=10, pady=(10, 5))
        ttk.Label(inner, text="Multiplies base health values for each enemy type. "
                  "1.0 = vanilla, 0.5 = half health, 2.0 = double health.",
                  style='Small.TLabel').pack(anchor='w', padx=10, pady=(0, 10))

        for enemy_key, friendly_name in ENEMY_TYPES.items():
            frame = ttk.Frame(inner)
            frame.pack(fill='x', padx=10, pady=2)

            ttk.Label(frame, text=friendly_name, width=35).pack(side='left')

            var = tk.DoubleVar(value=1.0)
            self.enemy_vars[enemy_key] = var

            spinbox = ttk.Spinbox(frame, from_=0.1, to=10.0, increment=0.25,
                                  textvariable=var, width=6)
            spinbox.pack(side='left', padx=5)

        # Global enemy multiplier
        ttk.Separator(inner).pack(fill='x', padx=10, pady=10)
        global_frame = ttk.Frame(inner)
        global_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(global_frame, text="Set All Enemies To:",
                  style='Header.TLabel').pack(side='left')
        self._global_enemy_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(global_frame, from_=0.1, to=10.0, increment=0.25,
                    textvariable=self._global_enemy_var, width=6).pack(side='left', padx=5)
        ttk.Button(global_frame, text="Apply To All",
                   command=self._set_all_enemies).pack(side='left', padx=5)

    # ══════════════════════════════════════════════════════════════════════
    # ACTIONS
    # ══════════════════════════════════════════════════════════════════════

    def _browse_game(self):
        path = filedialog.askdirectory(title="Select BioShock Infinite Installation")
        if path:
            p = Path(path)
            if (p / 'XGame' / 'CookedPCConsole_FR').exists():
                _update_game_root(p)
                self._path_var.set(str(p))
                self._log("Game root updated: " + str(p))
            else:
                messagebox.showerror("Invalid Path",
                    "Could not find XGame/CookedPCConsole_FR in the selected directory.")

    def _set_all_weapons(self):
        val = self._global_weapon_var.get()
        for var in self.weapon_vars.values():
            var.set(val)

    def _set_all_enemies(self):
        val = self._global_enemy_var.get()
        for var in self.enemy_vars.values():
            var.set(val)

    def _log(self, msg):
        self.msg_queue.put(msg + '\n')

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self.log_text.insert('end', msg)
                self.log_text.see('end')
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _start_analysis(self):
        """Background analysis of game packages."""
        def analyze():
            self._log("Checking game installation...")
            if not COOKED_DIR.exists():
                self._log(f"ERROR: Cooked directory not found: {COOKED_DIR}")
                return
            # Count available packages
            xxx_count = len(list(COOKED_DIR.glob("*.xxx")))
            self._log(f"Found {xxx_count} packages in {COOKED_DIR.name}")

            # Check for combat level packages
            combat_count = 0
            for stem in COMBAT_MAPS:
                if (COOKED_DIR / f"{stem}.xxx").exists():
                    combat_count += 1
            self._log(f"Combat level packages found: {combat_count}/{len(COMBAT_MAPS)}")
            self._status_var.set(f"Ready — {combat_count} combat levels available")

        threading.Thread(target=analyze, daemon=True).start()

    def _ensure_backup(self, filepath):
        """Ensure a pristine backup exists for the given file."""
        rel = filepath.relative_to(COOKED_DIR)
        backup_path = PRISTINE_DIR / rel
        if not backup_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, backup_path)
            return True
        return False

    def _restore_file(self, filepath):
        """Restore a file from pristine backup."""
        rel = filepath.relative_to(COOKED_DIR)
        backup_path = PRISTINE_DIR / rel
        if backup_path.exists():
            shutil.copy2(backup_path, filepath)
            return True
        return False

    def _apply_mod(self):
        if self.working:
            return
        self.working = True
        self._status_var.set("Applying mod...")

        def do_apply():
            try:
                self._log("=" * 60)
                self._log("APPLYING MOD — " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                self._log("=" * 60)

                total_patched = 0

                # ── Step 1: Spawn scaling ─────────────────────────────
                self._log("\n[Step 1] Spawn Scaling...")
                rate_mult = self.spawn_rate_var.get()

                patched_pkgs = set()  # avoid patching same sub-pkg twice
                for map_stem, var in self.spawn_vars.items():
                    mult = 3.0  # Fixed x3 multiplier (safe for 32-bit engine)
                    if mult == 1.0 and rate_mult == 1.0:
                        continue

                    # Get the game sub-packages for this map
                    game_pkgs = COMBAT_GAME_PACKAGES.get(map_stem, [])
                    if not game_pkgs:
                        # Fallback: try the map stem itself
                        game_pkgs = [map_stem]

                    map_count = 0
                    for sub_pkg_name in game_pkgs:
                        if sub_pkg_name in patched_pkgs:
                            continue

                        pkg_path = COOKED_DIR / f"{sub_pkg_name}.xxx"
                        if not pkg_path.exists():
                            continue

                        self._ensure_backup(pkg_path)
                        self._restore_file(pkg_path)  # always patch from clean

                        try:
                            pkg = UE3Package.from_file(pkg_path)
                            count = 0

                            if mult != 1.0:
                                count += scale_spawn_counts(pkg, mult)

                            if rate_mult != 1.0:
                                count += scale_spawn_rate(pkg, rate_mult)

                            if count > 0:
                                pkg.save()
                                self._log(f"  {sub_pkg_name}: patched {count} properties (x{mult})")
                                total_patched += count
                                map_count += count
                            patched_pkgs.add(sub_pkg_name)
                        except Exception as e:
                            self._log(f"  ERROR in {sub_pkg_name}: {e}")

                    if map_count == 0 and (mult != 1.0 or rate_mult != 1.0):
                        self._log(f"  {map_stem}: no game sub-packages found to patch")

                # ── Step 2: Weapon damage ─────────────────────────────
                self._log("\n[Step 2] Weapon Damage Scaling...")
                weapons_to_patch = {k: v.get() for k, v in self.weapon_vars.items()
                                    if v.get() != 1.0}
                if weapons_to_patch:
                    self._log(f"  {len(weapons_to_patch)} weapon(s) with non-default multipliers")
                    # Weapon data is in GlobalXItemDatabase or Master_P
                    for pkg_name in ('GlobalXItemDatabase_SF', 'Master_P'):
                        pkg_path = COOKED_DIR / f"{pkg_name}.xxx"
                        if not pkg_path.exists():
                            continue
                        self._ensure_backup(pkg_path)
                        self._restore_file(pkg_path)
                        try:
                            pkg = UE3Package.from_file(pkg_path)
                            count = self._patch_weapon_damage(pkg, weapons_to_patch)
                            if count > 0:
                                pkg.save()
                                self._log(f"  {pkg_name}: patched {count} weapon damage values")
                                total_patched += count
                        except Exception as e:
                            self._log(f"  ERROR in {pkg_name}: {e}")
                else:
                    self._log("  All weapons at default (1.0x) — skipping")

                # ── Step 3: Enemy health ──────────────────────────────
                self._log("\n[Step 3] Enemy Health Scaling...")
                enemies_to_patch = {k: v.get() for k, v in self.enemy_vars.items()
                                    if v.get() != 1.0}
                if enemies_to_patch:
                    self._log(f"  {len(enemies_to_patch)} enemy type(s) with non-default multipliers")
                    for pkg_name in ('GlobalXItemDatabase_SF', 'Master_P'):
                        pkg_path = COOKED_DIR / f"{pkg_name}.xxx"
                        if not pkg_path.exists():
                            continue
                        self._ensure_backup(pkg_path)
                        self._restore_file(pkg_path)
                        try:
                            pkg = UE3Package.from_file(pkg_path)
                            count = self._patch_enemy_health(pkg, enemies_to_patch)
                            if count > 0:
                                pkg.save()
                                self._log(f"  {pkg_name}: patched {count} health values")
                                total_patched += count
                        except Exception as e:
                            self._log(f"  ERROR in {pkg_name}: {e}")
                else:
                    self._log("  All enemies at default (1.0x) — skipping")

                self._log(f"\nDone! Total properties patched: {total_patched}")
                self._status_var.set(f"Mod applied — {total_patched} values patched")

            except Exception as e:
                self._log(f"\nFATAL ERROR: {e}")
                self._status_var.set("Error during apply")
            finally:
                self.working = False

        threading.Thread(target=do_apply, daemon=True).start()

    def _patch_weapon_damage(self, pkg, weapon_multipliers):
        """Find weapon-related exports and scale their damage properties."""
        patched = 0
        damage_props = ('Damage', 'BaseDamage', 'DamagePerShot', 'InstantHitDamage')

        for exp in pkg.exports:
            if exp.serial_size <= 16:
                continue
            obj_name = pkg.get_name(exp.object_name).lower()

            # Match weapon exports by name
            matched_mult = None
            for wep_key, mult in weapon_multipliers.items():
                if wep_key.lower() in obj_name:
                    matched_mult = mult
                    break

            if matched_mult is None:
                continue

            try:
                props = read_properties(pkg, exp)
                for p in props:
                    if p.name in damage_props and p.type_name == 'FloatProperty':
                        old_val = p.float_value
                        if old_val > 0:
                            new_val = old_val * matched_mult
                            patch_float_property(pkg, p, new_val)
                            patched += 1
                    elif p.name in damage_props and p.type_name == 'IntProperty':
                        old_val = p.int_value
                        if old_val > 0:
                            new_val = max(1, int(old_val * matched_mult))
                            patch_int_property(pkg, p, new_val)
                            patched += 1
            except Exception:
                continue

        return patched

    def _patch_enemy_health(self, pkg, enemy_multipliers):
        """Find enemy-related exports and scale their health properties."""
        patched = 0
        health_props = ('Health', 'MaxHealth', 'HealthMax', 'BaseHealth',
                        'ShieldHealth', 'ShieldMaxHealth')

        for exp in pkg.exports:
            if exp.serial_size <= 16:
                continue
            obj_name = pkg.get_name(exp.object_name).lower()

            # Match enemy exports by name
            matched_mult = None
            for enemy_key, mult in enemy_multipliers.items():
                if enemy_key.lower() in obj_name:
                    matched_mult = mult
                    break

            if matched_mult is None:
                continue

            try:
                props = read_properties(pkg, exp)
                for p in props:
                    if p.name in health_props and p.type_name == 'FloatProperty':
                        old_val = p.float_value
                        if old_val > 0:
                            new_val = old_val * matched_mult
                            patch_float_property(pkg, p, new_val)
                            patched += 1
                    elif p.name in health_props and p.type_name == 'IntProperty':
                        old_val = p.int_value
                        if old_val > 0:
                            new_val = max(1, int(old_val * matched_mult))
                            patch_int_property(pkg, p, new_val)
                            patched += 1
            except Exception:
                continue

        return patched

    def _restore_all(self):
        if self.working:
            return
        self.working = True
        self._status_var.set("Restoring...")

        def do_restore():
            try:
                self._log("\nRestoring all files from pristine backups...")
                restored = 0
                if PRISTINE_DIR.exists():
                    for backup_file in PRISTINE_DIR.rglob("*.xxx"):
                        rel = backup_file.relative_to(PRISTINE_DIR)
                        target = COOKED_DIR / rel
                        shutil.copy2(backup_file, target)
                        restored += 1
                self._log(f"Restored {restored} file(s) to vanilla state.")
                self._status_var.set(f"Restored {restored} files")
            except Exception as e:
                self._log(f"ERROR during restore: {e}")
                self._status_var.set("Error during restore")
            finally:
                self.working = False

        threading.Thread(target=do_restore, daemon=True).start()

    def _scan_packages(self):
        """Scan a package and log findings (for development/debugging)."""
        if self.working:
            return
        self.working = True
        self._status_var.set("Scanning...")

        def do_scan():
            try:
                # Scan the first available combat level
                for stem in COMBAT_MAPS:
                    pkg_path = COOKED_DIR / f"{stem}.xxx"
                    if not pkg_path.exists():
                        continue
                    self._log(f"\nScanning {stem}...")
                    try:
                        pkg = UE3Package.from_file(pkg_path)
                        self._log(pkg.summary())

                        # Find spawner-like exports
                        spawners = find_spawner_exports(pkg)
                        self._log(f"  Spawner-like exports: {len(spawners)}")
                        for sp in spawners[:10]:
                            name = pkg.get_name(sp.object_name)
                            cls = pkg.resolve_class_name(sp)
                            self._log(f"    [{sp.index}] {name} ({cls}, {sp.serial_size} bytes)")

                        # Sample some properties
                        if spawners:
                            sp = spawners[0]
                            try:
                                props = read_properties(pkg, sp)
                                self._log(f"  Properties of first spawner ({pkg.get_name(sp.object_name)}):")
                                for p in props[:15]:
                                    self._log(f"    {p}")
                            except Exception as e:
                                self._log(f"  Could not read properties: {e}")

                    except Exception as e:
                        self._log(f"  ERROR: {e}")
                    break  # just scan first available

                self._status_var.set("Scan complete")
            except Exception as e:
                self._log(f"Scan error: {e}")
            finally:
                self.working = False

        threading.Thread(target=do_scan, daemon=True).start()


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app = WarInColumbiaMod(root)
    root.mainloop()

if __name__ == '__main__':
    main()
