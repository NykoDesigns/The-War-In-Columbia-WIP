"""
Decompress a BioShock Infinite .xxx UE3 compressed package.
UE3 packages with CompressionFlags != 0 have a CompressedChunks table in the header.
Each chunk is individually compressed with ZLIB (flag=2) or LZO (flag=1).
"""
import struct, sys, zlib, os

def read_u32(f):
    return struct.unpack('<I', f.read(4))[0]

def read_u16(f):
    return struct.unpack('<H', f.read(2))[0]

def main():
    if len(sys.argv) < 2:
        print("Usage: decompress_pkg.py <input.xxx> [output.upk]")
        return
    
    inpath = sys.argv[1]
    outpath = sys.argv[2] if len(sys.argv) > 2 else inpath.replace('.xxx', '_decomp.upk')
    
    with open(inpath, 'rb') as f:
        # UE3 Package Header
        tag = read_u32(f)  # Magic: 0x9E2A83C1
        if tag != 0x9E2A83C1:
            print(f"ERROR: Not a UE package (tag=0x{tag:08X})")
            return
        
        file_version = read_u16(f)
        licensee_version = read_u16(f)
        header_size = read_u32(f)  # Total size of uncompressed data
        
        print(f"Package tag: 0x{tag:08X}")
        print(f"Version: {file_version}/{licensee_version}")
        print(f"Header/Total Size: {header_size}")
        
        # Read folder name (FString)
        folder_len = read_u32(f)
        if folder_len > 0 and folder_len < 1024:
            folder = f.read(folder_len)
            print(f"Folder: {folder}")
        elif folder_len == 0:
            pass
        else:
            # Negative = Unicode
            abs_len = abs(struct.unpack('<i', struct.pack('<I', folder_len))[0])
            if abs_len < 1024:
                folder = f.read(abs_len * 2)
            else:
                print(f"WARNING: unusual folder_len: {folder_len}")
                f.seek(f.tell() - 4)  # back up
        
        package_flags = read_u32(f)
        print(f"Package flags: 0x{package_flags:08X}")
        
        names_count = read_u32(f)
        names_offset = read_u32(f)
        exports_count = read_u32(f)
        exports_offset = read_u32(f)
        imports_count = read_u32(f)
        imports_offset = read_u32(f)
        
        print(f"Names: {names_count} @ 0x{names_offset:X}")
        print(f"Exports: {exports_count} @ 0x{exports_offset:X}")
        print(f"Imports: {imports_count} @ 0x{imports_offset:X}")
        
        depends_offset = read_u32(f)
        depends_count = read_u32(f) if file_version >= 415 else 0
        
        # Skip to GUID
        guid = f.read(16)
        
        # Generations
        gen_count = read_u32(f)
        print(f"Generations: {gen_count}")
        for i in range(gen_count):
            gen_exports = read_u32(f)
            gen_names = read_u32(f)
            gen_net = read_u32(f)
        
        # Engine version
        engine_version = read_u32(f)
        cooker_version = read_u32(f)
        print(f"Engine: {engine_version}, Cooker: {cooker_version}")
        
        # Compression flags
        compression_flags = read_u32(f)
        print(f"CompressionFlags: {compression_flags}")
        
        # Compressed chunks array
        num_chunks = read_u32(f)
        print(f"CompressedChunks: {num_chunks}")
        
        chunks = []
        for i in range(num_chunks):
            uncomp_offset = read_u32(f)
            uncomp_size = read_u32(f)
            comp_offset = read_u32(f)
            comp_size = read_u32(f)
            chunks.append((uncomp_offset, uncomp_size, comp_offset, comp_size))
            if i < 5:
                print(f"  Chunk {i}: uncomp@0x{uncomp_offset:X} sz={uncomp_size}, comp@0x{comp_offset:X} sz={comp_size}")
        
        if num_chunks > 5:
            print(f"  ... ({num_chunks - 5} more chunks)")
        
        # Now decompress
        # The uncompressed data starts at offset 0 with the header (which is already uncompressed)
        # and the chunks cover the rest of the file
        
        # First, read header up to the first chunk's uncompressed offset
        if num_chunks == 0:
            print("No compressed chunks! Package might not be compressed.")
            return
        
        first_chunk_offset = chunks[0][0]  # uncompressed offset of first chunk
        total_uncomp = max(c[0] + c[1] for c in chunks)
        print(f"First chunk starts at uncompressed offset: 0x{first_chunk_offset:X}")
        print(f"Total uncompressed size: {total_uncomp}")
        
        # Read the header (uncompressed part before chunks)
        f.seek(0)
        header_data = f.read(first_chunk_offset)
        
        # Decompress each chunk
        output = bytearray(total_uncomp)
        output[:first_chunk_offset] = header_data
        
        for i, (uncomp_off, uncomp_sz, comp_off, comp_sz) in enumerate(chunks):
            f.seek(comp_off)
            comp_data = f.read(comp_sz)
            
            # UE3 compressed blocks: first a FCompressedChunkInfo header
            # Each compressed chunk can have multiple sub-blocks
            # Header: Magic (4), BlockSize (4), TotalCompressedSize (4), TotalUncompressedSize (4)
            # Then pairs of (CompressedSize, UncompressedSize) followed by data
            
            pos = 0
            out_pos = 0
            
            # Read chunk header
            magic = struct.unpack_from('<I', comp_data, pos)[0]; pos += 4
            block_size = struct.unpack_from('<I', comp_data, pos)[0]; pos += 4
            total_comp = struct.unpack_from('<I', comp_data, pos)[0]; pos += 4
            total_uncomp_check = struct.unpack_from('<I', comp_data, pos)[0]; pos += 4
            
            if magic != 0x9E2A83C1:
                print(f"  Chunk {i}: unexpected magic 0x{magic:08X}")
                continue
            
            # Calculate number of blocks
            num_blocks = (total_uncomp_check + block_size - 1) // block_size
            
            # Read block size pairs
            blocks = []
            for b in range(num_blocks):
                b_comp = struct.unpack_from('<I', comp_data, pos)[0]; pos += 4
                b_uncomp = struct.unpack_from('<I', comp_data, pos)[0]; pos += 4
                blocks.append((b_comp, b_uncomp))
            
            # Decompress blocks
            for b_comp, b_uncomp in blocks:
                block_data = comp_data[pos:pos + b_comp]
                pos += b_comp
                
                if compression_flags == 2:  # ZLIB
                    decompressed = zlib.decompress(block_data)
                else:
                    print(f"  Unsupported compression: {compression_flags}")
                    return
                
                if len(decompressed) != b_uncomp:
                    print(f"  WARNING: block decompressed to {len(decompressed)}, expected {b_uncomp}")
                
                output[uncomp_off + out_pos:uncomp_off + out_pos + len(decompressed)] = decompressed
                out_pos += len(decompressed)
            
            if i < 3 or i == num_chunks - 1:
                print(f"  Chunk {i}: OK ({num_blocks} blocks, {out_pos} bytes)")
    
    # Patch the header to remove compression info
    # Set CompressionFlags to 0 and CompressedChunks count to 0
    # We need to find where CompressionFlags is in the header
    # For now just write the output as-is and let UE Explorer handle it
    
    with open(outpath, 'wb') as out_f:
        out_f.write(bytes(output))
    
    print(f"\nDecompressed: {outpath} ({len(output)} bytes)")

if __name__ == '__main__':
    main()
