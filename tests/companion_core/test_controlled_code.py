"""Host-boundary tests with synthetic source, never real model acceptance."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tempfile
import unittest

from src.companion_core.chat import Conversations, now
from src.companion_core.controlled_code import AUTHORITY, BASE, TARGET, ControlledCode, ExistingSignIn, ExistingVault, locked_target
from src.companion_core.native_execution import DISABLED, NativeClient, observe_turn
from src.companion_core.domain import Failure
from src.companion_core.runtime import RuntimeFailure
from src.companion_core.siwc import ChatError, Vault

def make_engine(tmp_path):
    root, state = tmp_path/'candidate', tmp_path/'state'
    target = root/TARGET
    target.parent.mkdir(parents=True)
    target.write_bytes(b'const original = 1;\n')
    state.mkdir()
    auth = SimpleNamespace(lock=threading.RLock(), pending=None,
                           vault=SimpleNamespace(data={'active': 'owner'}))
    chat = Conversations(root, state, auth)
    with chat.connect() as db:
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)', ('chat', str(root.resolve()), 'owner', 'test', now()))
        db.execute('CREATE TABLE controlled_code (id TEXT PRIMARY KEY, chat TEXT NOT NULL, value TEXT NOT NULL)')
    result = object.__new__(ControlledCode)
    result.chat, result.root, result.head = chat, root, BASE
    result.worker, result.key = None, secrets.token_bytes(32)
    result.node = shutil.which('node')
    result.git = Mock(return_value=BASE.encode())
    return result


def preview(engine):
    return engine.respond('preview', {'chat': 'chat', 'question': 'Add a review summary copy button'})


def approval(job):
    return {'id': job['id'], 'token': job['token'], 'authority': AUTHORITY}


def response(job, replacement='const original = 2;\n'):
    return json.dumps({'target': TARGET, 'source_sha256': job['source']['sha256'], 'replacement': replacement})




@unittest.skipUnless(os.name == 'nt', 'Windows handle isolation contract')
class ControlledCodeTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).absolute().parents[2]/'.eng01-safety-probe'
        scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='host-tests-',dir=scratch)
        assert Path(self.temp.name).resolve().is_relative_to(scratch.resolve())
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.number=0

    def fresh_engine(self):
        self.number+=1
        base=self.base/str(self.number)
        base.mkdir()
        return make_engine(base)

    def test_preview_captures_exact_source_without_writing(self):
        engine=self.fresh_engine()
        before = (engine.root/TARGET).read_bytes()
        job = preview(engine)
        assert job['source']['sha256'] == hashlib.sha256(before).hexdigest()
        assert job['source']['text'].encode() == before
        assert (engine.root/TARGET).read_bytes() == before
        assert engine.chat.get('chat')['turns'][0]['id'] == job['turn']


    def test_old_approvals_cannot_write(self):
        for authority in ['READ_ONLY', 'ISOLATED_SAMPLE_WRITE', '']:
            with self.subTest(authority=authority):
                engine=self.fresh_engine()
                body = approval(preview(engine)); body['authority'] = authority
                with self.assertRaises(ChatError): engine.respond('confirm', body)
                assert engine.worker is None

    def test_arbitrary_http_target_is_rejected(self):
        engine=self.fresh_engine()
        with self.assertRaises(ChatError):
            engine.respond('preview', {'chat':'chat', 'question':'change', 'target':'../AGENTS.md'})


    def test_approval_binds_all_authority_dimensions(self):
        for change in ['content', 'identity', 'head', 'goal', 'expiry', 'account', 'token']:
            with self.subTest(change=change):
                engine=self.fresh_engine()
                job = preview(engine); body = approval(job)
                if change == 'content': (engine.root/TARGET).write_text('changed')
                elif change == 'identity':
                    (engine.root/TARGET).unlink(); (engine.root/TARGET).write_bytes(job['source']['text'].encode())
                elif change == 'head': engine.git.return_value=b'other'
                elif change == 'account': engine.chat.auth.vault.data['active']='other'
                elif change == 'token': body['token']='invalid'
                else:
                    stored=engine.get(job['id'])
                    stored['goal' if change=='goal' else 'expires']='different' if change=='goal' else 0
                    engine.save(stored)
                with self.assertRaises(ChatError): engine.respond('confirm',body)
                assert engine.worker is None

    def test_approval_is_consumed_and_state_readback_has_no_side_effect(self):
        engine=self.fresh_engine()
        job=preview(engine)
        engine.run=Mock()
        engine.respond('confirm',approval(job)); engine.worker.join()
        with self.assertRaises(ChatError): engine.respond('confirm',approval(job))
        one=engine.respond('state',{'chat':'chat'}); two=engine.respond('state',{'chat':'chat'})
        assert one==two and one[0]['state']=='RUNNING'
        engine.run.assert_called_once()


    def test_invalid_model_result_never_writes(self):
        for bad in ['wrong_path', 'wrong_hash', 'duplicate', 'syntax', 'same']:
            with self.subTest(bad=bad):
                engine=self.fresh_engine()
                job=preview(engine); before=(engine.root/TARGET).read_bytes(); value=json.loads(response(job))
                if bad=='wrong_path': value['target']='AGENTS.md'
                elif bad=='wrong_hash': value['source_sha256']='0'*64
                elif bad=='syntax': value['replacement']='const broken = ;'
                elif bad=='same': value['replacement']=before.decode()
                answer=json.dumps(value)
                if bad=='duplicate': answer=answer[:-1]+',"target":"'+TARGET+'"}'
                with self.assertRaises((ChatError,ValueError)): engine.validate(answer,job)
                assert (engine.root/TARGET).read_bytes()==before

    def test_host_static_validation_and_apply_only_touch_fixed_file(self):
        engine=self.fresh_engine()
        job=preview(engine); stored=engine.get(job['id'])
        other=engine.root/'unapproved.txt';other.write_bytes(b'untouched')
        engine.validate(response(job),stored)
        assert stored['tests']['exitCode']==0
        assert stored['tests']['generated_code_executed'] is False
        engine.apply(stored)
        after=(engine.root/TARGET).read_bytes()
        assert after==b'const original = 2;\n' and other.read_bytes()==b'untouched'
        assert stored['diff'] and stored['state']=='COMPLETED'
        assert engine.respond('state',{'chat':'chat'})[0]['final_sha256']==hashlib.sha256(after).hexdigest()
        assert (engine.root/TARGET).read_bytes()==after


    def test_source_race_after_model_validation_cannot_apply(self):
        engine=self.fresh_engine()
        job=preview(engine);stored=engine.get(job['id']);engine.validate(response(job),stored)
        (engine.root/TARGET).write_bytes(b'new source')
        with self.assertRaises(ChatError):engine.apply(stored)
        assert (engine.root/TARGET).read_bytes()==b'new source'


    def test_target_handle_excludes_concurrent_writes_and_deletion(self):
        engine=self.fresh_engine()
        with locked_target(engine.root,write=True):
            with self.assertRaises(PermissionError): (engine.root/TARGET).write_bytes(b'forbidden')
            with self.assertRaises(PermissionError): (engine.root/TARGET).unlink()
        assert (engine.root/TARGET).read_bytes()==b'const original = 1;\n'


    def test_hardlink_target_is_rejected(self):
        engine=self.fresh_engine()
        os.link(engine.root/TARGET,engine.root/'alias.js')
        with self.assertRaises(ChatError):engine.snapshot()


    def test_junction_ancestor_is_rejected(self):
        engine=self.fresh_engine(); tmp_path=self.base
        parent=(engine.root/TARGET).parent
        moved=tmp_path/'moved';parent.rename(moved)
        result=subprocess.run(['cmd','/c','mklink','/J',str(parent),str(moved)],capture_output=True)
        assert result.returncode==0
        try:
            with self.assertRaises(ChatError):engine.snapshot()
            assert (moved/'engineering-pilot.js').read_bytes()==b'const original = 1;\n'
        finally:
            os.rmdir(parent)  # Remove only the junction itself; never recurse into it.


    def test_unexpected_model_tool_event_is_rejected(self):
        rpc=SimpleNamespace(notification=lambda _: {'method':'item/started','params':{
            'threadId':'thread','turnId':'turn','item':{'id':'tool','type':'commandExecution'}}})
        with self.assertRaises(RuntimeFailure) as error:
            observe_turn(rpc,'thread','turn',threading.Event(),lambda **_:None)
        assert error.exception.reason==Failure.POLICY


    def test_default_native_client_keeps_existing_settings_unchanged(self):
        assert NativeClient('empty','existing.exe').settings==()
        assert {'shell_tool','apply_patch_freeform','unified_exec','code_mode','browser_use'}.issubset(DISABLED)

class ManualSignInTests(unittest.TestCase):
    """Synthetic identities only; never open or inspect a real authorization URL."""
    def setUp(self):
        self.vault = object.__new__(ExistingVault)
        self.vault._manual_login_save = False
        self.vault.data = {'host':'synthetic-host','active':'owner','accounts':{
            'owner':{'client_id':'oaiapp_synthetic','subject':'synthetic-subject',
                     'label':'Synthetic account','expires_at':0}}}
        self.auth = ExistingSignIn(self.vault)
        self.addCleanup(self.auth.http.close)

    def test_expired_access_never_refreshes_or_saves(self):
        self.auth._json = Mock(side_effect=AssertionError('No automatic refresh'))
        with patch.object(Vault,'save') as save:
            with self.assertRaises(ChatError): self.auth.access('owner')
            save.assert_not_called()
        self.auth._json.assert_not_called()
        self.assertIn('Continue with ChatGPT',self.auth.notice)
        self.assertIn('owner',self.vault.data['accounts'])

    def test_explicit_login_opens_default_browser_and_waits_without_save(self):
        attempts=[]
        def opened(_):
            attempts.append(True)  # Discard URL without inspecting or retaining it.
            return True
        with patch('src.companion_core.siwc.webbrowser.open',new=opened),patch.object(Vault,'save') as save:
            self.auth.begin('http://127.0.0.1:56144','owner')
            self.assertEqual(len(attempts),1)
            self.assertIsNotNone(self.auth.pending)
            save.assert_not_called()
        self.assertIn('官方登入頁面',self.auth.notice)
        self.assertFalse(self.vault._manual_login_save)

    def test_browser_failure_is_explicit_and_not_left_pending(self):
        with patch('src.companion_core.siwc.webbrowser.open',new=lambda _:False):
            with self.assertRaises(ChatError):self.auth.begin('http://127.0.0.1:56144','owner')
        self.assertIsNone(self.auth.pending)
        self.assertIn('無法開啟系統瀏覽器',self.auth.notice)

    def test_only_valid_user_callback_can_save(self):
        with patch('src.companion_core.siwc.webbrowser.open',new=lambda _:True):
            self.auth.begin('http://127.0.0.1:56144','owner')
        self.auth._json=Mock(return_value={})
        self.auth._record=Mock(return_value={'client_id':'oaiapp_synthetic','subject':'synthetic-subject','email':'synthetic@example.invalid'})
        with patch.object(Vault,'save') as save:
            self.auth.callback({'state':self.auth.pending['state'],'code':'synthetic-code'})
            save.assert_called_once()
        self.assertIsNone(self.auth.pending)
        self.assertFalse(self.vault._manual_login_save)
        with self.assertRaises(ChatError):self.vault.save()

    def test_invalid_or_failed_callback_cannot_save_or_leave_permission_open(self):
        with patch.object(Vault,'save') as save:
            with self.assertRaises(ChatError):self.auth.callback({})
            save.assert_not_called()
        self.assertFalse(self.vault._manual_login_save)
        with self.assertRaises(ChatError):self.vault.save()

    def test_logout_and_account_switch_remain_blocked(self):
        with patch.object(Vault,'save') as save:
            with self.assertRaises(ChatError):self.auth.select('owner')
            with self.assertRaises(ChatError):self.auth.logout()
            save.assert_not_called()
        self.assertEqual(self.vault.data['active'],'owner')


if __name__ == '__main__':
    unittest.main()
