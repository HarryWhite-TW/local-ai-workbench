"""Confirmation gates only; real native/browser evidence is separate."""
import threading
import time
import unittest
from unittest.mock import Mock

from src.companion_core.engineering_pilot import EngineeringPilot
from src.companion_core.siwc import ChatError


class ConfirmationGates(unittest.TestCase):
    def setUp(self):
        self.pilot = object.__new__(EngineeringPilot)
        self.pilot.lock = threading.RLock()
        self.pilot.worker = None
        self.job = {'id': 'job', 'state': 'PREVIEW', 'expires': time.time()+60,
                    'token': 'preview-token', 'source': {'calculator.py': 'before'}}
        self.pilot.get = Mock(return_value=self.job)
        self.pilot.snapshot = Mock(return_value=dict(self.job['source']))
        self.pilot.save = Mock()
        self.body = {'id': 'job', 'token': 'preview-token', 'authority': 'ISOLATED_SAMPLE_WRITE'}

    def rejected(self):
        with self.assertRaises(ChatError):
            self.pilot.confirm(self.body)
        self.pilot.save.assert_not_called()
        self.assertIsNone(self.pilot.worker)

    def test_readonly_approval_cannot_grant_write(self):
        self.body['authority'] = 'READ_ONLY'
        self.rejected()

    def test_preview_token_cannot_be_guessed(self):
        self.body['token'] = 'other'
        self.rejected()

    def test_expired_preview_cannot_start(self):
        self.job['expires'] = time.time()-1
        self.rejected()

    def test_changed_source_invalidates_approval(self):
        self.pilot.snapshot.return_value = {'calculator.py': 'changed'}
        self.rejected()

    def test_consumed_confirmation_cannot_run_again(self):
        self.job['state'] = 'COMPLETED'
        self.rejected()

    def test_owner_guard_runs_before_confirmation(self):
        self.pilot.get.side_effect = ChatError('wrong account')
        self.rejected()


if __name__ == '__main__':
    unittest.main()
