"""Verify the published final evidence without reopening any raw measurement."""
import hashlib
import json
from pathlib import Path
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[1]


class SubmissionIntegrityTests(unittest.TestCase):
    def test_published_archive_and_report_are_identical(self):
        path=ROOT/'submission/FREEZE.json'
        frozen=json.loads(path.read_text())
        final=json.loads((ROOT/'reports/final/test/results.json').read_text())
        archive=ROOT/'submission/dist/reserve-odometry-v4.zip'
        expected=archive.with_suffix('.sha256').read_text().split()[0]
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),expected)
        # Final-test evidence belongs to the immutable published release, while
        # current development sources may contain later validated fixes.
        with zipfile.ZipFile(archive) as release:
            for name,digest in frozen['source_sha256'].items():
                self.assertEqual(hashlib.sha256(release.read('reserve-odometry-v4/'+name)).hexdigest(),digest,name)
        self.assertEqual(final['source_sha256'],frozen['source_sha256'])
        self.assertEqual(final['freeze_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(final['test_evaluated'])

    def test_all_22_test_bags_were_logged_once(self):
        frozen=json.loads((ROOT/'submission/FREEZE.json').read_text())
        final=json.loads((ROOT/'reports/final/test/results.json').read_text())
        access=json.loads((ROOT/'reports/final/test/access.json').read_text())['access']
        self.assertEqual(len(frozen['test_bags']),22)
        self.assertEqual(sorted(row['bag'] for row in final['clean']),sorted(frozen['test_bags']))
        self.assertEqual(sorted(row['bag'] for row in access),sorted(frozen['test_bags']))
        self.assertTrue(all(row['purpose']=='final_test' for row in access))
        self.assertEqual(final['operational'],frozen['operational'])

if __name__=='__main__':unittest.main()
