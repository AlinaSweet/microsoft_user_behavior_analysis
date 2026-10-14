import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from user_behavior_analysis.artifacts import check_git_files, register, sha256_file, SMALL_FILE_LIMIT
from user_behavior_analysis.runtime import ROOT, load_config, read_sample, resolve_source, resource_plan


class StageOneTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.cache/tests').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.cache/tests')
        self.root = Path(self.temp.name)
        self.csv = self.root / 'sample.csv'
        self.csv.write_text('time,user_id,item_id,item_category,behavior_type\n2025-12-06 02,001,0002,004,1\n', encoding='utf-8')
        self.config = load_config()

    def tearDown(self):
        self.temp.cleanup()

    def test_cli_path_beats_environment_and_environment_beats_default(self):
        self.config['data']['default_path'] = 'missing.csv'
        self.assertEqual(resolve_source(self.config, env={'USER_BEHAVIOR_CSV': str(self.csv)}), self.csv)
        self.assertEqual(resolve_source(self.config, str(self.csv), {'USER_BEHAVIOR_CSV': 'missing.csv'}), self.csv)

    def test_bad_csv_header_is_rejected(self):
        self.csv.write_text('user_id,item_id\n1,2\n')
        with self.assertRaisesRegex(ValueError, 'columns differ'):
            resolve_source(self.config, str(self.csv))

    def test_id_leading_zeros_survive(self):
        frame = read_sample(str(self.csv), 1, 'utf-8', self.config['data']['columns'])
        self.assertEqual(frame.loc[0, 'user_id'], '001')
        self.assertEqual(frame.loc[0, 'item_id'], '0002')

    def test_resource_plan_stays_within_available_budget(self):
        plan = resource_plan(self.config, available=1200 * 1024**2, cpu_count=2)
        self.assertEqual(plan['n_workers'], 1)
        self.assertLessEqual(plan['total_worker_budget_bytes'], int(1200 * 1024**2 * 0.70))
        self.assertGreaterEqual(plan['memory_limit_bytes'], 512 * 1024**2)

    def test_insufficient_memory_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'memory is too low'):
            resource_plan(self.config, available=100 * 1024**2, cpu_count=1)

    def test_unordered_thresholds_are_rejected(self):
        import yaml
        config = copy.deepcopy(self.config)
        config['distributed']['worker']['memory']['pause'] = 0.60
        path = self.root / 'bad.yaml'
        path.write_text(yaml.safe_dump(config))
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            load_config(path)

    def test_manifest_detects_changed_content_without_copying_data(self):
        output, payload = register(self.csv, 'sample', 'raw', 'test source', root=self.root)
        self.assertEqual(json.loads(output.read_text())['sha256'], sha256_file(self.csv))
        self.assertEqual(payload['distribution_status'], 'local_only')
        before = payload['sha256']
        self.csv.write_text('different data\n')
        self.assertNotEqual(before, sha256_file(self.csv))

    def test_manifest_name_cannot_escape_catalog(self):
        with self.assertRaises(ValueError):
            register(self.csv, '../outside', 'raw', 'test', root=self.root)

    def test_git_policy_rejects_large_files_and_raw_data(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        large = self.root / 'large.bin'
        with large.open('wb') as handle:
            handle.truncate(SMALL_FILE_LIMIT + 1)
        raw = self.root / 'data/raw/source.csv'
        raw.parent.mkdir(parents=True)
        raw.write_text('raw\n')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        issues = check_git_files(self.root)['issues']
        self.assertTrue(any('exceeds 10 MiB' in issue for issue in issues))
        self.assertTrue(any('Large data directory' in issue for issue in issues))

    def test_small_csv_is_tracked_and_large_data_and_environments_are_ignored(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / '.gitignore').write_text((ROOT / '.gitignore').read_text())
        for name in ('outputs/reports/summary.csv', 'data/interim/large.csv', '.venv-repro/cache'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('example')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        tracked = subprocess.check_output(['git', 'ls-files'], cwd=self.root, text=True)
        self.assertIn('outputs/reports/summary.csv', tracked)
        self.assertNotIn('data/interim/large.csv', tracked)
        self.assertNotIn('.venv-repro/cache', tracked)

    def test_manifest_records_actual_git_tracking_status(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', 'add', 'sample.csv'], cwd=self.root, check=True)
        _, payload = register(self.csv, 'tracked_sample', 'interim', 'test input', root=self.root)
        self.assertTrue(payload['data_file_in_git'])


if __name__ == '__main__':
    unittest.main()
