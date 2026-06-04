"""
The War In Columbia — Spawn Patcher
=====================================
Patches spawn counts in BioShock Infinite level packages to increase
enemy density. Works by:

1. Parsing the .xxx level sub-packages (*_Game.xxx)
2. Scanning decompressed data for spawn-related UE3 property patterns
3. Multiplying integer spawn count values in-place
4. Saving the package uncompressed

BioShock Infinite encounter system:
  - XSeqAct_SpawnAI / XSeqAct_SpawnScriptedAI: Kismet spawn actions
  - XAIScriptedSpawner: Scripted spawner actors
  - SpawnCount / SpawnInfo: Properties controlling how many AI to spawn
  - Encounter data lives in *_Game.xxx sub-level packages
"""

import struct
from pathlib import Path
from .ue3_parser import UE3Package, read_i32, read_u32


# ─── Spawn Property Names ────────────────────────────────────────────────────

# Properties that control spawn COUNTS (to be multiplied)
# MaxTriggerCount: Kismet SeqAct trigger limit (1 = fire once, 0 = unlimited)
#   Changing from 1 to N makes spawn actions fire N times → N× enemies
SPAWN_COUNT_PROPS = {
    'MaxTriggerCount', 'SpawnCount', 'MaxAlive', 'MaxSpawned',
    'NumToSpawn', 'MaxActorsAlive', 'TotalToSpawn',
    'MaxConcurrent', 'SquadSize', 'WaveSize',
}

# Properties that control spawn TIMING (delays to be divided for faster spawns)
SPAWN_DELAY_PROPS = {
    'SpawnDelay', 'MinSpawnDelay', 'MaxSpawnDelay',
    'RespawnDelay', 'TimeBetweenSpawns', 'WaveDelay',
    'BaseRespawnDuration',
}

# Properties that control spawn RATES (to be multiplied for faster spawns)
SPAWN_RATE_PROPS = {
    'SpawnRate', 'RateOfSpawn', 'RespawnRate',
}

# UE3 property type names we care about
INT_PROP_NAME = 'IntProperty'
FLOAT_PROP_NAME = 'FloatProperty'


# ─── Binary Pattern Scanner ──────────────────────────────────────────────────

def _find_name_index(pkg, name):
    """Find the index of a name in the package's name table."""
    for i, entry in enumerate(pkg.names):
        if entry.name == name:
            return i
    return -1


def _build_prop_index_map(pkg, target_names):
    """Build a map of name_index -> property_name for fast lookup."""
    result = {}
    for name in target_names:
        idx = _find_name_index(pkg, name)
        if idx >= 0:
            result[idx] = name
    return result


def _scan_int_properties(pkg, target_name_indices, type_idx):
    """Scan virtual data for IntProperty instances matching target names.
    
    UE3 property header format:
      name_idx(i32) + name_num(i32) + type_idx(i32) + type_num(i32) + size(i32) + array_idx(i32) + value(i32)
    
    Returns list of (name, value_offset, current_value) tuples.
    """
    data = pkg._virtual_data
    results = []
    
    for name_idx, prop_name in target_name_indices.items():
        # Build the pattern: name_idx + 0 (name_num) + type_idx + 0 (type_num) + 4 (size) + 0 (array_idx)
        pattern = struct.pack('<iiiiiiI', name_idx, 0, type_idx, 0, 4, 0, 0)
        # We only match the first 24 bytes (name+type+size+array_idx), then read value
        header_pattern = pattern[:24]
        
        search_start = 0
        while True:
            pos = data.find(header_pattern, search_start)
            if pos < 0:
                break
            # Value is at pos + 24
            value_offset = pos + 24
            if value_offset + 4 <= len(data):
                value = struct.unpack_from('<i', data, value_offset)[0]
                # Sanity check: spawn counts should be small positive numbers
                if 0 < value < 10000:
                    results.append((prop_name, value_offset, value))
            search_start = pos + 4
    
    return results


def _scan_float_properties(pkg, target_name_indices, type_idx):
    """Scan virtual data for FloatProperty instances matching target names.
    Returns list of (name, value_offset, current_value) tuples.
    """
    data = pkg._virtual_data
    results = []
    
    for name_idx, prop_name in target_name_indices.items():
        # Pattern: name_idx + 0 + type_idx + 0 + 4 (size) + 0 (array_idx)
        header_pattern = struct.pack('<iiiiii', name_idx, 0, type_idx, 0, 4, 0)
        
        search_start = 0
        while True:
            pos = data.find(header_pattern, search_start)
            if pos < 0:
                break
            value_offset = pos + 24
            if value_offset + 4 <= len(data):
                value = struct.unpack_from('<f', data, value_offset)[0]
                # Sanity: delays/rates should be reasonable floats
                if 0.0 < value < 100000.0:
                    results.append((prop_name, value_offset, value))
            search_start = pos + 4
    
    return results


# ─── Public API ──────────────────────────────────────────────────────────────

def find_spawner_exports(pkg):
    """Find spawner-related exports using binary scan (for compatibility).
    Returns list of spawn property locations found.
    """
    int_type_idx = _find_name_index(pkg, INT_PROP_NAME)
    if int_type_idx < 0:
        return []
    
    count_indices = _build_prop_index_map(pkg, SPAWN_COUNT_PROPS)
    return _scan_int_properties(pkg, count_indices, int_type_idx)


# Maximum safe value for MaxTriggerCount on a 32-bit engine.
# Higher values spawn too many AI simultaneously, exceeding the 4GB address space.
MAX_TRIGGER_COUNT_CAP = 3


def scale_spawn_counts(pkg, multiplier):
    """Scale all spawn count properties by a multiplier.
    Scans the entire decompressed package data for spawn count patterns.
    
    For MaxTriggerCount: only patches value=1 (single-fire) to multiplier,
    capped at MAX_TRIGGER_COUNT_CAP to prevent out-of-memory crashes.
    Values of 0 (unlimited) are left unchanged.
    
    Returns count of patched properties.
    """
    if multiplier <= 0 or multiplier == 1.0:
        return 0

    int_type_idx = _find_name_index(pkg, INT_PROP_NAME)
    if int_type_idx < 0:
        return 0

    count_indices = _build_prop_index_map(pkg, SPAWN_COUNT_PROPS)
    if not count_indices:
        return 0

    hits = _scan_int_properties(pkg, count_indices, int_type_idx)
    
    patched = 0
    for prop_name, value_offset, old_val in hits:
        if prop_name == 'MaxTriggerCount':
            # Only patch MaxTriggerCount=1 (single fire) → multiply
            # Leave 0 (unlimited) and >1 (already multi) unchanged
            if old_val == 1:
                new_val = min(max(1, int(multiplier)), MAX_TRIGGER_COUNT_CAP)
                if new_val != old_val:
                    pkg.patch_int32(value_offset, new_val)
                    patched += 1
        else:
            # Standard spawn count: multiply
            new_val = max(1, int(old_val * multiplier))
            if new_val != old_val:
                pkg.patch_int32(value_offset, new_val)
                patched += 1

    return patched


def scale_spawn_rate(pkg, rate_multiplier):
    """Scale spawn timing properties.
    Rate multiplier > 1 means faster spawning (delays divided, rates multiplied).
    Returns count of patched properties.
    """
    if rate_multiplier <= 0 or rate_multiplier == 1.0:
        return 0

    float_type_idx = _find_name_index(pkg, FLOAT_PROP_NAME)
    if float_type_idx < 0:
        return 0

    patched = 0

    # Divide delays
    delay_indices = _build_prop_index_map(pkg, SPAWN_DELAY_PROPS)
    if delay_indices:
        hits = _scan_float_properties(pkg, delay_indices, float_type_idx)
        for prop_name, value_offset, old_val in hits:
            if old_val > 0:
                new_val = old_val / rate_multiplier
                pkg.patch_float(value_offset, new_val)
                patched += 1

    # Multiply rates
    rate_indices = _build_prop_index_map(pkg, SPAWN_RATE_PROPS)
    if rate_indices:
        hits = _scan_float_properties(pkg, rate_indices, float_type_idx)
        for prop_name, value_offset, old_val in hits:
            if old_val > 0:
                new_val = old_val * rate_multiplier
                pkg.patch_float(value_offset, new_val)
                patched += 1

    return patched


def scan_level_spawners(pkg):
    """Scan a package and return summary of spawn properties found."""
    int_type_idx = _find_name_index(pkg, INT_PROP_NAME)
    float_type_idx = _find_name_index(pkg, FLOAT_PROP_NAME)
    
    results = []
    
    if int_type_idx >= 0:
        count_indices = _build_prop_index_map(pkg, SPAWN_COUNT_PROPS)
        for prop_name, offset, value in _scan_int_properties(pkg, count_indices, int_type_idx):
            results.append({'name': prop_name, 'value': value, 'type': 'int', 'offset': offset})
    
    if float_type_idx >= 0:
        delay_indices = _build_prop_index_map(pkg, SPAWN_DELAY_PROPS)
        for prop_name, offset, value in _scan_float_properties(pkg, delay_indices, float_type_idx):
            results.append({'name': prop_name, 'value': round(value, 3), 'type': 'float', 'offset': offset})
        
        rate_indices = _build_prop_index_map(pkg, SPAWN_RATE_PROPS)
        for prop_name, offset, value in _scan_float_properties(pkg, rate_indices, float_type_idx):
            results.append({'name': prop_name, 'value': round(value, 3), 'type': 'float', 'offset': offset})
    
    return results
