"""Confirmation gates only; real native/browser evidence is separate."""
import threading
import time
import unittest
from unittest.mock import Mock
from pathlib import Path
import tempfile
from types import SimpleNamespace

from src.companion_core.engineering_pilot import EngineeringPilot
from src.companion_core.siwc import ChatError
from src.companion_core.chat import Conversations


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


class LocalPreview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.workspace = root / 'project'
        self.workspace.mkdir()
        state = root / 'state'; state.mkdir()
        fixture = root / 'fixture'; fixture.mkdir()
        for name, value in {'calculator.py': 'def average(v): return sum(v)/len(v)\n',
                            'test_calculator.py': 'import unittest\n',
                            'AGENTS.md': 'Only edit calculator.py\n'}.items():
            (fixture / name).write_text(value, encoding='utf8')
        self.auth = SimpleNamespace(pending=None, lock=threading.RLock(),
                                   vault=SimpleNamespace(data={'active': 'synthetic-owner'}))
        self.chat = Conversations(self.workspace, state, self.auth)
        self.pilot = EngineeringPilot(self.chat, fixture, 'unused-codex.exe')

    def test_new_preview_creates_same_owner_local_chat_without_model(self):
        job = self.pilot.respond('preview', {'chat': None, 'question': 'Fix empty average'})
        saved = self.chat.get(job['chat'])
        self.assertEqual(saved['account'], 'synthetic-owner')
        self.assertEqual(saved['turns'][0]['id'], job['turn'])
        self.assertEqual(saved['turns'][0]['model'], 'NEXUS · 工程試點')
        self.assertEqual(self.pilot.state({'chat': job['chat']})[0]['state'], 'PREVIEW')
        self.assertIsNone(self.pilot.worker)
        self.assertIsNone(self.chat.worker)
        reopened = EngineeringPilot(self.chat, self.pilot.root, 'unused-codex.exe')
        self.assertEqual(reopened.get(job['id'])['chat'], job['chat'])

    def test_existing_chat_is_reused_and_foreign_owner_is_rejected(self):
        first = self.pilot.respond('preview', {'chat': None, 'question': 'First local preview'})
        second = self.pilot.respond('preview', {'chat': first['chat'], 'question': 'Same conversation'})
        self.assertEqual(second['chat'], first['chat'])
        self.assertEqual(len(self.chat.get(first['chat'])['turns']), 2)
        self.auth.vault.data['active'] = 'another-owner'
        with self.assertRaises(ChatError):
            self.pilot.respond('preview', {'chat': first['chat'], 'question': 'Foreign preview'})

    def test_signed_out_or_pending_cannot_create_local_chat(self):
        for active, pending in [(None, None), ('synthetic-owner', object())]:
            self.auth.vault.data['active'], self.auth.pending = active, pending
            with self.assertRaises(ChatError):
                self.pilot.respond('preview', {'chat': None, 'question': 'Not authorized'})
        with self.chat.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chats').fetchone()[0], 0)

    def test_invalid_goal_creates_no_partial_conversation(self):
        with self.assertRaises(ChatError):
            self.pilot.respond('preview', {'chat': None, 'question': '   '})
        with self.chat.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chats').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
