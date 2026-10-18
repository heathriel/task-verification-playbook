"""Offline regression tests: python3 -m unittest discover -s tests -v."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'quality-trend.sh'


class QualityTrendTests(unittest.TestCase):
    def run_report(self, artifacts):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'work-records' / 'completions'
            root.mkdir(parents=True)
            for name, (content, days) in artifacts.items():
                path = root / name
                path.write_text(content)
                modified = time.time() - days * 86400
                os.utime(path, (modified, modified))
            result = subprocess.run(['bash', str(SCRIPT)], cwd=directory,
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            return result.stdout

    def test_blank_and_blocked_are_not_zero(self):
        report = self.run_report({
            'good.md': ('**Overall: 9.75/10**\n', 0),
            'blank.md': ('**Overall: __/10**\n', 0),
            'blocked.md': ('**Overall: N/A (BLOCKED)**\n', 0),
        })
        self.assertEqual(report.count('Average quality score: 9.75/10'), 2)
        self.assertIn('1 scored, 2 unscored', report)
        self.assertNotIn('all recent tasks scored', report)

    def test_no_numeric_scores(self):
        report = self.run_report({'blank.md': ('**Overall: __/10**\n', 0)})
        self.assertEqual(report.count('Average quality score: N/A'), 2)
        self.assertNotIn('all recent tasks scored', report)

    def test_integer_low_score_and_unusual_filename(self):
        name = "task with spaces ' quote\nand newline.md"
        report = self.run_report({name: ('Overall: 7/10\n', 0),
                                  'eight.md': ('**Overall: 8.0/10**\n', 0)})
        self.assertEqual(report.count('Average quality score: 7.50/10'), 2)
        self.assertIn(name + ': 7/10', report)
        self.assertNotIn('eight.md:', report)

    def test_integer_low_score(self):
        report = self.run_report({'integer.md': ('Overall: 7/10\n', 0)})
        self.assertIn('integer.md: 7/10', report)

    def test_generated_template_is_unscored(self):
        generator = SCRIPT.with_name('generate-scorecard.sh')
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['bash', str(generator), 'example'], cwd=directory,
                           check=True, capture_output=True, timeout=5)
            report = subprocess.run(['bash', str(SCRIPT)], cwd=directory,
                                    check=True, capture_output=True, text=True,
                                    timeout=5).stdout
            self.assertIn('0 scored, 1 unscored', report)
            self.assertEqual(report.count('Average quality score: N/A'), 2)

    def test_time_windows(self):
        report = self.run_report({'week.md': ('Overall: 9/10\n', 0),
                                  'month.md': ('Overall: 7.5/10\n', 10),
                                  'old.md': ('Overall: 1/10\n', 40)})
        self.assertIn('Average quality score: 8.25/10', report)
        self.assertIn('Average quality score: 9.00/10', report)
        self.assertNotIn('month.md:', report)
        self.assertNotIn('old.md:', report)

    def test_invalid_scores_and_mentions_are_excluded(self):
        report = self.run_report({
            'high.md': ('Overall: 11/10\n', 0),
            'negative.md': ('Overall: -1/10\n', 0),
            'bad.md': ('Overall: 7abc/10\n', 0),
            'mention.md': ('The old Overall: 2/10 was revised.\nOverall: 10/10\n', 0),
        })
        self.assertEqual(report.count('Average quality score: 10.00/10'), 2)
        self.assertIn('1 scored, 3 unscored', report)

    def test_one_score_per_artifact(self):
        report = self.run_report({'one.md': ('Overall: 8/10\nOverall: 2/10\n', 0)})
        self.assertEqual(report.count('Average quality score: 8.00/10'), 2)

    def test_no_artifacts(self):
        self.assertIn('No completion artifacts found', self.run_report({}))


if __name__ == '__main__':
    unittest.main()
