"""Real bounded files and owner checks; synthetic identity, no model or credentials."""
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.companion_core.chat import Conversations
from src.companion_core.resources import MAX_BYTES, read_text
from src.companion_core.siwc import ChatError


class DocumentSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'project'; self.root.mkdir(); (self.root/'docs').mkdir()
        self.state = Path(self.temp.name)/'state'; self.state.mkdir()
        (self.root/'README.md').write_text('Body-only NEEDLE and 中文搜尋', encoding='utf-8')
        (self.root/'AGENTS.md').write_text('Boundaries', encoding='utf-8')
        (self.root/'docs'/'needle.txt').write_text('Safe guide', encoding='utf-8')
        (self.root/'docs'/'z.txt').write_text('Another needle', encoding='utf-8')
        self.auth = SimpleNamespace(lock=threading.RLock(), pending=None, vault=SimpleNamespace(data={'active':'owner'}))
        self.chat = Conversations(self.root, self.state, self.auth)
        self.r = self.chat.resources
        self.body = {'workspace':str(self.root)}

    def search(self, query):
        return self.r.documents({**self.body, 'query':query})

    def test_filename_path_body_chinese_and_stable_priority(self):
        expected = ['docs/needle.txt', 'README.md', 'docs/z.txt']
        for query in ('needle', 'NEEDLE', ' needle '):
            for _ in range(2):
                self.assertEqual([d['relative'] for d in self.search(query)['documents']], expected)
        self.assertEqual([d['relative'] for d in self.search('docs/z')['documents']], ['docs/z.txt'])
        self.assertEqual([d['relative'] for d in self.search('中文搜尋')['documents']], ['README.md'])
        self.assertEqual(self.search('missing')['documents'], [])
        self.assertEqual(self.search('')['documents'], self.r.documents(self.body)['documents'])

    def test_search_metadata_only_no_grants_writes_or_model_sources(self):
        before = {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.chat.connect() as db:
            dump = list(db.iterdump())
        result = self.search('中文搜尋')
        self.assertNotIn('中文搜尋', json.dumps(result, ensure_ascii=False))
        self.assertEqual(set(result['documents'][0]), {'id','name','relative','type','workspace','category','available','version','bytes','status'})
        self.assertIsNone(self.r.pending); self.assertIsNone(self.r.handoff)
        self.assertIsNone(self.chat.project_approval); self.assertIsNone(self.chat.busy)
        with self.chat.connect() as db:
            self.assertEqual(list(db.iterdump()), dump)
        self.assertEqual(before, {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        item = result['documents'][0]
        preview = self.r.preview({**self.body,'id':item['id'],'version':item['version']})
        self.assertIn('中文搜尋', preview['text'])
        self.assertIsNone(self.r.handoff)

    def test_unsafe_unreadable_outside_and_linked_files_never_match(self):
        bad = {'huge.txt':b'needle'+b'x'*MAX_BYTES, 'binary.txt':b'needle\x00',
               'sensitive.txt':b'needle api_key = "abcdefgh12345678"', 'encoding.txt':b'needle\xff',
               'private.txt':b'needle', 'file.pdf':b'needle', 'file.docx':b'needle'}
        for name, raw in bad.items(): (self.root/'docs'/name).write_bytes(raw)
        denied = self.root/'docs'/'denied.txt'; denied.write_text('needle'); denied.chmod(0o000)
        self.addCleanup(lambda: denied.chmod(0o600))
        (self.root/'outside.txt').write_text('needle')
        (self.root/'docs'/'nested').mkdir(); (self.root/'docs'/'nested'/'leak.txt').write_text('needle')
        external = Path(self.temp.name)/'external.txt'; external.write_text('needle')
        os.link(external, self.root/'docs'/'hardlink.txt')
        link = self.root/'docs'/'linked.txt'
        try: link.symlink_to(external)
        except OSError:
            if os.name != 'nt': raise
        self.assertEqual([d['relative'] for d in self.search('needle')['documents']], ['docs/needle.txt','README.md','docs/z.txt'])
        self.assertEqual(self.search('huge')['documents'], [])

    def test_changed_or_deleted_source_rejects_old_preview_and_search(self):
        item = self.search('中文搜尋')['documents'][0]
        body = {**self.body,'id':item['id'],'version':item['version']}
        (self.root/'README.md').write_text('Replacement', encoding='utf-8')
        with self.assertRaises(ChatError): self.r.preview(body)
        self.assertEqual(self.search('中文搜尋')['documents'], [])
        with self.assertRaises(ChatError): self.r.preview(body)
        (self.root/'README.md').unlink()
        self.assertEqual(self.search('中文搜尋')['documents'], [])

    def test_identity_change_during_search_and_foreign_workspace_fail_closed(self):
        for kind in ('account', 'pending', 'workspace'):
            def changed(*args):
                value = read_text(*args)
                if kind == 'account': self.auth.vault.data['active'] = 'other'
                elif kind == 'pending': self.auth.pending = True
                else: self.chat.workspace = 'foreign'
                return value
            with self.subTest(kind=kind), patch('src.companion_core.resources.read_text', side_effect=changed):
                with self.assertRaises(ChatError): self.search('needle')
            self.auth.vault.data['active'], self.auth.pending = 'owner', None
            self.chat.workspace = str(self.root)
        with self.assertRaises(ChatError): self.r.documents({'workspace':'foreign','query':'needle'})
        self.search('needle'); self.auth.vault.data['active']='other'
        with self.assertRaises(ChatError):
            item = next(iter(self.r.catalog.items()))
            self.r.preview({**self.body,'id':item[0],'version':item[1][3]})

    def test_limits_and_query_shape_are_enforced(self):
        for query in (None, [], 7, 'x'*101):
            with self.subTest(query=query), self.assertRaises(ChatError): self.search(query)
        with self.assertRaises(ChatError): self.r.documents({**self.body,'query':'needle','path':'elsewhere'})
        for i in range(80): (self.root/'docs'/f'{i:03}.txt').write_text('needle')
        with patch('src.companion_core.resources.read_text', wraps=read_text) as reader:
            self.assertLessEqual(len(self.search('needle')['documents']), 64)
            self.assertEqual(reader.call_count, 64)


if __name__ == '__main__': unittest.main()
