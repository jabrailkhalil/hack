"""JSON-boundary regression tests; no data, fitting or selection policy changes."""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver

class TestSerialization(unittest.TestCase):
    def test_scalar_types_and_values(self):
        value = {'count': np.int64(13), 'passed': np.bool_(True), 'fraction': np.float64(.5), 'tuple': (np.int32(2), None)}
        result = driver.native_scalars(value)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), {'count': 13, 'passed': True, 'fraction': .5, 'tuple': [2, None]})
        self.assertIs(type(result['count']), int)
        self.assertIs(type(result['passed']), bool)

    def test_json_write_once_and_no_nan(self):
        with TemporaryDirectory() as t:
            p = Path(t)/'receipt.json'
            driver.write(p, {'material_fit_groups': np.int64(13)})
            self.assertEqual(json.loads(p.read_text()), {'material_fit_groups': 13})
            with self.assertRaises(FileExistsError):
                driver.write(p, {})
            with self.assertRaises(ValueError):
                driver.write(Path(t)/'invalid.json', {'value': np.float64('nan')})

    def test_source_binding(self):
        sources = driver.source_files()
        self.assertIn('research/R6/H57/driver.py', sources)
        self.assertIn('research/R6/H57/run.py', sources)
        self.assertEqual(len(sources), 5)
        self.assertEqual(sources, driver.implementation.source_files())

if __name__ == '__main__':
    unittest.main()
