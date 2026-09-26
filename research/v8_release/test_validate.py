"""Synthetic gate/role/runner tests; never claims validation accuracy."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import validate as v
import prepare as prep
import ros_selected as ros


def gate_fixture():
    base=dict(clean_rmse=1.,pooled_rmse=1.,fault_rmse=1.,distance_rmse=1.,full_faulted_distance_rmse=1.)
    candidate=dict(base,fault_rmse=.9)
    primary={s:{'main':dict(base),'disturbance_070':dict(candidate)} for s in ('all','30618','30639')}
    extra={s:{k:{'main':1.,'disturbance_070':1.} for k in ('low','common','slow')} for s in primary}
    return primary,extra


def signals(seconds=70):
    events=[]
    for i in range(seconds*10+1):
        t=i*.1
        events.extend([(t,0,0.),(t,1,4.),(t,2,4.)])
    refs={'master':[(i*.05,4.) for i in range(seconds*20+1)],'rover':[]}
    return v.np.asarray(events),refs


class AdmissionTests(unittest.TestCase):
    def test_frozen_bytes_and_single_exact_parameter(self):
        self.assertEqual(len(v.verify_frozen()['baseline']),19)
        self.assertEqual(v.fixed_models()['disturbance_070'][1].disturbance_limit_mps2,.7000000000000001)

    def test_no_other_profile_selection(self):
        self.assertEqual(tuple(v.fixed_models()),('main','disturbance_070'))

    def test_synthetic_passing_gates(self):
        self.assertEqual(v.aggregate_gates(*gate_fixture()),[])

    def test_target_gain_not_replaced_by_other_vehicle(self):
        p,x=gate_fixture();p['30618']['disturbance_070']['fault_rmse']=1.
        self.assertIn('30618:insufficient_gain',v.aggregate_gates(p,x))

    def test_distance_guard_is_independent(self):
        p,x=gate_fixture();p['all']['disturbance_070']['full_faulted_distance_rmse']=1.01001
        self.assertIn('all:regression:full_faulted_distance_rmse',v.aggregate_gates(p,x))

    def test_missing_supplement_is_not_pass(self):
        p,x=gate_fixture();x['30618']['slow']['disturbance_070']=None
        self.assertIn('30618:missing:slow',v.aggregate_gates(p,x))

    def test_slow_regression_veto(self):
        p,x=gate_fixture();x['all']['slow']['disturbance_070']=1.00501
        self.assertIn('all:regression:slow',v.aggregate_gates(p,x))

    def test_missing_primary_and_nan_never_pass(self):
        for value in (None,float('nan'),float('inf')):
            p,x=gate_fixture();p['all']['disturbance_070']['pooled_rmse']=value
            self.assertIn('all:missing:pooled_rmse',v.aggregate_gates(p,x))

    def test_role_veto_before_any_measurement_io(self):
        s=v.ValidationStore('/no-dataset')
        with patch.object(v.e.ex,'digest',side_effect=AssertionError('Measurement hash must not run')):
            for role in ('train','development','test'):
                with self.assertRaises(PermissionError):s.load(s.plan['splits'][role][0])
            with self.assertRaises(PermissionError):s.load(s.plan['splits']['validation'][0],'test')

    def test_incomplete_data_is_failure_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'results'
            with self.assertRaises(FileNotFoundError):v.run(Path(tmp)/'missing',out,1)
            self.assertEqual(json.loads((out/'FAILURE.json').read_text())['status'],'INCOMPLETE_NOT_PASS')
            self.assertFalse((out/'RESULT.json').exists())

    def test_existing_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):v.run('/no-data',tmp,1)

    def test_clean_adapter_matches_frozen_scorer(self):
        events,refs=signals(6);models=v.fixed_models()
        a,info=v.e.predictions(events,models)
        got=v.e.score_arrays(a,info,refs);want=v.e.g.compare(events,refs,models)
        self.assertEqual(got['receivers'],want['receivers'])
        self.assertEqual(got['runtime'],want['runtime'])
        self.assertIsNone(got['receivers']['rover']['main']['rmse'])

    def test_all_original_faults_keep_prefault_and_integral(self):
        events,refs=signals();models=v.fixed_models();clean,_=v.e.predictions(events,models)
        faults=list(v.e.g.fault_windows(events));self.assertEqual(len(faults),4)
        for fault,window in faults:
            changed,_=v.e.predictions(events,models,fault)
            for n in v.NAMES:self.assertLess(v.integral_check(clean[n],changed[n],fault)['max_error_m'],1e-7)

    def test_integral_or_prefault_tampering_detected(self):
        events,_=signals(3);a,_=v.e.predictions(events,v.fixed_models());x=a['main'];f={'start':1.,'end':2.}
        b=x.copy();b[0,2]+=1.
        with self.assertRaises(AssertionError):v.integral_check(x,b,f)
        b=x.copy();b[-1,2]+=1.
        with self.assertRaises(AssertionError):v.integral_check(x,b,f)

    def test_nonfinite_distance_cannot_bypass_integral_gate(self):
        events,_=signals(3);a,_=v.e.predictions(events,v.fixed_models());x=a['main']
        for bad in (float('nan'),float('inf')):
            b=x.copy();b[-1,2]=bad
            with self.assertRaises(AssertionError):v.integral_check(x,b,{'start':1.,'end':2.})

    def test_future_extension_prefix(self):
        a,_=v.e.predictions(signals(3)[0],v.fixed_models());b,_=v.e.predictions(signals(5)[0],v.fixed_models())
        for n in v.NAMES:self.assertTrue(v.np.array_equal(a[n],b[n][:len(a[n])],equal_nan=True))

    def test_new_unrecovered_and_false_stop_detected(self):
        base={'n':20,'coverage':1.,'rmse':.1,'false_stop_samples':0,'event_rmse':.1,'recovery_s':.2}
        changed=dict(base,false_stop_samples=1,recovery_s=None)
        row={'bag':'fake','runtime':{n:{'causal_errors':0,'resets':0} for n in v.NAMES},'receivers':{'master':{'main':base,'disturbance_070':changed}}}
        reasons=v.individual_gates({'original':[row]})
        self.assertTrue(any(x.startswith('false_stop:') for x in reasons))
        self.assertTrue(any(x.startswith('new_unrecovered:') for x in reasons))

    def test_zero_reference_not_confused_with_missing(self):
        m=v.e.ex.metrics(v.np.array([0.,.05]),v.np.array([0.,0.]),v.np.array([0.,0.]),v.np.array([True,True]))
        self.assertEqual(m['n'],2);self.assertEqual(m['rmse'],0.)

    def test_published_fingerprint_is_not_arbitrary(self):
        p,_=gate_fixture()
        self.assertFalse(v.fingerprint(p)['passed'])

    def test_selected_schema_required_by_ros_probe(self):
        p=json.loads((v.TARGET/'selected.json').read_text())
        self.assertEqual(p['config']['disturbance_limit_mps2'],.7000000000000001)
        self.assertEqual(p['readout'],{'gain':1.0,'holdoff_s':.5})

    def test_complete_worker_with_synthetic_inputs(self):
        events,refs=signals()
        class FakeStore:
            def __init__(self,root):
                self.records={'30618_synthetic':{'group':'synthetic','sha256':'synthetic-only'}}
                self.access=[{'purpose':'synthetic_fixture'}]
            def load(self,bag):return events,refs
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'arrays').mkdir();(out/'bags').mkdir()
            with patch.object(v,'ValidationStore',FakeStore):
                row=v.worker(('30618_synthetic','/not-real',out))
            self.assertEqual(len(row['stress']),4)
            self.assertEqual(len(row['full']),4)
            self.assertTrue((out/'bags/30618_synthetic.json').exists())
            report=v.summarize([row])
            self.assertEqual(report['status'],'VALIDATION_REJECTED')
            self.assertIn('baseline_fingerprint',report['reasons'])
            self.assertFalse(report['ready_to_merge'])

    def test_ros_fault_adapter_selects_exact_profile(self):
        source="proc=['guarded_odometry_node',"+ros.PARAM_EXPR+"]"
        changed=ros.fault_probe_source(source,'/tmp/selected.yaml')
        self.assertIn('/tmp/selected.yaml',changed)
        self.assertNotIn(ros.PARAM_EXPR,changed)
        with self.assertRaises(ValueError):ros.fault_probe_source('old unguarded probe','/tmp/x')

    def test_ros_clock_profile_changes_only_clock(self):
        text=(v.TARGET/'v8_residual070.yaml').read_text()
        changed=ros.clock_yaml(text)
        self.assertEqual(changed.replace('    clock_mode: ros_clock','    clock_mode: input_stamp'),text)
        with self.assertRaises(ValueError):ros.clock_yaml('no clock')

    def test_archive_hash_failure_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'bad.zip';archive.write_bytes(b'not organizer data')
            with self.assertRaises(ValueError):prep.prepare(archive,Path(tmp)/'out')
            self.assertFalse((Path(tmp)/'out').exists())


if __name__=='__main__':unittest.main()
