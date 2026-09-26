import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
from factory import build
from run import paired,safety_reasons,signed_integral,relative,exceeds,low_windows

def fixture():
 events=[]
 for t in np.arange(0,40,.1):
  for ch,val in ((0,.7 if t<10 else 0.),(1,4.),(2,4.)):events.append((t,ch,val))
 refs={'master':[(float(t),4.) for t in np.arange(0,40,.1)],'rover':[]}
 return np.asarray(events),refs
class DriverTests(unittest.TestCase):
 def test_role_denied_before_io(self):
  s=Store()
  with patch('sqlite3.connect',side_effect=AssertionError('unexpected database access')):
   for role in ('validation','test','unknown'):
    with self.assertRaises(PermissionError):s.load(s.plan['splits']['development'][0],role)
   with self.assertRaises(PermissionError):s.load(s.plan['splits']['validation'][0],'development')
 def test_native_score_and_off_equal(self):
  events,refs=fixture();row=paired(events,refs)
  c,r=profile();old=ev.Observer
  try:
   ev.Observer=lambda config:GuardedReadoutObserver(config,readout=r)
   native=ev.score(events,refs,dict(baseline_v2=c,balanced_physics=profile()[0]),OPS)
  finally:ev.Observer=old
  for rec in refs:
   for key in ('n','coverage','rmse','mae','bias','p95','false_stop_samples','distance_surrogate'):
    self.assertEqual(row['receivers'][rec]['v8'].get(key),native['receivers'][rec]['baseline_v2'].get(key))
  self.assertEqual(row['runtime']['v8'],row['runtime']['off'])
 def test_masks_missing_is_null(self):
  row=paired(*fixture(),fault=dict(kind='dropout',start=10.,end=15.))
  for n in ('v8','off','H35_R050','H35_R200'):
   self.assertIsNone(row['receivers']['rover'][n]['event_rmse'])
   self.assertEqual(row['receivers']['master'][n]['n'],row['provenance']['reference']['master']['n'])
 def test_full_fault_position_diagnostics(self):
  row=paired(*fixture(),fault=dict(kind='dropout',start=10.,end=15.),full=True)
  self.assertEqual(row['distance_delta']['off']['terminal_delta_s_m'],0.)
  self.assertEqual(row['distance_delta']['v8']['post_end_delta_s_m'],{'1':0.,'5':0.,'10':0.})
  self.assertIsNotNone(row['receivers']['master']['H35_R050']['distance_surrogate']['reanchored_span_rmse_m'])
 def test_signed_integral_honours_gaps(self):
  a=np.array([[0,2,0],[.05,2,.1],[.1,2,.2],[.15,2,.3]])
  self.assertAlmostEqual(signed_integral(a,np.array([1.,1.,np.nan,1.])),.05)
 def test_new_unrecovered_not_net_count(self):
  r=dict(bag='b',suite='original',runtime={'H35_R050':{'causal_errors':0,'resets':0}},receivers={'master':{'v8':{'n':2,'coverage':1.,'event_rmse':1.,'recovery_s':.1},'H35_R050':{'n':2,'coverage':1.,'event_rmse':1.,'recovery_s':None}}})
  self.assertTrue(any('new_unrecovered' in s for s in safety_reasons([r],'H35_R050')))
 def test_numerical_thresholds(self):
  self.assertFalse(exceeds(1.005,1.,.005));self.assertTrue(exceeds(1.0051,1.,.005));self.assertEqual(relative(0.,0.),0.);self.assertIsNone(relative(.1,0.))
 def test_low_speed_anchor_is_vehicle_only(self):
  events,_=fixture();events[events[:,1]>0,2]=1.5
  windows=list(low_windows(events));self.assertEqual(windows,[]) # 40-second stream cannot satisfy both 25s margins.
if __name__=='__main__':unittest.main()
