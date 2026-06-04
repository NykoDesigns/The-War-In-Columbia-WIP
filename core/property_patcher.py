"""
The War In Columbia — UE3 Property Patcher
============================================
Reads and patches serialized UE3 properties within export objects.

UE3 properties are stored as a tagged list:
  - Name index (i32 + i32 number) identifying the property name
  - Type name index (i32 + i32 number) identifying the property type
  - Size (i32) of the property value data
  - Array index (i32) for array elements
  - Value data (size bytes)
  - Terminated by 'None' name

Supported property types for patching:
  - IntProperty: 4 bytes (i32)
  - FloatProperty: 4 bytes (f32)
  - BoolProperty: 4 bytes (u32, 0 or 1) — stored in array_index field
  - NameProperty: 8 bytes (name_index + number)
  - ObjectProperty: 4 bytes (object reference index)
  - StructProperty: variable (struct_name + nested properties)
  - ArrayProperty: variable (count + elements)
"""

import struct
from .ue3_parser import (
    read_i32, read_u32, read_u64, read_f32, read_fstring,
    write_i32, write_f32, UE3Package
)


# ─── Property Types ──────────────────────────────────────────────────────────

PROP_TYPES = {
    'IntProperty', 'FloatProperty', 'BoolProperty', 'StrProperty',
    'NameProperty', 'ObjectProperty', 'ByteProperty', 'StructProperty',
    'ArrayProperty', 'MapProperty', 'DelegateProperty', 'InterfaceProperty',
}


# ─── Property Entry ──────────────────────────────────────────────────────────

class UE3Property:
    """Represents a single serialized property."""
    __slots__ = ('name', 'type_name', 'size', 'array_index', 'value_offset',
                 'value_bytes', 'struct_name', 'header_offset', 'total_size')

    def __init__(self):
        self.name = ''
        self.type_name = ''
        self.size = 0
        self.array_index = 0
        self.value_offset = 0     # absolute offset in package data
        self.value_bytes = b''
        self.struct_name = None   # for StructProperty
        self.header_offset = 0    # absolute offset of property header start
        self.total_size = 0       # total bytes consumed (header + value)

    @property
    def int_value(self):
        if len(self.value_bytes) >= 4:
            return struct.unpack_from('<i', self.value_bytes, 0)[0]
        return 0

    @property
    def float_value(self):
        if len(self.value_bytes) >= 4:
            return struct.unpack_from('<f', self.value_bytes, 0)[0]
        return 0.0

    @property
    def bool_value(self):
        return self.array_index != 0

    def __repr__(self):
        if self.type_name == 'FloatProperty':
            return f'{self.name} = {self.float_value:.4f} (float)'
        elif self.type_name == 'IntProperty':
            return f'{self.name} = {self.int_value} (int)'
        elif self.type_name == 'BoolProperty':
            return f'{self.name} = {self.bool_value} (bool)'
        else:
            return f'{self.name} ({self.type_name}, {self.size} bytes)'


# ─── Property Reader ─────────────────────────────────────────────────────────

def read_properties(pkg, export):
    """Read all serialized properties from an export's data.
    Returns a list of UE3Property objects.
    """
    data = pkg._virtual_data
    base_offset = export.serial_offset

    # Skip the object's net index and other preamble
    # UE3 objects typically start with: net_index (i32) for networked objects
    # For non-class objects, properties start after a small preamble
    offset = base_offset

    # Skip net index if present (common for actors)
    # We detect property start by looking for valid name+type pattern
    offset = _find_property_start(pkg, data, offset, export.serial_size)
    if offset < 0:
        return []

    properties = []
    end_offset = base_offset + export.serial_size

    while offset < end_offset:
        prop, offset = _read_single_property(pkg, data, offset, end_offset)
        if prop is None:
            break  # hit 'None' terminator or error
        properties.append(prop)

    return properties


def _find_property_start(pkg, data, base_offset, serial_size):
    """Find where properties begin in the export data.
    Properties start with a valid name index that resolves to a known property name,
    followed by a valid type name.
    """
    # Try common preamble sizes: 0, 4, 8, 12, 28, 32
    for skip in (0, 4, 8, 12, 16, 28, 32, 36):
        offset = base_offset + skip
        if offset + 8 > base_offset + serial_size:
            continue
        # Read potential name index
        name_idx = struct.unpack_from('<i', data, offset)[0]
        if 0 <= name_idx < len(pkg.names):
            name = pkg.names[name_idx].name
            if name == 'None':
                # Properties section is empty (just 'None' terminator)
                return offset
            # Check if next field (after name_number) is a valid type
            if offset + 16 <= base_offset + serial_size:
                type_idx = struct.unpack_from('<i', data, offset + 8)[0]
                if 0 <= type_idx < len(pkg.names):
                    type_name = pkg.names[type_idx].name
                    if type_name in PROP_TYPES:
                        return offset
    return -1


def _read_single_property(pkg, data, offset, end_offset):
    """Read a single property. Returns (UE3Property, new_offset) or (None, offset) on termination."""
    if offset + 8 > end_offset:
        return None, offset

    header_start = offset
    prop = UE3Property()

    # Property name (name_index + number)
    name_idx, offset = read_i32(data, offset)
    _name_num, offset = read_i32(data, offset)

    if name_idx < 0 or name_idx >= len(pkg.names):
        return None, offset

    prop.name = pkg.names[name_idx].name

    # Check for 'None' terminator
    if prop.name == 'None':
        return None, offset

    # Property type (name_index + number)
    if offset + 8 > end_offset:
        return None, offset
    type_idx, offset = read_i32(data, offset)
    _type_num, offset = read_i32(data, offset)

    if type_idx < 0 or type_idx >= len(pkg.names):
        return None, offset

    prop.type_name = pkg.names[type_idx].name

    # Size
    if offset + 4 > end_offset:
        return None, offset
    prop.size, offset = read_i32(data, offset)

    # Array index
    if offset + 4 > end_offset:
        return None, offset
    prop.array_index, offset = read_i32(data, offset)

    # Type-specific header data
    if prop.type_name == 'StructProperty':
        # Struct name (name_index + number)
        if offset + 8 > end_offset:
            return None, offset
        struct_name_idx, offset = read_i32(data, offset)
        _struct_num, offset = read_i32(data, offset)
        if 0 <= struct_name_idx < len(pkg.names):
            prop.struct_name = pkg.names[struct_name_idx].name

    elif prop.type_name == 'BoolProperty':
        # Bool value is stored differently - it's in the data area
        # but for v727 it's typically a u32 after the header
        if offset + 4 > end_offset:
            return None, offset
        bool_val, offset = read_u32(data, offset)
        prop.value_offset = offset - 4
        prop.value_bytes = data[offset - 4:offset]
        prop.array_index = bool_val  # store bool value here
        prop.header_offset = header_start
        prop.total_size = offset - header_start
        return prop, offset

    elif prop.type_name == 'ByteProperty':
        # Enum name (name_index + number) for v633+
        if offset + 8 > end_offset:
            return None, offset
        _enum_idx, offset = read_i32(data, offset)
        _enum_num, offset = read_i32(data, offset)

    # Value data
    prop.value_offset = offset
    if prop.size < 0 or offset + prop.size > end_offset:
        return None, offset
    prop.value_bytes = data[offset:offset + prop.size]
    offset += prop.size

    prop.header_offset = header_start
    prop.total_size = offset - header_start
    return prop, offset


# ─── Property Search ──────────────────────────────────────────────────────────

def find_property(properties, name):
    """Find a property by name in a property list."""
    for prop in properties:
        if prop.name == name:
            return prop
    return None


def find_properties(properties, name):
    """Find all properties with the given name (for arrays stored as repeated entries)."""
    return [p for p in properties if p.name == name]


def find_float_properties(properties):
    """Get all FloatProperty entries."""
    return [p for p in properties if p.type_name == 'FloatProperty']


def find_int_properties(properties):
    """Get all IntProperty entries."""
    return [p for p in properties if p.type_name == 'IntProperty']


# ─── Property Patching ────────────────────────────────────────────────────────

def patch_float_property(pkg, prop, new_value):
    """Patch a FloatProperty's value in the package data."""
    if prop.type_name != 'FloatProperty':
        raise ValueError(f'Cannot patch {prop.type_name} as float')
    pkg.patch_float(prop.value_offset, new_value)
    prop.value_bytes = struct.pack('<f', new_value)


def patch_int_property(pkg, prop, new_value):
    """Patch an IntProperty's value in the package data."""
    if prop.type_name != 'IntProperty':
        raise ValueError(f'Cannot patch {prop.type_name} as int')
    pkg.patch_int32(prop.value_offset, new_value)
    prop.value_bytes = struct.pack('<i', new_value)


def patch_property_by_name(pkg, export, prop_name, new_value):
    """Find and patch a named property in an export.
    Automatically detects int vs float based on property type.
    Returns True if found and patched.
    """
    properties = read_properties(pkg, export)
    prop = find_property(properties, prop_name)
    if prop is None:
        return False
    if prop.type_name == 'FloatProperty':
        patch_float_property(pkg, prop, float(new_value))
        return True
    elif prop.type_name == 'IntProperty':
        patch_int_property(pkg, prop, int(new_value))
        return True
    return False


# ─── Scanning ─────────────────────────────────────────────────────────────────

def scan_export_properties(pkg, export):
    """Scan an export and return a dict of property_name -> (type, value)."""
    properties = read_properties(pkg, export)
    result = {}
    for prop in properties:
        if prop.type_name == 'FloatProperty':
            result[prop.name] = ('float', prop.float_value)
        elif prop.type_name == 'IntProperty':
            result[prop.name] = ('int', prop.int_value)
        elif prop.type_name == 'BoolProperty':
            result[prop.name] = ('bool', prop.bool_value)
        elif prop.type_name == 'NameProperty' and len(prop.value_bytes) >= 4:
            name_ref = struct.unpack_from('<i', prop.value_bytes, 0)[0]
            if 0 <= name_ref < len(pkg.names):
                result[prop.name] = ('name', pkg.names[name_ref].name)
            else:
                result[prop.name] = ('name', f'<idx:{name_ref}>')
        elif prop.type_name == 'ObjectProperty' and len(prop.value_bytes) >= 4:
            obj_ref = struct.unpack_from('<i', prop.value_bytes, 0)[0]
            result[prop.name] = ('object', pkg.resolve_object_ref(obj_ref))
        else:
            result[prop.name] = (prop.type_name, f'<{prop.size} bytes>')
    return result


def scan_package_for_property(pkg, prop_name, class_filter=None):
    """Scan all exports in a package for a specific property name.
    Returns list of (export, property) tuples.
    """
    results = []
    for exp in pkg.exports:
        if exp.serial_size <= 0:
            continue
        if class_filter:
            cls_name = pkg.resolve_class_name(exp)
            if cls_name != class_filter:
                continue
        try:
            properties = read_properties(pkg, exp)
            for prop in properties:
                if prop.name == prop_name:
                    results.append((exp, prop))
        except Exception:
            continue
    return results
