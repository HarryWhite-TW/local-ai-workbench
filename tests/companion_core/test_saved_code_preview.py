"""Synthetic saved messages; no model, DPAPI, Windows handle or host apply."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from src.companion_core.chat import now
from src.companion_core.controlled_code import BASE, TARGET
from src.companion_core.siwc import ChatError
from tests.companion_core.test_controlled_code import make_engine, approval


class SavedPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = make_engine(Path(self.temp.name))
        self.engine.run = Mock(side_effect=AssertionError('Preview must never call model'))
        self.engine.apply = Mock(side_effect=AssertionError('Preview must never write source'))
        self.raw = (self.engine.root/TARGET).read_bytes()
        self.engine.snapshot = Mock(return_value={
            'target': TARGET, 'root': str(self.engine.root), 'head': BASE, 'text': self.raw.decode(),
            'sha256': hashlib.sha256(self.raw).hexdigest(), 'identity': ['synthetic']})
        with self.engine.chat.connect() as db:
            for ident, owner in [('other-chat', 'owner'), ('foreign-chat', 'other')]:
                db.execute('INSERT INTO chats VALUES (?,?,?,?,?)', (ident, self.engine.chat.workspace, owner, ident, now()))
            for ident, chat, status, model in [('saved', 'chat', 'complete', 'synthetic-chat-model'),
                    ('pending', 'chat', 'pending', 'synthetic-chat-model'),
                    ('failed', 'chat', 'failed', 'synthetic-chat-model'),
                    ('other-turn', 'other-chat', 'complete', 'synthetic-chat-model'),
                    ('foreign-turn', 'foreign-chat', 'complete', 'synthetic-chat-model'),
                    ('generated', 'chat', 'complete', 'NEXUS · 受控程式修改')]:
                db.execute('INSERT INTO turns (id,chat,question,answer,sources,model,created,status) VALUES (?,?,?,?,?,?,?,?)',
                    (ident, chat, ' Add a review copy button ', 'Saved answer', '[]', model, now(), status))
        self.body = {'chat': 'chat', 'turn': 'saved'}

    def tearDown(self):
        self.engine.run.assert_not_called()
        self.engine.apply.assert_not_called()
        self.assertIsNone(self.engine.worker)
        self.assertEqual((self.engine.root/TARGET).read_bytes(), self.raw)

    def test_backend_resolves_message_and_readback_survives_new_engine_instance(self):
        before = self.engine.chat.get('chat')['turns']
        job = self.engine.respond('preview', self.body)
        self.assertEqual(job['goal'], 'Add a review copy button')
        self.assertEqual(job['source_turn'], 'saved')
        self.assertEqual(job['turn'], 'saved')
        self.assertEqual(job['state'], 'PREVIEW')
        self.assertEqual(self.engine.chat.get('chat')['turns'], before)
        other = object.__new__(type(self.engine))
        other.__dict__.update(self.engine.__dict__)
        self.assertEqual(other.respond('state', {'chat': 'chat'}), [job])

    def test_parallel_duplicate_actions_reuse_one_preview(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = list(pool.map(lambda _: self.engine.respond('preview', self.body), range(4)))
        self.assertEqual(len({job['id'] for job in jobs}), 1)
        self.assertEqual(len(self.engine.respond('state', {'chat': 'chat'})), 1)

    def test_running_unknown_completed_and_failed_jobs_are_read_back_without_retry(self):
        job = self.engine.respond('preview', self.body)
        for state in ('RUNNING', 'UNKNOWN', 'COMPLETED', 'FAILED'):
            stored = self.engine.get(job['id']); stored['state'] = state
            self.engine.save(stored)
            current = self.engine.respond('preview', self.body)
            self.assertEqual((current['id'], current['state']), (job['id'], state))

    def test_expired_or_changed_source_requires_a_fresh_preview(self):
        first = self.engine.respond('preview', self.body)
        stored = self.engine.get(first['id']); stored['expires'] = time.time()-1
        self.engine.save(stored)
        second = self.engine.respond('preview', self.body)
        self.assertNotEqual(first['id'], second['id'])
        self.engine.snapshot.return_value = {**second['source'], 'identity': ['changed']}
        third = self.engine.respond('preview', self.body)
        self.assertNotEqual(second['id'], third['id'])
        with self.assertRaises(ChatError): self.engine.respond('confirm', approval(second))

    def test_invalid_foreign_or_unfinished_messages_and_spoofed_text_fail_closed(self):
        for body in ({'chat':'chat', 'turn':turn} for turn in
                     ('missing', 'pending', 'failed', 'other-turn', 'foreign-turn', 'generated', None)):
            with self.subTest(body=body), self.assertRaises(ChatError): self.engine.respond('preview', body)
        for extra in ({'question':'spoofed'}, {'target':'AGENTS.md'}):
            with self.assertRaises(ChatError): self.engine.respond('preview', {**self.body, **extra})
        self.assertEqual(self.engine.respond('state', {'chat':'chat'}), [])

    def test_account_pending_workspace_and_conversation_boundaries(self):
        job = self.engine.respond('preview', self.body)
        auth = self.engine.chat.auth
        for kind in ('account', 'pending', 'workspace'):
            old_workspace = self.engine.chat.workspace
            if kind == 'account': auth.vault.data['active'] = 'other'
            elif kind == 'pending': auth.pending = {'synthetic': True}
            else: self.engine.chat.workspace = 'other-workspace'
            with self.subTest(kind=kind):
                with self.assertRaises(ChatError): self.engine.respond('preview', self.body)
                with self.assertRaises(ChatError): self.engine.respond('state', {'chat':'chat'})
                with self.assertRaises(ChatError): self.engine.respond('confirm', approval(job))
            auth.vault.data['active'], auth.pending = 'owner', None
            self.engine.chat.workspace = old_workspace
        self.assertEqual(self.engine.respond('state', {'chat':'other-chat'}), [])

    def test_saved_turn_binding_and_independent_authority(self):
        job = self.engine.respond('preview', self.body)
        body = {**approval(job), 'authority':'READ_ONLY'}
        with self.assertRaises(ChatError): self.engine.respond('confirm', body)
        stored = self.engine.get(job['id']); stored['source_turn'] = 'other-turn'
        self.engine.save(stored)
        with self.assertRaises(ChatError): self.engine.respond('confirm', approval(job))

    def test_legacy_composer_route_still_creates_its_own_turn(self):
        job = self.engine.respond('preview', {'chat':'chat', 'question':'Existing draft route'})
        self.assertNotIn('source_turn', job)
        self.assertEqual(self.engine.chat.get('chat')['turns'][-1]['id'], job['turn'])


if __name__ == '__main__':
    unittest.main()
