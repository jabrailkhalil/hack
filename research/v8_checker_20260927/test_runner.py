"""Wire format, arithmetic and isolation tests for the offline checker harness."""
from __future__ import annotations
from dataclasses import asdict
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runner as r


def encode_odometry(end='<', frame='map', child='base_link', stamp=(12,345)):
    raw=bytearray(b'\x00\x01\x00\x00' if end=='<' else b'\x00\x00\x00\x00')
    def put(fmt,alignment,*values):
        raw.extend(b'\0'*((-(len(raw)-4))%alignment));raw.extend(struct.pack(end+fmt,*values))
    def text(s):
        value=s.encode()+b'\0';put('I',4,len(value));raw.extend(value)
    put('iI',4,*stamp);text(frame);text(child)
    put('3d',8,1.,2.,3.);put('4d',8,0.,0.,0.,1.);put('36d',8,*range(36))
    put('6d',8,4.,5.,6.,7.,8.,9.);put('36d',8,*range(100,136))
    return bytes(raw)


def synthetic_data(seconds=5):
    events=[];receipts=[]
    for i in range(seconds*10+1):
        t=i*.1
        for ch,value in ((0,0.),(1,3.),(2,3.)):
            events.append((t,ch,value));receipts.append(10**18+i*100_000_000+ch)
    return r.Data(10**18,np.array(events),np.array(receipts,np.int64),[],{}, {})


class WireAndIsolationTests(unittest.TestCase):
    def test_little_endian_odometry(self):
        d=r.decode_odometry(encode_odometry())
        self.assertEqual(d['stamp_ns'],12_000_000_345)
        self.assertEqual(d['xyz'],(1.,2.,3.));self.assertEqual(d['twist'],(4.,5.,6.,7.,8.,9.))
        self.assertEqual(d['pose_covariance'],tuple(range(36)));self.assertEqual(d['twist_covariance'],tuple(range(100,136)))
        self.assertEqual((d['frame'],d['child']),('map','base_link'))

    def test_big_endian_and_variable_padding(self):
        for frame in ('m','map','long_frame_name'):
            self.assertEqual(r.decode_odometry(encode_odometry('>',frame=frame)),r.decode_odometry(encode_odometry('<',frame=frame)))

    def test_truncated_payload_rejected(self):
        raw=encode_odometry()
        for end in (1,4,15,len(raw)-1):
            with self.assertRaises((ValueError,struct.error)):r.decode_odometry(raw[:end])

    def test_trailing_payload_rejected(self):
        with self.assertRaises(ValueError):r.decode_odometry(encode_odometry()+b'\0')

    def test_invalid_stamp_rejected(self):
        with self.assertRaises(ValueError):r.decode_odometry(encode_odometry(stamp=(1,10**9)))

    def test_invalid_string_and_cdr2_rejected(self):
        raw=bytearray(encode_odometry());raw[12:16]=struct.pack('<I',999999)
        with self.assertRaises(ValueError):r.decode_odometry(raw)
        raw=bytearray(encode_odometry());raw[1]=7
        with self.assertRaises(ValueError):r.decode_odometry(raw)

    def test_frozen_bytes(self):
        self.assertGreaterEqual(len(r.frozen_sources()),29)

    def test_only_two_exact_profiles(self):
        models=r.fixed_models();self.assertEqual(tuple(models),r.NAMES)
        a,b=(asdict(models[n][1]) for n in r.NAMES)
        self.assertEqual([k for k in a if a[k]!=b[k]],['disturbance_limit_mps2'])
        self.assertEqual(b['disturbance_limit_mps2'],.7000000000000001)

    def test_source_mismatch_fails(self):
        with patch.object(r,'sha',return_value='bad'):
            with self.assertRaises(ValueError):r.frozen_sources()

    def test_bad_db_before_sql(self):
        with patch.object(r,'sha',return_value='bad'),patch.object(r.sqlite3,'connect',side_effect=AssertionError('SQL forbidden')):
            with self.assertRaises(ValueError):r.load_data(Path('/unused'))

    def test_nearest_ns_precision_and_ties(self):
        epoch=1_800_000_000_000_000_000
        indices,mask=r.nearest([epoch,epoch+2,epoch+20],[epoch+1,epoch+21],2)
        self.assertEqual(indices.tolist(),[1,2]);self.assertTrue(np.all(mask))

    def test_nearest_tolerance_and_empty(self):
        indices,mask=r.nearest([0,10],[5,16],5)
        self.assertEqual(mask.tolist(),[True,False])
        self.assertFalse(r.nearest([], [1])[1][0])

    def test_reference_duplicate_stamps_rejected(self):
        for ns in ([2,1],[1,1]):
            with self.assertRaises(ValueError):r.nearest(ns,[1])

    def test_pair_sync_consumes_messages_once(self):
        s=r.PairSync(tolerance_ns=5)
        s.add(0,10,100);s.add(1,11,101);s.add(1,12,102)
        self.assertEqual(s.pairs,[(100,101)]);self.assertEqual(len(s.q[0]),0)

    def test_sync_strict_boundary(self):
        s=r.PairSync(tolerance_ns=5);s.add(0,10,0);s.add(1,15,0)
        self.assertEqual(s.pairs,[])

    def test_sync_nearest_and_tie_order(self):
        s=r.PairSync(tolerance_ns=10);s.add(0,12,1);s.add(0,8,2);s.add(1,10,9)
        self.assertEqual(s.pairs,[(1,9)])

    def test_sync_queue_evicts_oldest_stamp_not_arrival(self):
        s=r.PairSync(queue_size=2,tolerance_ns=1)
        for t in (10,30,20):s.add(0,t,t)
        self.assertEqual(list(s.q[0]),[30,20]);self.assertEqual(s.evicted,[1,0])

    def test_no_reference_or_gnss_in_model_inputs(self):
        data=synthetic_data();models=r.fixed_models()
        before=r.scheduled_replay(data,models['main'])
        data.references=[{'bogus_reference':'not a model input'}];data.gnss={'bad':object()}
        after=r.scheduled_replay(data,models['main'])
        self.assertTrue(np.array_equal(before[0],after[0],equal_nan=True));self.assertEqual(before[2],after[2])

    def test_native_schedule_equals_pinned_evaluator(self):
        data=synthetic_data()
        for n,model in r.fixed_models().items():
            expected,info=r.e.g.predict(data.events,model);actual,_,diag=r.scheduled_replay(data,model)
            self.assertTrue(np.array_equal(actual,expected,equal_nan=True));self.assertEqual(info,diag)

    def test_future_extension_does_not_change_past(self):
        a=synthetic_data(3);b=synthetic_data(5)
        for phase in (None,0,5_000_000):
            aa,_,_=r.scheduled_replay(a,r.fixed_models()['disturbance_070'],phase)
            bb,_,_=r.scheduled_replay(b,r.fixed_models()['disturbance_070'],phase)
            self.assertTrue(np.array_equal(aa,bb[:len(aa)],equal_nan=True))

    def test_distance_integral_detects_tampering(self):
        a=np.array([[0.,0.,0.],[1.,2.,1.],[2.,2.,3.]])
        self.assertEqual(r.integrity(a,a.copy(),{'start':1.})['max_integral_error_m'],0.)
        for index in (0,2):
            b=a.copy();b[index,2]+=.5
            with self.assertRaises(AssertionError):r.integrity(a,b,{'start':1.})

    def test_epoch_stamps_not_float_array(self):
        data=synthetic_data();a,_,_=r.scheduled_replay(data,r.fixed_models()['main'])
        p=r.stamp_predictions(data,a)
        self.assertIsInstance(p[0][0],int)
        self.assertEqual(p[0][0],data.origin_ns+round(a[0,0]*1e9))

    def test_kinematic_label_does_not_relabel_gnss_diagnostic(self):
        value={'native':{'definition':'s versus integral matched horizontal GNSS speed; NOT xyz'},
               'sparse_GNSS_diagnostic':{'definition':'s versus integral matched horizontal GNSS speed; NOT xyz'}}
        r.relabel_distance({k:v for k,v in value.items() if k != 'sparse_GNSS_diagnostic'})
        self.assertIn('kinematic_state',value['native']['definition'])
        self.assertIn('GNSS speed',value['sparse_GNSS_diagnostic']['definition'])

    def test_results_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):r.run(Path('/unused'),Path(tmp))


class UploadedCheckerArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('CHECKER_ROOT')
        if not path:raise unittest.SkipTest('Set CHECKER_ROOT to the uploaded checksum-pinned check-code folder')
        cls.path=Path(path);cls.checker=r.load_checker(cls.path)

    def test_unmodified_accumulator(self):
        a=self.checker.ErrorAccumulator();self.assertTrue(math.isnan(a.rmse))
        self.assertTrue(a.add(-3));self.assertTrue(a.add(4))
        self.assertFalse(a.add(float('nan')));self.assertFalse(a.add(float('inf')))
        self.assertEqual(a.count,2);self.assertEqual(a.maximum_error,4)
        self.assertAlmostEqual(a.rmse,math.sqrt(12.5))

    def test_original_callback_xyz_and_velocity(self):
        reference=[dict(stamp_ns=10,twist=[5.],xyz=[3.,4.,12.],frame='map',child='base_link')]
        score=r.exact_arithmetic(self.checker,reference,[(10,7.,0.)],[(0,0)])
        self.assertEqual(score['velocity']['rmse'],2.)
        self.assertEqual(score['raw_position']['distance']['rmse'],13.)
        self.assertFalse(score['position_frames_compatible'])

    def test_checker_missing_not_zero(self):
        score=r.exact_arithmetic(self.checker,[],[],[])
        self.assertIsNone(score['velocity']['rmse']);self.assertEqual(score['velocity']['n'],0)

    def test_checker_source_hash_before_ast(self):
        with patch.object(r,'sha',return_value='bad'):
            with self.assertRaises(ValueError):r.load_checker(self.path)

    def test_reference_copied_to_result_is_zero_by_construction(self):
        a=r.message(100,5.,(1.,2.,3.),'map')
        self.assertEqual(self.checker.position_errors(a,a),(0.,0.,0.,0.))
        self.assertEqual(self.checker.get_numeric_field(a,'twist.twist.linear.x'),5.)


if __name__=='__main__':unittest.main()
