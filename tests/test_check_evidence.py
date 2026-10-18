import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/check-evidence.py'
spec = importlib.util.spec_from_file_location('evidence', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NOW = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b'{"tests":{"passed":3,"ran":true},"a/b":{"~value":null}}\n'
        (self.root / 'result.json').write_bytes(self.data)
        self.item = {'id':'tests', 'claim':'The test report records three passing tests',
                     'kind':'json_equals','path':'result.json',
                     'sha256':hashlib.sha256(self.data).hexdigest(),
                     'pointer':'/tests/passed','expected':3}
        self.manifest = {'version':1,'task':'Review output','recorded_at':'2026-10-17T00:00:00Z',
                         'valid_until':'2026-10-19T00:00:00Z','criteria':[self.item]}

    def result(self):
        return m.check(self.manifest, self.root, NOW)

    def status(self):
        return self.result()['criteria'][0]['status']

    def test_matching_record_never_certifies_task_or_event(self):
        report = self.result()
        self.assertEqual(report['task_acceptance'], 'not_assessed')
        self.assertEqual(report['authorization'], 'not_assessed')
        self.assertEqual(self.status(), 'recorded_value_matched')
        self.assertIn('underlying event not verified', report['criteria'][0]['reason'])

    def test_hash_match_not_semantic_success(self):
        self.item['kind'] = 'artifact_sha256'
        del self.item['pointer'], self.item['expected']
        self.assertEqual(self.status(), 'artifact_identity_matched')

    def test_changed_bytes_mismatch(self):
        (self.root / 'result.json').write_text('{"tests":{"passed":3}}')
        self.assertEqual(self.status(), 'mismatch')

    def test_missing_artifact_unknown(self):
        (self.root / 'result.json').unlink()
        self.assertEqual(self.status(), 'unknown')

    def test_wrong_value_mismatch(self):
        self.item['expected'] = 4
        self.assertEqual(self.status(), 'mismatch')

    def test_type_bool_not_int(self):
        self.item.update(pointer='/tests/ran', expected=1)
        self.assertEqual(self.status(), 'mismatch')

    def test_escaped_pointer(self):
        self.item.update(pointer='/a~1b/~0value', expected=None)
        self.assertEqual(self.status(), 'recorded_value_matched')

    def test_missing_pointer_unknown(self):
        self.item['pointer'] = '/missing'
        self.assertEqual(self.status(), 'unknown')

    def test_malformed_json_unknown_even_matching_hash(self):
        for data in (b'{', b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff'):
            with self.subTest(data=data):
                (self.root / 'result.json').write_bytes(data)
                self.item['sha256'] = hashlib.sha256(data).hexdigest()
                self.assertEqual(self.status(), 'unknown')

    def test_stale_and_future_evidence_unknown(self):
        for now in (NOW - dt.timedelta(days=2), NOW + dt.timedelta(days=1)):
            self.assertEqual(m.check(self.manifest,self.root,now)['criteria'][0]['status'], 'unknown')

    def test_declared_window_never_attests_record_creation(self):
        self.assertEqual(self.result()['scope'], 'local artifact observations only')

    def test_human_claim_never_passed(self):
        self.manifest['criteria'] = [{'id':'useful','claim':'Meets the actual user need','kind':'human_review'}]
        self.assertEqual(self.status(), 'human_review_required')

    def test_paths_are_bounded(self):
        for path in ('../result.json','/etc/passwd','a/../../result.json','./result.json',
                     'a//result.json','a\\result.json','SENSITIVE_fixture',
                     'knowledge_base/data.json','.hidden','a/../result.json'):
            with self.subTest(path=path):
                self.item['path'] = path
                self.assertEqual(self.status(), 'unknown')

    def test_symlink_file_denied(self):
        (self.root / 'link').symlink_to('result.json')
        self.item['path'] = 'link'
        self.assertEqual(self.status(), 'unknown')

    def test_symlink_directory_denied(self):
        (self.root / 'alias').symlink_to(self.root, target_is_directory=True)
        self.item['path'] = 'alias/result.json'
        self.assertEqual(self.status(), 'unknown')

    def test_directory_not_read(self):
        (self.root / 'folder').mkdir()
        self.item['path'] = 'folder'
        self.assertEqual(self.status(), 'unknown')

    def test_fifo_not_blocking(self):
        os.mkfifo(self.root / 'pipe')
        self.item['path'] = 'pipe'
        self.assertEqual(self.status(), 'unknown')

    def test_oversize_artifact_denied(self):
        (self.root / 'result.json').write_bytes(b'x' * (m.LIMIT + 1))
        self.assertEqual(self.status(), 'unknown')

    def test_invalid_schemas_fail_closed(self):
        changes = ({'criteria':[]},{'version':True},{'version':2},
                   {'recorded_at':'2026-10-17'}, {'valid_until':'2026-10-16T00:00:00Z'},
                   {'criteria':[self.item,self.item]}, {'command':'touch unwanted'})
        for change in changes:
            with self.subTest(change=change):
                manifest = copy.deepcopy(self.manifest)
                manifest.update(change)
                with self.assertRaises(ValueError): m.check(manifest,self.root,NOW)

    def test_untrusted_command_never_executed(self):
        self.item.update(kind='shell', command='touch unwanted')
        with self.assertRaises(ValueError): self.result()
        self.assertFalse((self.root / 'unwanted').exists())

    def test_manifest_rejects_unknown_fields(self):
        self.item['reported_success'] = True
        with self.assertRaises(ValueError): self.result()

    def test_exact_decimal_comparisons(self):
        for actual, expected in [('9007199254740993.0', '9007199254740992.0'),
                                 ('1e-10000', '0.0'), ('1.0', '1'), ('true', '1')]:
            with self.subTest(actual=actual, expected=expected):
                self.assertFalse(m.equal_json(m.strict_json(actual), m.strict_json(expected)))
        self.assertTrue(m.equal_json(m.strict_json('1.00'), m.strict_json('1.0')))

    def test_unrepresentable_decimal_exponents_rejected(self):
        for value in ('1e999999999999999999999999', '1e-999999999999999999999999'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): m.strict_json(value)

    def test_extreme_timezone_overflow_is_invalid(self):
        for stamp in ('0001-01-01T00:00:00+23:59', '9999-12-31T23:59:59-23:59'):
            with self.subTest(stamp=stamp):
                self.manifest['recorded_at'] = stamp
                (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
                run = subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),
                                      '--manifest','manifest.json'],capture_output=True,text=True)
                self.assertEqual(run.returncode, 2, run.stderr)
                report = json.loads(run.stdout)
                self.assertEqual(report['task_acceptance'], 'not_assessed')
                self.assertEqual(report['authorization'], 'not_assessed')
                self.assertNotIn('Traceback', run.stderr)

    def test_cli_invalid_manifest_exit_two(self):
        (self.root / 'manifest.json').write_text('{"version":1,"version":1}')
        run = subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),
                              '--manifest','manifest.json'],capture_output=True,text=True)
        self.assertEqual(run.returncode,2)
        self.assertEqual(json.loads(run.stdout)['task_acceptance'],'not_assessed')

    def test_cli_report_does_not_modify_evidence(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.manifest['recorded_at'] = (now-dt.timedelta(hours=1)).isoformat()
        self.manifest['valid_until'] = (now+dt.timedelta(hours=1)).isoformat()
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        run = subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),
                              '--manifest','manifest.json'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0)
        self.assertIn('manifest_sha256',json.loads(run.stdout))
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_cli_missing_artifact_exit_one(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.manifest['recorded_at'] = (now-dt.timedelta(hours=1)).isoformat()
        self.manifest['valid_until'] = (now+dt.timedelta(hours=1)).isoformat()
        (self.root / 'result.json').unlink()
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        run = subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),
                              '--manifest','manifest.json'],capture_output=True,text=True)
        self.assertEqual(run.returncode,1)


if __name__ == '__main__': unittest.main()
