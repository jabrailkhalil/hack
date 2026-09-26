import unittest
from unittest.mock import patch
from test_command_map import ROOT
from common import profile, ev, np
import develop as d
from fit import decode, encode, data_residual, weights


class DriverTests(unittest.TestCase):
    def test_monotone_parameterization(self):
        for a in ([0]*6,[1]*6,[.1,.8,.5,.9,.2,.1]):
            q=decode(np.asarray(a));self.assertTrue(all(0<=x<=1 for x in q))
            self.assertTrue(q[0]<=q[1]<=q[2] and q[3]<=q[4]<=q[5])
        c,_,_=profile();q=np.tile(np.array([.25,.5,.75])**c.command_exponent,2)
        np.testing.assert_allclose(decode(encode(q)),q,atol=1e-15)

    def test_exact_robust_normalization(self):
        target=np.zeros((3,2));pred=np.array([[.3,-.2],[.5,.1],[2.,-1.]])
        meta=[dict(group='a'),dict(group='a'),dict(group='b')];w=weights(meta)
        r=pred/np.array([.2,.5]);expected=np.sum(w*2*(np.sqrt(1+r*r)-1))
        self.assertAlmostEqual(float(np.sum(data_residual(pred,target,w)**2)),float(expected))
        self.assertAlmostEqual(float(np.sum(np.broadcast_to(w,(3,2)))),1.)

    def test_role_denial_before_sqlite(self):
        s=d.DevelopmentStore()
        with patch('sqlite3.connect',side_effect=AssertionError('IO must be denied')):
            for role in ('train','validation','test'):
                with self.assertRaises(PermissionError):s.load(s.plan['splits'][role][0],role)
            with self.assertRaises(PermissionError):s.load(s.plan['splits']['validation'][0],'development')

    def test_unchanged_does_not_count_as_regression(self):
        self.assertFalse(d.increased(.1,.1,.005));self.assertTrue(d.increased(.101,.1,.005))
        self.assertFalse(d.increased(0.,0.,.005));self.assertTrue(d.increased(.001,0.,.005))
        self.assertTrue(d.increased(None,1.,.005))

    def test_individual_recovery_veto(self):
        b=dict(n=20,coverage=1.,rmse=.1,event_rmse=.2,recovery_s=.1,false_stop_samples=0)
        a=b|{'recovery_s':None}
        row=dict(bag='synthetic',fault=dict(kind='dropout',start=1,end=2),receivers={'master':{'main':b,'x':a}})
        self.assertTrue(any('individual_unrecovered' in r for r in d.row_veto([row],'x')))

    def test_canonical_off_official_scorer(self):
        c,_,_=profile();q=[float(x**c.command_exponent) for x in (.25,.5,.75)]
        fit={n:dict(command_map=dict(traction=q,braking=q,enabled=True)) for n in d.CANDIDATES}
        events=np.asarray([(float(t),ch,(.3 if ch==0 else 4+.2*t)) for t in np.arange(0,4,.1) for ch in range(3)])
        refs={'master':[(float(t),4+.2*t) for t in np.arange(0,4,.05)],'rover':[]}
        out,col=d.score(events,refs,fit,official_check=True)
        self.assertTrue(out['baseline_reproduced_with_direct_factory'])
        self.assertEqual(out['receivers']['master']['main']['n'],out['receivers']['master']['off']['n'])
        self.assertIsNone(out['receivers']['rover']['main']['rmse'])
        self.assertTrue(all(out['runtime'][n]['causal_errors']==0 for n in d.NAMES))

    def test_fault_anchors_preserve_legacy_rule(self):
        events=np.asarray([(float(t),ch,(.3 if ch==0 else 1.5)) for t in np.arange(0,80,.1) for ch in range(3)])
        low=list(d.low_speed_windows(events));self.assertEqual(len(low),2)
        self.assertAlmostEqual(low[0][0]['start'],25.1)
        self.assertEqual([round(f['end']-f['start']) for f,w in low],[3,5])


if __name__=='__main__':unittest.main()
