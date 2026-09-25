#!/usr/bin/env python3
"""Read the supplied Humble SQLite/CDR schemas; stream arrival-ordered CSV exports.

Decoder is intentionally restricted to the four organizer types and CDR1.
An unsupported wire representation fails explicitly. This is an OFFLINE tool.
"""
import argparse
import csv
import gzip
from pathlib import Path
import sqlite3
import struct


class CDR:
    def __init__(self, raw):
        if raw[:2] not in (b'\x00\x00', b'\x00\x01'):
            raise ValueError('Only CDR1 supported')
        self.raw, self.pos = raw, 4
        self.end = '<' if raw[1] else '>'

    def take(self, fmt, alignment):
        self.pos = 4 + ((self.pos - 4 + alignment - 1) // alignment) * alignment
        value = struct.unpack_from(self.end + fmt, self.raw, self.pos)
        self.pos += struct.calcsize(self.end + fmt)
        return value[0] if len(value) == 1 else value

    def header(self):
        sec, ns = self.take('iI', 4)
        length = self.take('I', 4)
        if not 0 < length < 4096 or self.pos + length > len(self.raw):
            raise ValueError('Invalid CDR header string')
        if self.raw[self.pos + length - 1] != 0 or ns >= 1000000000:
            raise ValueError('Invalid string terminator or nanoseconds')
        self.pos += length
        return sec * 1000000000 + ns


def decode(raw, typ):
    d = CDR(raw)
    stamp = d.header()
    values = ['', '', '', '', '']
    if typ == 'tram_vehicle_msgs/msg/VelocitySensor':
        values[0] = d.take('d', 8)
    elif typ == 'tram_vehicle_msgs/msg/DriverControllerCommand':
        values[0] = d.take('b', 1)
    elif typ == 'geometry_msgs/msg/TwistStamped':
        values[:3] = d.take('6d', 8)[:3]
    elif typ == 'sensor_msgs/msg/NavSatFix':
        values[3] = d.take('b', 1)
        d.take('H', 2)
        values[:3] = d.take('3d', 8)
        cov = d.take('9d', 8)
        values[4] = max(cov[0], cov[4], cov[8])
        d.take('B', 1)
    else:
        raise ValueError('Unsupported type: ' + typ)
    if not 0 <= len(raw) - d.pos < 8:
        raise ValueError('Unexpected trailing payload: ' + typ)
    return stamp, values


def export_bag(bag, output):
    databases = sorted(bag.glob('*.db3'))
    if len(databases) != 1:
        raise ValueError('Expected exactly one db3 per organizer bag: ' + str(bag))
    output.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)
    count = 0
    try:
        topics = {r[0]: (r[1], r[2]) for r in con.execute('SELECT id,name,type FROM topics')}
        with gzip.open(output, 'wt', newline='') as target:
            writer = csv.writer(target)
            writer.writerow(['topic', 'record_ns', 'stamp_ns', 'v0', 'v1', 'v2', 'status', 'covmax'])
            for tid, received, raw in con.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
                name, typ = topics[tid]
                stamp, values = decode(raw, typ)
                writer.writerow([name, received, stamp, *values])
                count += 1
    finally:
        con.close()
    print(bag.name, count, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bags', nargs='+', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('exports'))
    args = parser.parse_args()
    for bag in args.bags:
        export_bag(bag, args.output_dir / (bag.name + '.csv.gz'))


if __name__ == '__main__':
    main()
