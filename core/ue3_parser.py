"""
The War In Columbia — UE3 Package Parser
==========================================
Reads and writes Unreal Engine 3 cooked packages (.xxx) for BioShock Infinite.

Package format (version 727, licensee 75):
  - Header with magic 0x9E2A83C1
  - Name Table: array of FName entries (string + flags)
  - Import Table: array of FObjectImport entries
  - Export Table: array of FObjectExport entries
  - Export serial data: raw bytes for each export object

This parser supports:
  - Full read of package structure (names, imports, exports)
  - Property deserialization for export objects
  - In-place value patching (modify property values without restructuring)
  - Export duplication (append cloned exports for spawn scaling)
  - Full package rewrite with updated headers
"""

import struct
import os
from pathlib import Path
from .lzo import decompress as lzo_decompress, compress as lzo_compress


# ─── Constants ────────────────────────────────────────────────────────────────

UE3_MAGIC = 0x9E2A83C1
BIOSHOCK_INF_VERSION = 727
BIOSHOCK_INF_LICENSEE = 75


# ─── Low-level read helpers ───────────────────────────────────────────────────

def read_u8(data, offset):
    return struct.unpack_from('<B', data, offset)[0], offset + 1

def read_u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0], offset + 2

def read_i32(data, offset):
    return struct.unpack_from('<i', data, offset)[0], offset + 4

def read_u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0], offset + 4

def read_i64(data, offset):
    return struct.unpack_from('<q', data, offset)[0], offset + 8

def read_u64(data, offset):
    return struct.unpack_from('<Q', data, offset)[0], offset + 8

def read_f32(data, offset):
    return struct.unpack_from('<f', data, offset)[0], offset + 4

def read_guid(data, offset):
    return data[offset:offset+16], offset + 16

def read_fstring(data, offset):
    """Read a length-prefixed string (UE3 FString format).
    Length is i32. If positive: ASCII (length includes null).
    If negative: UTF-16LE (abs(length) chars including null).
    """
    length, offset = read_i32(data, offset)
    if length == 0:
        return '', offset
    if length > 0:
        # ASCII / Latin-1
        s = data[offset:offset + length - 1].decode('latin-1')
        offset += length
    else:
        # UTF-16LE
        char_count = -length
        s = data[offset:offset + (char_count - 1) * 2].decode('utf-16-le')
        offset += char_count * 2
    return s, offset


def write_u8(value):
    return struct.pack('<B', value)

def write_u16(value):
    return struct.pack('<H', value)

def write_i32(value):
    return struct.pack('<i', value)

def write_u32(value):
    return struct.pack('<I', value)

def write_i64(value):
    return struct.pack('<q', value)

def write_u64(value):
    return struct.pack('<Q', value)

def write_f32(value):
    return struct.pack('<f', value)

def write_fstring(s):
    """Write a length-prefixed ASCII string."""
    if not s:
        return write_i32(0)
    encoded = s.encode('latin-1') + b'\x00'
    return write_i32(len(encoded)) + encoded


# ─── Name Table Entry ─────────────────────────────────────────────────────────

class FNameEntry:
    __slots__ = ('name', 'hash1', 'hash2')

    def __init__(self, name='', hash1=0, hash2=0):
        self.name = name
        self.hash1 = hash1
        self.hash2 = hash2

    def __repr__(self):
        return f'FNameEntry({self.name!r})'


def read_name_entry(data, offset):
    """Read a single name table entry (BioShock Infinite format).
    Format: i32 strlen + char[strlen] null-terminated string + u32 hash1 + u32 hash2
    """
    name, offset = read_fstring(data, offset)
    hash1, offset = read_u32(data, offset)
    hash2, offset = read_u32(data, offset)
    return FNameEntry(name, hash1, hash2), offset


# ─── Import Table Entry ───────────────────────────────────────────────────────

class FObjectImport:
    __slots__ = ('class_package', 'class_name', 'package_index', 'object_name')

    def __init__(self):
        self.class_package = 0  # name index
        self.class_name = 0     # name index
        self.package_index = 0  # i32 (outer reference)
        self.object_name = 0    # name index

    def __repr__(self):
        return (f'FObjectImport(pkg={self.class_package}, cls={self.class_name}, '
                f'outer={self.package_index}, name={self.object_name})')


def read_import_entry(data, offset):
    """Read a single import table entry."""
    imp = FObjectImport()
    imp.class_package, offset = read_i32(data, offset)
    _num1, offset = read_i32(data, offset)  # class_package number (always 0)
    imp.class_name, offset = read_i32(data, offset)
    _num2, offset = read_i32(data, offset)  # class_name number (always 0)
    imp.package_index, offset = read_i32(data, offset)
    imp.object_name, offset = read_i32(data, offset)
    _num3, offset = read_i32(data, offset)  # object_name number (always 0)
    return imp, offset


# ─── Export Table Entry ───────────────────────────────────────────────────────

class FObjectExport:
    __slots__ = ('class_index', 'super_index', 'outer_index', 'object_name',
                 'object_name_number', 'archetype', 'object_flags',
                 'serial_size', 'serial_offset', 'export_flags',
                 'net_object_count', '_raw_bytes', 'index')

    def __init__(self):
        self.class_index = 0
        self.super_index = 0
        self.outer_index = 0
        self.object_name = 0
        self.object_name_number = 0
        self.archetype = 0
        self.object_flags = 0
        self.serial_size = 0
        self.serial_offset = 0
        self.export_flags = 0
        self.net_object_count = 0
        self._raw_bytes = b''
        self.index = 0

    def __repr__(self):
        return (f'FObjectExport(name={self.object_name}, cls={self.class_index}, '
                f'outer={self.outer_index}, size={self.serial_size}, '
                f'offset={self.serial_offset})')


def read_export_entry(data, offset):
    """Read a single export table entry for BioShock Infinite (v727).

    The fixed prefix is 44 bytes (6xi32 + u64 + 2xi32 + u32), followed by the
    GenerationNetObjectCount TArray (i32 count + count*i32). MOST entries stop
    there (48 bytes when count==0). However, FORCED-EXPORT entries additionally
    serialize a 16-byte package GUID + 4-byte PackageFlags + 4-byte trailer
    (28 extra bytes total => 76-byte entry). Presence of that block is NOT
    encoded in a single reliable bit across this build, so callers must resync
    against the next valid header (see UE3Package._parse_exports).

    This function only reads the FIXED PREFIX + net-count and returns the offset
    just past the net-count array. The variable GUID tail is handled by the
    adaptive parser so it can validate against the following entry.
    """
    start = offset
    exp = FObjectExport()
    exp.class_index, offset = read_i32(data, offset)
    exp.super_index, offset = read_i32(data, offset)
    exp.outer_index, offset = read_i32(data, offset)
    exp.object_name, offset = read_i32(data, offset)
    exp.object_name_number, offset = read_i32(data, offset)
    exp.archetype, offset = read_i32(data, offset)
    exp.object_flags, offset = read_u64(data, offset)
    exp.serial_size, offset = read_i32(data, offset)
    exp.serial_offset, offset = read_i32(data, offset)
    exp.export_flags, offset = read_u32(data, offset)
    exp.net_object_count, offset = read_i32(data, offset)
    # Skip the net-object-count array values (count entries of i32).
    if 0 <= exp.net_object_count <= 16:
        offset += exp.net_object_count * 4
    exp._raw_bytes = data[start:offset]
    return exp, offset


EXPORT_ENTRY_SIZE = 48  # Common (non-forced-export) entry size for v727

# Extra bytes appended to FORCED-EXPORT entries: GUID(16) + PackageFlags(4)
# + trailer(4). Confirmed empirically across S_TWN_P / *_Game packages.
FORCED_EXPORT_TAIL = 24


# ─── Package Header ──────────────────────────────────────────────────────────

class UE3PackageHeader:
    __slots__ = ('magic', 'file_version', 'licensee_version', 'header_size',
                 'folder_name', 'package_flags', 'name_count', 'name_offset',
                 'export_count', 'export_offset', 'import_count', 'import_offset',
                 'depends_offset', 'guid', 'generations', 'engine_version',
                 'cooker_version', 'compression_flags', 'compressed_chunks',
                 'package_source', '_header_end_offset', '_raw_data',
                 '_compression_flags_offset', '_chunk_count_offset')

    def __init__(self):
        self.magic = UE3_MAGIC
        self.file_version = BIOSHOCK_INF_VERSION
        self.licensee_version = BIOSHOCK_INF_LICENSEE
        self.header_size = 0
        self.folder_name = ''
        self.package_flags = 0
        self.name_count = 0
        self.name_offset = 0
        self.export_count = 0
        self.export_offset = 0
        self.import_count = 0
        self.import_offset = 0
        self.depends_offset = 0
        self.guid = b'\x00' * 16
        self.generations = []
        self.engine_version = 0
        self.cooker_version = 0
        self.compression_flags = 0
        self.compressed_chunks = []
        self.package_source = 0
        self._header_end_offset = 0
        self._raw_data = b''


# ─── Package Class ────────────────────────────────────────────────────────────

class UE3Package:
    """Full representation of a UE3 package file."""

    def __init__(self):
        self.header = UE3PackageHeader()
        self.names = []      # list of FNameEntry
        self.imports = []    # list of FObjectImport
        self.exports = []    # list of FObjectExport
        self.raw_data = b''  # full file bytes (compressed on disk)
        self._virtual_data = b''  # decompressed virtual buffer
        self.filepath = None

    @classmethod
    def from_file(cls, filepath):
        """Load and parse a UE3 package from disk."""
        filepath = Path(filepath)
        with open(filepath, 'rb') as f:
            data = f.read()
        pkg = cls()
        pkg.filepath = filepath
        pkg.raw_data = data
        pkg._parse_header(data)
        # If compressed, decompress to get the virtual buffer for table parsing
        if pkg.header.compressed_chunks:
            pkg._virtual_data = pkg._decompress_full(data)
        else:
            pkg._virtual_data = data
        pkg._parse_names(pkg._virtual_data)
        pkg._parse_imports(pkg._virtual_data)
        pkg._parse_exports(pkg._virtual_data)
        return pkg

    def _decompress_chunk(self, data, chunk_info):
        """Decompress a single chunk (may contain multiple LZO blocks)."""
        uc_off, uc_size, c_off, c_size = chunk_info
        comp_data = data[c_off:c_off + c_size]
        coff = 0
        _magic = struct.unpack_from('<I', comp_data, coff)[0]; coff += 4
        block_size = struct.unpack_from('<I', comp_data, coff)[0]; coff += 4
        _total_comp = struct.unpack_from('<i', comp_data, coff)[0]; coff += 4
        total_uncomp = struct.unpack_from('<i', comp_data, coff)[0]; coff += 4
        num_blocks = (total_uncomp + block_size - 1) // block_size

        blocks = []
        for _ in range(num_blocks):
            bc = struct.unpack_from('<i', comp_data, coff)[0]; coff += 4
            bu = struct.unpack_from('<i', comp_data, coff)[0]; coff += 4
            blocks.append((bc, bu))

        result = bytearray()
        for bc, bu in blocks:
            block_data = comp_data[coff:coff + bc]
            coff += bc
            dec = lzo_decompress(bytes(block_data), bu)
            result.extend(dec)
            if len(dec) < bu:
                result.extend(b'\x00' * (bu - len(dec)))
        return bytes(result[:uc_size])

    def _decompress_full(self, data):
        """Decompress all chunks and build the full virtual uncompressed buffer."""
        chunks = self.header.compressed_chunks
        if not chunks:
            return data
        # Calculate total virtual size
        last = chunks[-1]
        total_size = last[0] + last[1]
        virtual = bytearray(total_size)
        # Copy uncompressed header portion
        header_end = chunks[0][0]
        virtual[0:header_end] = data[0:header_end]
        # Decompress each chunk
        for chunk_info in chunks:
            uc_off, uc_size = chunk_info[0], chunk_info[1]
            dec = self._decompress_chunk(data, chunk_info)
            virtual[uc_off:uc_off + uc_size] = dec[:uc_size]
        return bytes(virtual)

    def _parse_header(self, data):
        """Parse the package header (BioShock Infinite v727 format)."""
        h = self.header
        h._raw_data = data
        offset = 0

        magic, offset = read_u32(data, offset)
        if magic != UE3_MAGIC:
            raise ValueError(f'Invalid UE3 magic: 0x{magic:08X} (expected 0x{UE3_MAGIC:08X})')
        h.magic = magic

        h.file_version, offset = read_u16(data, offset)
        h.licensee_version, offset = read_u16(data, offset)
        h.header_size, offset = read_i32(data, offset)
        # Unknown field (present in BioShock Infinite cooked packages)
        _unknown, offset = read_i32(data, offset)
        h.folder_name, offset = read_fstring(data, offset)
        h.package_flags, offset = read_u32(data, offset)
        h.name_count, offset = read_i32(data, offset)
        h.name_offset, offset = read_i32(data, offset)
        h.export_count, offset = read_i32(data, offset)
        h.export_offset, offset = read_i32(data, offset)
        h.import_count, offset = read_i32(data, offset)
        h.import_offset, offset = read_i32(data, offset)
        h.depends_offset, offset = read_i32(data, offset)

        # Skip one field before GUID
        _skip, offset = read_i32(data, offset)

        h.guid, offset = read_guid(data, offset)

        # Generations
        gen_count, offset = read_i32(data, offset)
        h.generations = []
        for _ in range(gen_count):
            gen_exports, offset = read_i32(data, offset)
            gen_names, offset = read_i32(data, offset)
            gen_net, offset = read_i32(data, offset)
            h.generations.append((gen_exports, gen_names, gen_net))

        h.engine_version, offset = read_i32(data, offset)
        h.cooker_version, offset = read_i32(data, offset)
        h._compression_flags_offset = offset
        h.compression_flags, offset = read_u32(data, offset)

        # Compressed chunks
        h._chunk_count_offset = offset
        chunk_count, offset = read_i32(data, offset)
        h.compressed_chunks = []
        for _ in range(chunk_count):
            uncompressed_offset, offset = read_i32(data, offset)
            uncompressed_size, offset = read_i32(data, offset)
            compressed_offset, offset = read_i32(data, offset)
            compressed_size, offset = read_i32(data, offset)
            h.compressed_chunks.append((uncompressed_offset, uncompressed_size,
                                         compressed_offset, compressed_size))

        h._header_end_offset = offset

    def _parse_names(self, data):
        """Parse the name table."""
        offset = self.header.name_offset
        self.names = []
        for _ in range(self.header.name_count):
            entry, offset = read_name_entry(data, offset)
            self.names.append(entry)

    def _parse_imports(self, data):
        """Parse the import table."""
        offset = self.header.import_offset
        self.imports = []
        for _ in range(self.header.import_count):
            imp, offset = read_import_entry(data, offset)
            self.imports.append(imp)

    def _export_header_valid(self, data, offset):
        """Heuristic: do the bytes at `offset` look like a valid export header?
        Used to resync across the variable-length forced-export GUID tail."""
        if offset < 0 or offset + 44 > len(data):
            return False
        nc = self.header.name_count
        ic = self.header.import_count
        ec = self.header.export_count
        try:
            ci, si, oi, nm, num, arch, fl0, fl1, ssz, soff, ef = \
                struct.unpack_from('<11i', data, offset)
        except struct.error:
            return False
        return (-ic <= ci <= ec and -ic <= si <= ec and -ic <= oi <= ec
                and 0 <= nm < nc and -ic <= arch <= ec
                and ssz >= 0 and 0 <= soff <= len(data)
                and 0 <= ef < 0x10000)

    def _parse_exports(self, data):
        """Parse the export table with adaptive resync.

        BioShock Infinite export entries are 48 bytes normally, but FORCED-EXPORT
        entries append a 24-byte GUID/flags tail. We detect the tail by checking
        whether the next entry's header validates immediately after the net-count
        array; if not, we skip the forced-export tail and re-validate.
        """
        offset = self.header.export_offset
        self.exports = []
        count = self.header.export_count
        for i in range(count):
            start = offset
            exp, offset = read_export_entry(data, offset)
            exp.index = i
            is_last = (i == count - 1)
            if not is_last:
                if self._export_header_valid(data, offset):
                    pass  # plain entry, next header follows directly
                elif self._export_header_valid(data, offset + FORCED_EXPORT_TAIL):
                    offset += FORCED_EXPORT_TAIL  # forced-export GUID tail
                # else: leave as-is; resync failed but keep going best-effort
                exp._raw_bytes = data[start:offset]
            self.exports.append(exp)

    # ─── Name resolution ──────────────────────────────────────────────────

    def get_name(self, index):
        """Get string name by name table index."""
        if 0 <= index < len(self.names):
            return self.names[index].name
        return f'<invalid:{index}>'

    def find_name_index(self, name):
        """Find the index of a name in the name table. Returns -1 if not found."""
        for i, entry in enumerate(self.names):
            if entry.name == name:
                return i
        return -1

    # ─── Object reference resolution ─────────────────────────────────────

    def resolve_object_ref(self, ref_index):
        """Resolve an object reference index to a name string.
        Positive: export index (1-based)
        Negative: import index (negated, 1-based)
        Zero: null reference
        """
        if ref_index == 0:
            return 'None'
        elif ref_index > 0:
            idx = ref_index - 1
            if idx >= len(self.exports):
                return f'<export:{ref_index}>'
            exp = self.exports[idx]
            return self.get_name(exp.object_name)
        else:
            idx = -ref_index - 1
            if idx >= len(self.imports):
                return f'<import:{ref_index}>'
            imp = self.imports[idx]
            return self.get_name(imp.object_name)

    def resolve_class_name(self, export):
        """Get the class name for an export."""
        return self.resolve_object_ref(export.class_index)

    def resolve_full_path(self, ref_index):
        """Resolve an object reference to its full dotted path."""
        if ref_index == 0:
            return 'None'
        parts = []
        current = ref_index
        seen = set()
        while current != 0 and current not in seen:
            seen.add(current)
            if current > 0:
                exp = self.exports[current - 1]
                parts.append(self.get_name(exp.object_name))
                current = exp.outer_index
            else:
                imp = self.imports[-current - 1]
                parts.append(self.get_name(imp.object_name))
                current = imp.package_index
        parts.reverse()
        return '.'.join(parts)

    # ─── Export serial data ───────────────────────────────────────────────

    def get_export_data(self, export):
        """Get the raw serial data bytes for an export."""
        if export.serial_size <= 0:
            return b''
        return self._virtual_data[export.serial_offset:export.serial_offset + export.serial_size]

    # ─── Export search ────────────────────────────────────────────────────

    def find_exports_by_class(self, class_name):
        """Find all exports with the given class name."""
        results = []
        for exp in self.exports:
            if self.resolve_class_name(exp) == class_name:
                results.append(exp)
        return results

    def find_exports_by_name(self, name):
        """Find all exports with the given object name."""
        results = []
        target_idx = self.find_name_index(name)
        if target_idx < 0:
            return results
        for exp in self.exports:
            if exp.object_name == target_idx:
                results.append(exp)
        return results

    def find_exports_by_name_substring(self, substring):
        """Find all exports whose object name contains the substring."""
        results = []
        sub_lower = substring.lower()
        for exp in self.exports:
            name = self.get_name(exp.object_name)
            if sub_lower in name.lower():
                results.append(exp)
        return results

    # ─── Summary ──────────────────────────────────────────────────────────

    def summary(self):
        """Return a brief summary of the package."""
        h = self.header
        return (f'UE3 Package: {self.filepath.name if self.filepath else "<memory>"}\n'
                f'  Version: {h.file_version}, Licensee: {h.licensee_version}\n'
                f'  Names: {h.name_count}, Imports: {h.import_count}, '
                f'Exports: {h.export_count}\n'
                f'  Compression: {"Yes" if h.compression_flags else "No"}\n'
                f'  File size: {len(self.raw_data):,} bytes')

    # ─── In-place byte patching ───────────────────────────────────────────

    def patch_bytes(self, offset, new_bytes):
        """Patch bytes at offset in the virtual (decompressed) data."""
        data = bytearray(self._virtual_data)
        data[offset:offset + len(new_bytes)] = new_bytes
        self._virtual_data = bytes(data)

    def patch_float(self, offset, value):
        """Patch a 32-bit float at the given offset in virtual data."""
        self.patch_bytes(offset, write_f32(value))

    def patch_int32(self, offset, value):
        """Patch a 32-bit integer at the given offset in virtual data."""
        self.patch_bytes(offset, write_i32(value))

    # ─── Save ─────────────────────────────────────────────────────────────

    def save(self, filepath=None):
        """Save the package to disk, re-compressing with LZO if originally compressed."""
        if filepath is None:
            filepath = self.filepath
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        h = self.header
        if not h.compressed_chunks:
            # Package was never compressed — write virtual data directly
            with open(filepath, 'wb') as f:
                f.write(self._virtual_data)
            return

        # Re-compress using the original chunk layout
        BLOCK_SIZE = 0x20000  # 131072 bytes per block (UE3 default)
        virtual = self._virtual_data
        header_end = h.compressed_chunks[0][0]  # uncompressed offset of first chunk

        # Start output with the header portion (will patch offsets later)
        out = bytearray(virtual[:header_end])

        # Build new chunk table
        new_chunks = []
        for chunk_info in h.compressed_chunks:
            uc_off, uc_size = chunk_info[0], chunk_info[1]
            chunk_data = virtual[uc_off:uc_off + uc_size]

            # Split into blocks and compress each
            num_blocks = (uc_size + BLOCK_SIZE - 1) // BLOCK_SIZE
            compressed_blocks = []
            for b in range(num_blocks):
                bstart = b * BLOCK_SIZE
                bend = min(bstart + BLOCK_SIZE, uc_size)
                block = chunk_data[bstart:bend]
                comp = lzo_compress(block)
                compressed_blocks.append((comp, len(block)))

            # Build chunk header
            total_uncomp = uc_size
            total_comp = sum(len(c) for c, _ in compressed_blocks)
            # Chunk sub-header: magic(4) + block_size(4) + total_comp(4) + total_uncomp(4)
            # + num_blocks * (comp_size(4) + uncomp_size(4))
            chunk_header_size = 16 + num_blocks * 8
            total_comp_with_header = chunk_header_size + total_comp

            c_off = len(out)
            # Write chunk sub-header
            out.extend(struct.pack('<I', UE3_MAGIC))
            out.extend(struct.pack('<I', BLOCK_SIZE))
            out.extend(struct.pack('<i', total_comp_with_header))
            out.extend(struct.pack('<i', total_uncomp))
            # Write block entries
            for comp_data, uncomp_size in compressed_blocks:
                out.extend(struct.pack('<ii', len(comp_data), uncomp_size))
            # Write compressed block data
            for comp_data, _ in compressed_blocks:
                out.extend(comp_data)

            new_chunks.append((uc_off, uc_size, c_off, total_comp_with_header))

        # Patch the chunk table in the header
        # Rewrite compression_flags (keep original LZO flag)
        struct.pack_into('<I', out, h._compression_flags_offset, h.compression_flags)
        # Rewrite chunk count
        struct.pack_into('<i', out, h._chunk_count_offset, len(new_chunks))
        # Rewrite chunk entries (each is 4 x i32 = 16 bytes)
        chunk_table_offset = h._chunk_count_offset + 4
        for i, (uc_off, uc_size, c_off, c_size) in enumerate(new_chunks):
            off = chunk_table_offset + i * 16
            struct.pack_into('<iiii', out, off, uc_off, uc_size, c_off, c_size)

        with open(filepath, 'wb') as f:
            f.write(out)
