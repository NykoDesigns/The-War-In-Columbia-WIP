"""
Pure Python LZO1X decompression (miniLZO compatible).
Based closely on the reference miniLZO C implementation.

This implements only decompression (not compression), which is all we need
for reading compressed UE3 packages.
"""


def decompress(src, uncompressed_size):
    """Decompress LZO1X compressed data.
    
    Args:
        src: bytes/bytearray of compressed data
        uncompressed_size: expected size of decompressed output
    
    Returns:
        bytes of decompressed data
    """
    out = bytearray(uncompressed_size)
    ip = 0      # input position
    op = 0      # output position
    ip_end = len(src)

    if ip_end == 0:
        return bytes(out[:op])

    t = src[ip]; ip += 1

    if t > 17:
        # Copy (t - 17) literal bytes
        n = t - 17
        out[op:op+n] = src[ip:ip+n]
        op += n; ip += n
        # Next control byte
        t = src[ip]; ip += 1
        if t < 16:
            # M1 match after initial literals
            m_pos = op - 1 - 0x0800 - (t >> 2) - (src[ip] << 2)
            ip += 1
            out[op] = out[m_pos]; out[op+1] = out[m_pos+1]; out[op+2] = out[m_pos+2]
            op += 3
            # Trailing literals
            t = t & 3
            if t == 0:
                pass  # will get new t below
            else:
                out[op:op+t] = src[ip:ip+t]
                op += t; ip += t
                t = src[ip]; ip += 1
                # Go to main loop
                # but we need to enter the main loop with t already read
                return _main_loop(src, out, ip, op, ip_end, t, uncompressed_size)
            t = src[ip]; ip += 1
    elif t < 16:
        # First literal run: length = t + 3 (with extension for t==0)
        if t == 0:
            while ip < ip_end and src[ip] == 0:
                t += 255; ip += 1
            t += 15 + src[ip]; ip += 1
        n = t + 3
        out[op:op+n] = src[ip:ip+n]
        op += n; ip += n
        # Read next control byte
        t = src[ip]; ip += 1
        if t < 16:
            # M1 match
            m_pos = op - 1 - 0x0800 - (t >> 2) - (src[ip] << 2)
            ip += 1
            out[op] = out[m_pos]; out[op+1] = out[m_pos+1]; out[op+2] = out[m_pos+2]
            op += 3
            t = t & 3
            if t == 0:
                t = src[ip]; ip += 1
            else:
                out[op:op+t] = src[ip:ip+t]
                op += t; ip += t
                t = src[ip]; ip += 1

    return _main_loop(src, out, ip, op, ip_end, t, uncompressed_size)


def _main_loop(src, out, ip, op, ip_end, t, max_out):
    """Main LZO1X decompression loop."""
    while ip < ip_end and op < max_out:
        if t >= 64:
            # M2 match: length 3-8, offset 1-2048
            m_len = 1 + (t >> 5)
            m_off = 1 + ((t >> 2) & 7) + (src[ip] << 3)
            ip += 1
            m_pos = op - m_off
            _copy_match(out, op, m_pos, m_len, max_out)
            op += m_len
            t = t & 3

        elif t >= 32:
            # M3 match: length 2+, offset 1-16384
            m_len = t & 31
            if m_len == 0:
                # Extended length
                while ip < ip_end and src[ip] == 0:
                    m_len += 255; ip += 1
                m_len += 31 + src[ip]; ip += 1
            m_len += 2
            m_off = 1 + (src[ip] >> 2) + (src[ip+1] << 6)
            ip += 2
            m_pos = op - m_off
            _copy_match(out, op, m_pos, m_len, max_out)
            op += m_len
            t = src[ip-2] & 3

        elif t >= 16:
            # M4 match: length 2+, offset 16384+ (or EOS)
            m_len = t & 7
            if m_len == 0:
                while ip < ip_end and src[ip] == 0:
                    m_len += 255; ip += 1
                m_len += 7 + src[ip]; ip += 1
            m_len += 2
            m_off = (src[ip] >> 2) + (src[ip+1] << 6)
            ip += 2
            if m_off == 0 and (t & 8) == 0:
                # End of stream marker
                break
            m_off += ((t & 8) << 11)
            m_off += 0x4000
            m_pos = op - m_off
            _copy_match(out, op, m_pos, m_len, max_out)
            op += m_len
            t = src[ip-2] & 3

        else:
            # M1 match: length 2, offset 1-2048
            m_pos = op - 1 - (t >> 2) - (src[ip] << 2)
            ip += 1
            out[op] = out[m_pos]; out[op+1] = out[m_pos+1]
            op += 2
            t = t & 3

        # Handle literal trailer (0-3 bytes based on 't')
        if t == 0:
            # No trailing literals; read next control byte
            if ip >= ip_end:
                break
            t = src[ip]; ip += 1
            if t >= 16:
                continue
            # Literal run: length = t + 3 (with extension for t==0)
            if t == 0:
                while ip < ip_end and src[ip] == 0:
                    t += 255; ip += 1
                t += 15 + src[ip]; ip += 1
            n = t + 3
            if ip + n > ip_end or op + n > max_out:
                n = min(ip_end - ip, max_out - op)
            out[op:op+n] = src[ip:ip+n]
            op += n; ip += n
            # Next control byte
            if ip >= ip_end:
                break
            t = src[ip]; ip += 1
        else:
            # Copy t trailing literal bytes
            if ip + t > ip_end or op + t > max_out:
                break
            out[op:op+t] = src[ip:ip+t]
            op += t; ip += t
            if ip >= ip_end:
                break
            t = src[ip]; ip += 1

    return bytes(out[:op])


def _copy_match(out, op, m_pos, m_len, max_out):
    """Copy m_len bytes from m_pos to op in the output buffer (handles overlap)."""
    for i in range(m_len):
        if op + i >= max_out:
            break
        if m_pos + i >= 0:
            out[op + i] = out[m_pos + i]
        else:
            out[op + i] = 0


# ─── LZO1X-1 Compression ─────────────────────────────────────────────────────

_HTAB_BITS = 14
_HTAB_SIZE = 1 << _HTAB_BITS
_HTAB_MASK = _HTAB_SIZE - 1
_M2_MAX_LEN = 8
_M2_MAX_OFF = 0x0800
_M3_MAX_OFF = 0x4000
_M4_MAX_OFF = 0xBFFF


def _hash4(data, p):
    """Simple hash of 4 bytes for dictionary lookup."""
    v = data[p] | (data[p+1] << 8) | (data[p+2] << 16) | (data[p+3] << 24)
    return ((v * 0x1824429D) >> 18) & _HTAB_MASK


def _match_len(data, a, b, limit):
    """Return how many bytes match starting at positions a and b."""
    n = 0
    while b + n < limit and data[a + n] == data[b + n]:
        n += 1
    return n


def compress(data):
    """Compress data using LZO1X-1 algorithm.
    
    Args:
        data: bytes/bytearray to compress
    
    Returns:
        bytes of LZO1X compressed data
    """
    src = bytes(data)
    src_len = len(src)
    out = bytearray()

    if src_len <= 12:
        # Too short for matching - emit as literal + EOS
        if src_len == 0:
            # Just EOS
            out.extend(b'\x11\x00\x00\x00')
            return bytes(out)
        out.append(src_len + 17)
        out.extend(src)
        out.extend(b'\x11\x00\x00\x00')
        return bytes(out)

    htab = [0] * _HTAB_SIZE
    ip = 0            # current input position
    lit_start = 0     # start of pending literal run
    first_lit = True  # is this the first literal emission?

    # Need at least 4 bytes for hashing
    ip_limit = src_len - 4

    while ip <= ip_limit:
        h = _hash4(src, ip)
        ref = htab[h]
        htab[h] = ip

        m_off = ip - ref
        if ref > 0 and m_off >= 1 and m_off <= _M4_MAX_OFF and ip + 3 < src_len:
            # Check if we actually have a match
            if src[ref] == src[ip] and src[ref+1] == src[ip+1] and src[ref+2] == src[ip+2]:
                # We have a match of at least 3
                m_len = 3 + _match_len(src, ref + 3, ip + 3, src_len)
                lit_len = ip - lit_start

                # Emit pending literals
                if lit_len > 0:
                    if first_lit:
                        _emit_first_literal(out, src, lit_start, lit_len)
                        first_lit = False
                    elif lit_len <= 3:
                        # Patch into previous match's last byte
                        out[-2] |= lit_len
                        out.extend(src[lit_start:lit_start + lit_len])
                    else:
                        # Emit as standalone literal run
                        t = lit_len - 3
                        if t <= 15:
                            out.append(t)
                        else:
                            out.append(0)
                            remaining = t - 15
                            while remaining > 255:
                                out.append(0)
                                remaining -= 255
                            out.append(remaining)
                        out.extend(src[lit_start:lit_start + lit_len])

                # Emit match
                if m_off <= _M2_MAX_OFF and m_len <= _M2_MAX_LEN:
                    # M2 match: 2 bytes
                    m_off -= 1
                    out.append(((m_len - 1) << 5) | ((m_off & 7) << 2))
                    out.append(m_off >> 3)
                elif m_off <= _M3_MAX_OFF:
                    # M3 match: 3 bytes
                    m_off -= 1
                    if m_len <= 33:
                        out.append(32 | (m_len - 2))
                    else:
                        out.append(32)
                        remaining = m_len - 2 - 31
                        while remaining > 255:
                            out.append(0)
                            remaining -= 255
                        out.append(remaining)
                    out.append((m_off << 2) & 0xFF)
                    out.append((m_off >> 6) & 0xFF)
                else:
                    # M4 match: 3 bytes
                    m_off -= 0x4000
                    if m_len <= 9:
                        out.append(16 | ((m_off >> 11) & 8) | (m_len - 2))
                    else:
                        out.append(16 | ((m_off >> 11) & 8))
                        remaining = m_len - 2 - 7
                        while remaining > 255:
                            out.append(0)
                            remaining -= 255
                        out.append(remaining)
                    out.append((m_off << 2) & 0xFF)
                    out.append((m_off >> 6) & 0xFF)

                ip += m_len
                lit_start = ip
                continue

        ip += 1

    # Emit remaining literals
    lit_len = src_len - lit_start
    if lit_len > 0:
        if first_lit:
            _emit_first_literal(out, src, lit_start, lit_len)
        elif lit_len <= 3:
            out[-2] |= lit_len
            out.extend(src[lit_start:lit_start + lit_len])
        else:
            t = lit_len - 3
            if t < 16:
                out.append(t)
            else:
                out.append(0)
                remaining = t - 15
                while remaining > 255:
                    out.append(0)
                    remaining -= 255
                out.append(remaining)
            out.extend(src[lit_start:lit_start + lit_len])

    # End-of-stream marker (M4 with offset=0)
    out.extend(b'\x11\x00\x00\x00')
    return bytes(out)


def _emit_first_literal(out, src, start, length):
    """Emit the very first literal run in the stream."""
    if length <= 238:
        # Use the (t > 17) encoding: first byte = length + 17
        out.append(length + 17)
    else:
        # Use the (t < 16) encoding: t + 3 = length, t = length - 3
        t = length - 3
        if t <= 14:
            out.append(t)
        else:
            out.append(0)
            t -= 15
            while t > 255:
                out.append(0)
                t -= 255
            out.append(t)
    out.extend(src[start:start + length])
