from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay as r


def fixture(seconds=70):
    # Generated signals only: not a bag, not a speed-accuracy benchmark.
    events = []
    for i in range(seconds*10+1):
        t = i*.1
        u = .2 if t < 32 else -.1
        events.extend([(t, 0, u), (t, 1, 3.), (t, 2, 3.)])
    refs = {'master': [(i*.05, 3.) for i in range(seconds*20+1)], 'rover': []}
    return r.np.asarray(events), refs


class ReplayTests(unittest.TestCase):
    def test_only_development_authorized_before_io(self):
        store = r.DevelopmentStore('/does-not-exist')
        with patch.object(r.sqlite3, 'connect', side_effect=AssertionError('SQL must not run')):
            with patch.object(r.ev, 'sha', side_effect=AssertionError('DB must not be read')):
                for role in ('train', 'validation', 'test'):
                    bag = store.plan['splits'][role][0]
                    with self.assertRaises(PermissionError): store.load(bag)
                bag = store.plan['splits']['development'][0]
                with self.assertRaises(PermissionError): store.load(bag, 'validation')

    def test_clean_adapter_exact_and_missing_reference_retained(self):
        events, refs = fixture(5)
        arrays, info = r.predictions(events)
        actual = r.score_full(arrays, info, refs)
        expected = r.g.compare(events, refs, r.rt.models())
        self.assertEqual(actual['receivers'], expected['receivers'])
        self.assertEqual(actual['runtime'], expected['runtime'])
        for value in actual['receivers']['rover'].values():
            self.assertIsNone(value['rmse'])
            self.assertEqual(value['n'], 0)
        for name in r.rt.NAMES:
            summary = r.v6.summary([dict(actual, group='fixture')], [], name)
            self.assertIn('samples', summary)

    def test_original_four_faults_and_full_integrals(self):
        events, refs = fixture()
        clean, _ = r.predictions(events)
        faults = list(r.g.fault_windows(events))
        self.assertEqual(len(faults), 4)
        for fault, window in faults:
            result = r.g.compare(window, refs, r.rt.models(), fault)
            self.assertGreater(result['outputs'], 0)
            changed, _ = r.predictions(events, fault)
            retained = r.retained_displacement(clean, changed, fault)
            for profile in retained.values():
                self.assertLess(profile['max_integral_identity_error_m'], 1e-7)
                self.assertIsNotNone(profile['end_plus_10_delta_s_m'])

    def test_output_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError): r.run('/missing', Path(directory))

    def test_future_extension_preserves_prefix(self):
        short, _ = fixture(10); longer, _ = fixture(20)
        a, _ = r.predictions(short); b, _ = r.predictions(longer)
        for name in r.rt.NAMES:
            count = len(a[name])
            self.assertTrue(r.np.array_equal(a[name], b[name][:count], equal_nan=True))

    def test_prefault_change_detected(self):
        events, _ = fixture(5)
        clean, _ = r.predictions(events)
        changed = {name: a.copy() for name, a in clean.items()}
        changed['candidate'][0, 2] += 1
        with self.assertRaises(AssertionError):
            r.retained_displacement(clean, changed, {'start': 1., 'end': 2.})


if __name__ == '__main__': unittest.main()
