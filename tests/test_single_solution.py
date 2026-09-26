"""Packaging-only consolidation must not mutate the selected numerical model."""
import ast
import hashlib
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'src/reserve_odometry'

class SingleSolutionTests(unittest.TestCase):
    def setup_arguments(self):
        with patch('setuptools.setup') as call:
            runpy.run_path(str(PKG/'setup.py'))
        return call.call_args.kwargs

    def test_one_entrypoint(self):
        self.assertEqual(self.setup_arguments()['entry_points']['console_scripts'],
                         ['guarded_odometry_node = reserve_odometry.guarded_node:main'])

    def test_one_installed_launch_and_config(self):
        data=dict(self.setup_arguments()['data_files'])
        self.assertEqual(data['share/reserve_odometry/launch'],['launch/odometry.launch.py'])
        self.assertEqual(data['share/reserve_odometry/config'],['config/champion_v8.yaml'])
        for values in data.values():
            for path in values:self.assertTrue((PKG/path).is_file(),path)

    def test_numerical_runtime_and_profile_unchanged(self):
        pin=json.loads((ROOT/'research/adjudication/SELECTED_SOURCE.json').read_text())
        for path,expected in pin['sha256'].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected)

    def test_build_and_run_use_isolated_prefix(self):
        for file in ('submission/build.sh','submission/run.sh'):
            self.assertIn('install_main/setup.bash',(ROOT/file).read_text())
        self.assertNotIn('source install/setup.bash',(ROOT/'submission/run.sh').read_text())

    def test_launch_points_to_only_installed_entrypoint(self):
        text=(PKG/'launch/odometry.launch.py').read_text()
        self.assertIn("executable='guarded_odometry_node'",text)
        self.assertIn('champion_v8.yaml',text)

if __name__=='__main__':unittest.main()
