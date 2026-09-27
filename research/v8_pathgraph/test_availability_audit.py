import dataclasses
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import availability_audit as a
from pathgraph import ARMS


def fix(t, status=0):
    return a.Fix(int(t*1e9), int(t*1e9), 'rover', 55.8, 37.5, status)


def wire(endian='<'):
    out = bytearray(b'\0\1\0\0' if endian == '<' else b'\0\0\0\0')
    def put(fmt, align, *values):
        out.extend(b'\0'*(-(len(out)-4) % align));out.extend(struct.pack(endian+fmt, *values))
    put('iI', 4, 12, 345)
    s = b'gps\0';put('I', 4, len(s));out.extend(s)
    put('b', 1, 2);put('H', 2, 1);put('3d', 8, 55.8, 37.5, 180.)
    put('9d', 8, *([0.]*9));put('B', 1, 0)
    return bytes(out)


class AvailabilityTests(unittest.TestCase):
    def test_recorded_does_not_drop(self):
        data = [fix(t) for t in range(100)]
        self.assertEqual(list(a.select(data, 0)), data)

    def test_half_open_initial_window(self):
        self.assertEqual([f.stamp_ns for f in a.select([fix(0), fix(4.999), fix(5)], 0, 5)], [0, 4999000000])

    def test_no_gnss_is_empty(self):
        self.assertEqual(list(a.select([fix(0), fix(100)], 0, 0)), [])

    def test_isolated_fix_spacing(self):
        got = list(a.select([fix(t) for t in range(131)], 0, 5, 30))
        self.assertEqual([f.stamp_ns//10**9 for f in got], [0, 1, 2, 3, 4, 5, 35, 65, 95, 125])

    def test_invalid_fix_consumes_slot(self):
        got = list(a.select([fix(5, -1), fix(6), fix(34), fix(35)], 0, 5, 30))
        self.assertEqual([f.stamp_ns//10**9 for f in got], [5, 35])
        self.assertEqual(got[0].status, -1)

    def test_burst_boundaries(self):
        got = list(a.select([fix(t) for t in (4,5,6,7,64,65,66,67)], 0, 5, 60, 2))
        self.assertEqual([f.stamp_ns//10**9 for f in got], [4,5,6,65,66])

    def test_prefix_does_not_depend_on_future(self):
        data = [fix(t) for t in range(100)]
        for kwargs in a.SCENARIOS.values():
            prefix = list(a.select(data[:60], 0, **kwargs))
            full = [f for f in a.select(data, 0, **kwargs) if f.receipt_ns < 60*10**9]
            self.assertEqual(prefix, full)

    def test_no_selection_by_coordinate_or_status(self):
        data = [fix(t) for t in range(100)]
        bad = [dataclasses.replace(f, latitude=float('nan'), longitude=-1., status=-1) for f in data]
        for kwargs in a.SCENARIOS.values():
            self.assertEqual([f.receipt_ns for f in a.select(data, 0, **kwargs)],
                             [f.receipt_ns for f in a.select(bad, 0, **kwargs)])

    def test_receipt_not_header_controls_mask(self):
        data = [dataclasses.replace(fix(5), stamp_ns=10**9)]
        self.assertEqual(list(a.select(data, 0, 5)), [])

    def test_time_reversal_and_wrong_origin_rejected(self):
        with self.assertRaises(ValueError):list(a.select([fix(2),fix(1)], 0))
        with self.assertRaises(ValueError):list(a.select([fix(1)], 2*10**9))

    def test_bad_schedules_rejected(self):
        for kwargs in ({'warmup_s':-1},{'period_s':30},{'warmup_s':5,'period_s':0},
                       {'warmup_s':5,'burst_s':2},{'warmup_s':5,'period_s':1,'burst_s':2}):
            with self.assertRaises(ValueError):list(a.select([],0,**kwargs))

    def test_decode_cdr1_both_byte_orders(self):
        expected = a.Fix(12000000345, 999, 'rover', 55.8, 37.5, 2, 'gps')
        for endian in ('<','>'):
            self.assertEqual(a.decode_fix(wire(endian),999), expected)

    def test_reject_bad_wire(self):
        data = wire()
        for b in (b'',data[:10],data[:-1],b'\0\7\0\0'+data[4:],data+b'x'):
            with self.assertRaises((ValueError,struct.error)):a.decode_fix(b,999)

    def test_pins_before_sql(self):
        with patch.object(a, 'digest', return_value='bad'), patch.object(a.sqlite3, 'connect', side_effect=AssertionError('SQL')):
            with self.assertRaises(ValueError):a.load_fixes(Path('/missing'))

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):a.run(Path('/missing'),Path('/missing'),Path(tmp))

    def test_true_thinning_prevents_course_even_on_map(self):
        n = 301
        rows = [dict(x=float(i), y=0., z=0., tang=0., curv=0.) for i in range(101)]
        route = a.Pathgraph({'points':rows,'paths':[{'point_indices':list(range(101))}]})
        class Grid:
            def xy(self, lat, lon):return lat,lon
        t = np.arange(n)*.05
        cache = {'source_ns':np.arange(n,dtype=np.int64)*50000000,
                 'receipt_ns':np.arange(n,dtype=np.int64)*50000000,
                 'raw_distance':2*t, 'predictions':np.column_stack([t,*[np.zeros(n) for _ in range(5)]])}
        fixes = [a.Fix(int(ti*1e9),int(ti*1e9),'rover',20+2*ti+ARMS['rover'][0],0.) for ti in t]
        before = cache['raw_distance'].copy()
        _, full = a.replay([route],Grid(),cache,fixes)
        _, thin = a.replay([route],Grid(),cache,list(a.select(fixes,0,0,30)))
        self.assertGreater(full['available_positions'],0)
        self.assertEqual(thin['available_positions'],0)
        self.assertIsNone(thin['accuracy_rmse'])
        self.assertTrue(np.array_equal(before,cache['raw_distance']))


if __name__ == '__main__':unittest.main()
