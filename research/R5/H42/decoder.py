"""Strict independent CDR1 GNSS decoder. Offline only; no ROS dependency."""
import struct

VEL = 'geometry_msgs/msg/TwistStamped'
FIX = 'sensor_msgs/msg/NavSatFix'

class Reader:
    def __init__(self, raw):
        if len(raw) < 4 or raw[:2] not in (b'\x00\x00', b'\x00\x01'):
            raise ValueError('Unsupported/truncated CDR1 encapsulation')
        self.raw, self.pos, self.endian = raw, 4, '<' if raw[1] else '>'
    def take(self, fmt, align):
        p = 4 + ((self.pos - 4 + align - 1) // align) * align
        n = struct.calcsize(self.endian + fmt)
        if p + n > len(self.raw):
            raise ValueError('Truncated CDR field')
        result = struct.unpack_from(self.endian + fmt, self.raw, p)
        self.pos = p + n
        return result[0] if len(result) == 1 else result
    def header(self):
        sec, ns = self.take('iI', 4)
        size = self.take('I', 4)
        if ns >= 1_000_000_000 or not 0 < size < 4096:
            raise ValueError('Bad stamp/string length')
        end = self.pos + size
        if end > len(self.raw) or self.raw[end-1] != 0:
            raise ValueError('Truncated or unterminated frame_id')
        frame = self.raw[self.pos:end-1].decode('utf-8', errors='strict')
        if '\x00' in frame:
            raise ValueError('Embedded NUL in frame_id')
        self.pos = end
        return sec * 1_000_000_000 + ns, frame

def decode(raw, typ):
    d = Reader(raw)
    stamp, frame = d.header()
    out = {'stamp_ns': stamp, 'frame_id': frame}
    if typ == VEL:
        data = d.take('6d', 8)
        out.update(linear=data[:3], angular=data[3:])
    elif typ == FIX:
        status, service = d.take('b', 1), d.take('H', 2)
        position, cov, ctype = d.take('3d', 8), d.take('9d', 8), d.take('B', 1)
        out.update(status=status, service=service, position=position,
                   covariance=cov, covariance_type=ctype)
    else:
        raise ValueError('Unsupported GNSS schema: ' + typ)
    if not 0 <= len(raw) - d.pos < 8:
        raise ValueError('Unexpected trailing payload')
    return out

def common_fields(row, typ):
    if typ == VEL:
        return row['stamp_ns'], [*row['linear'], '', '']
    cov = row['covariance']
    return row['stamp_ns'], [*row['position'], row['status'], max(cov[0], cov[4], cov[8])]
