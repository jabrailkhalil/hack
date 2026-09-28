"""Synthetic correctness tests, not estimates of real GNSS accuracy."""
import hashlib, inspect, io, json, struct, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from decoder import decode, VEL, FIX
from policy import POLICY, REASONS, FLAGS, make_teacher, nearest, pairing
from storage import Store, columns, savez, ROOT

class Writer:
    def __init__(self,end='<'):self.end=end;self.b=bytearray(b'\x00\x01\0\0' if end=='<' else b'\x00\x00\0\0')
    def add(self,fmt,val,align):
        self.b.extend(b'\0'*((-(len(self.b)-4))%align));self.b.extend(struct.pack(self.end+fmt,*val))
    def header(self,t=1_000_000_000,frame='map'):
        self.add('iI',(t//10**9,t%10**9),4);b=frame.encode()+b'\0';self.add('I',(len(b),),4);self.b.extend(b)

def fake(speed, offset=0, frames='map', stamp=None, nofix=False):
    rows=[];fix=[]
    for i,v in enumerate(speed):
        t=int(stamp[i]) if stamp is not None else 1_000_000_000+i*100_000_000+offset
        rows.append(dict(message_id=i,record_ns=t+123,stamp_ns=t,frame_id=frames,
          wire_sha256=hashlib.sha256(str((t,v,frames)).encode()).hexdigest(),linear=(v,0.,0.),angular=(0.,0.,0.)))
        fix.append(dict(message_id=100+i,record_ns=t+1000,stamp_ns=t,frame_id='antenna',
          wire_sha256=hashlib.sha256(str((t,'fix')).encode()).hexdigest(),position=(55.,37.,180.),
          covariance=(0.,)*9,status=-1 if nofix else 0,service=3,covariance_type=0))
    return columns(rows,'vel'),columns(fix,'fix')

def teach(a,b):return make_teacher(a[0],b[0],a[1],b[1])

class Tests(unittest.TestCase):
    def test_decode_velocity_endians_and_frames(self):
        for end in ('<','>'):
            for frame in ('','a','map','longer_frame'):
                w=Writer(end);w.header(frame=frame);w.add('6d',(1.,2.,3.,4.,5.,6.),8)
                d=decode(bytes(w.b),VEL);self.assertEqual(d['frame_id'],frame);self.assertEqual(d['linear'],(1.,2.,3.))
                self.assertEqual(d['angular'],(4.,5.,6.));self.assertEqual(d['stamp_ns'],10**9)
    def test_decode_fix_all_fields(self):
        for end in ('<','>'):
            w=Writer(end);w.header();w.add('b',(-1,),1);w.add('H',(3,),2);w.add('3d',(55.,37.,180.),8)
            w.add('9d',tuple(range(9)),8);w.add('B',(0,),1);d=decode(bytes(w.b),FIX)
            self.assertEqual(d['status'],-1);self.assertEqual(d['service'],3);self.assertEqual(d['covariance'],tuple(range(9)))
    def test_truncated_payload(self):
        w=Writer();w.header();w.add('6d',(0.,)*6,8)
        for n in (0,2,4,9,len(w.b)-1):
            with self.assertRaises((ValueError,struct.error)):decode(bytes(w.b[:n]),VEL)
    def test_unknown_representation(self):
        with self.assertRaises(ValueError):decode(b'\0\x03\0\0'+b'\0'*100,VEL)
    def test_bad_nanoseconds(self):
        w=Writer();w.add('iI',(1,10**9),4);w.add('I',(1,),4);w.b+=b'\0'
        with self.assertRaises(ValueError):decode(bytes(w.b),VEL)
    def test_both_zero_retained_unknown_cov(self):
        t=teach(fake([0.,0.,0.]),fake([0.,0.,0.]));self.assertTrue(t['accepted'].all());self.assertTrue((t['speed_mps']==0).all())
        self.assertTrue((t['flag_bits']&FLAGS['UNKNOWN_COVARIANCE']!=0).all())
    def test_disagree_abstains(self):
        t=teach(fake([0.]),fake([5.]));self.assertFalse(t['accepted'][0]);self.assertTrue(np.isnan(t['speed_mps'][0]))
        self.assertTrue(t['reason_bits'][0]&REASONS['SPEED_DISAGREEMENT'])
    def test_single_receiver_never_teacher(self):
        t=teach(fake([1.]),fake([]));self.assertEqual(t['state'][0],2);self.assertFalse(t['accepted'][0])
    def test_empty(self):self.assertEqual(len(teach(fake([]),fake([]))['stamp_ns']),0)
    def test_nonfinite(self):
        t=teach(fake([np.nan]),fake([1.]));self.assertFalse(t['accepted'][0]);self.assertTrue(t['reason_bits'][0]&REASONS['NONFINITE_VELOCITY'])
    def test_frame_mismatch(self):self.assertFalse(teach(fake([1.],frames='a'),fake([1.],frames='b'))['accepted'][0])
    def test_no_fix(self):self.assertFalse(teach(fake([1.],nofix=True),fake([1.]))['accepted'][0])
    def test_missing_fix(self):
        v,f=fake([1.]);empty=fake([])[1];self.assertFalse(teach((v,empty),(v,f))['accepted'][0])
    def test_altitude_nan_does_not_invent_height(self):
        a=fake([1.]);a[1]['position'][0,2]=np.nan;t=teach(a,fake([1.]));self.assertTrue(t['accepted'][0]);self.assertTrue(t['flag_bits'][0]&FLAGS['ALTITUDE_UNKNOWN'])
    def test_pair_tolerance_boundary(self):
        self.assertTrue(teach(fake([1.]),fake([1.],offset=50_000_000))['accepted'][0])
        self.assertEqual(teach(fake([1.]),fake([1.],offset=50_000_001))['accepted'].sum(),0)
    def test_nearest_tie(self):
        a,t=nearest(np.array([5]),np.array([0,10]),5);self.assertEqual(a[0],-1);self.assertTrue(t[0])
    def test_exact_before_nearest(self):
        p=pairing(np.array([100,120]),np.array([120]));self.assertIn((1,0,False),p);self.assertFalse(any(x[0]==0 and x[1]>=0 for x in p))
    def test_duplicate_exact(self):
        a=fake([1.,1.],stamp=[10**9,10**9]);b=fake([1.]);t=teach(a,b);self.assertEqual(len(t['stamp_ns']),1);self.assertTrue(t['accepted'][0])
    def test_conflicting_duplicate(self):
        t=teach(fake([1.,2.],stamp=[10**9,10**9]),fake([1.]));self.assertFalse(t['accepted'][0]);self.assertTrue(t['reason_bits'][0]&REASONS['CONFLICTING_DUPLICATE'])
    def test_temporal_jump_marks_both_sides(self):
        t=teach(fake([5.,0.,5.]),fake([5.,0.,5.]));self.assertEqual(t['accepted'].sum(),0);self.assertTrue(t['flag_bits'][1]&FLAGS['ISOLATED_ZERO'])
    def test_gap_not_interpolated_or_zeroed(self):
        t=teach(fake([1.,10.],stamp=[10**9,3*10**9]),fake([1.,10.],stamp=[10**9,3*10**9]));self.assertTrue(t['accepted'].all());self.assertTrue(t['flag_bits'][1]&FLAGS['GAP_BEFORE'])
    def test_boundary_agreement(self):
        self.assertTrue(teach(fake([0.]),fake([.3]))['accepted'][0]);self.assertFalse(teach(fake([0.]),fake([.3000001]))['accepted'][0])
    def test_quality_api_no_vehicle(self):
        self.assertEqual(list(inspect.signature(make_teacher).parameters),['master_vel','rover_vel','master_fix','rover_fix'])
        with self.assertRaises(TypeError):make_teacher(*fake([1.]),*fake([1.]),vehicle=[1.])
    def test_forbidden_role_before_any_io(self):
        with patch('sqlite3.connect') as sql:
            with self.assertRaises(PermissionError):Store('/none','/none','/none','test')
            with self.assertRaises(PermissionError):Store('/none','/none','/none','validation')
            with self.assertRaises(PermissionError):Store('/none','/none','/none','development')
            sql.assert_not_called()
    def test_wrong_bag_denied_before_io(self):
        s=Store.__new__(Store);s.records={'x':{'split':'test'}};s.role='train'
        with patch('sqlite3.connect') as sql:
            with self.assertRaises(PermissionError):s.path('x')
            sql.assert_not_called()
    def test_symmetric(self):
        a,b=fake([1.,1.1,1.2]),fake([1.1,1.,1.3],offset=20_000_000)
        x,y=teach(a,b),teach(b,a);np.testing.assert_array_equal(x['accepted'],y['accepted']);np.testing.assert_array_equal(x['speed_mps'],y['speed_mps'])
    def test_npz_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.npz',Path(d)/'b.npz';v={'x':np.array([1.,np.nan]),'y':np.array(['map'])};savez(a,v);savez(b,v)
            self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(np.load(a,allow_pickle=False)['y'][0],'map')
    def test_random_pairing_independent_oracle(self):
        rng=np.random.default_rng(42)
        for _ in range(100):
            a=np.unique(rng.integers(1,30,12))*10_000_000;b=np.unique(rng.integers(1,30,10))*10_000_000
            p=pairing(a,b);got={(int(a[i]),int(b[j])) for i,j,_ in p if i>=0 and j>=0}
            exact=set(a)&set(b);expected={(int(t),int(t)) for t in exact}
            aa=[int(t) for t in a if t not in exact];bb=[int(t) for t in b if t not in exact]
            def near(x,v):
                if not v:return None
                ds=[abs(x-y) for y in v];m=min(ds)
                return v[ds.index(m)] if m<=50_000_000 and ds.count(m)==1 else None
            for t in aa:
                u=near(t,bb)
                if u is not None and near(u,aa)==t:expected.add((t,u))
            self.assertEqual(got,expected)
    def test_folds(self):
        f=json.loads((Path(__file__).parent/'contracts/TRAIN_FOLDS.json').read_text());gs=f['groups']
        self.assertEqual(sum(x['fold']=='fit' for x in gs),20);self.assertEqual(sum(x['fold']=='check' for x in gs),7)
        split=json.loads((ROOT/'research/split_v3.json').read_text());bygroup={x['group']:x['fold'] for x in gs};clusters={}
        for r in split['records']:
            if r['split']=='train':clusters.setdefault(r['vehicle_wire_sha256'],set()).add(bygroup[r['group']])
        self.assertTrue(all(len(x)==1 for x in clusters.values()))

if __name__=='__main__':unittest.main(verbosity=2)
