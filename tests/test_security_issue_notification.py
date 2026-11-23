import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'scripts' / 'notify_security_issue.py'
spec = importlib.util.spec_from_file_location('cir_security_notification', FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SecurityIssueNotificationTests(unittest.TestCase):
    def invoke(self, existing, result):
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ('issue', 'list'):
                import json
                return json.dumps(existing)
            return ''
        with patch.dict(os.environ, {'GH_TOKEN': 'test-token'}), patch.object(mod, 'gh', side_effect=fake_gh):
            mod.notify('[CIR security] Review', result,
                       'https://github.com/example/repo/actions/runs/123',
                       'amd64/arm64 review', 'example/repo')
        return calls

    def test_failure_creates_issue(self):
        self.assertTrue(any(x[:2] == ('issue','create') for x in self.invoke([], 'failure')))

    def test_repeat_failure_comments(self):
        calls=self.invoke([{'number':12,'title':'[CIR security] Review','state':'OPEN'}], 'failure')
        self.assertTrue(any(x[:2] == ('issue','comment') for x in calls))
        self.assertFalse(any(x[:2] == ('issue','create') for x in calls))

    def test_success_closes_existing_issue(self):
        self.assertTrue(any(x[:2] == ('issue','close') for x in self.invoke([{'number':12,'title':'[CIR security] Review','state':'OPEN'}], 'success')))

    def test_success_does_not_create_issue(self):
        self.assertFalse(any(x[:2] == ('issue','create') for x in self.invoke([], 'success')))

    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError):
            mod.notify('t','failure','http://unsafe','context','example/repo')
