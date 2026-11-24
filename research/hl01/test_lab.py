"""Deterministic host checks. Scripted responses exercise policy and never count as natural model evidence."""
import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
import lab
from work_index import WorkIndex


class PolicyTests(unittest.TestCase):
    def setUp(self):
        base = lab.ROOT / ".lab-tmp"
        base.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / str(uuid.uuid4())
        self.path.mkdir()
        self.log = self.path / "audit.jsonl"

    def tools(self, allow):
        agent = lab.agent_for(TestModel(), self.path, "A", self.log, lambda *_: allow)
        return {name: tool.function for name, tool in agent.toolsets[0].tools.items()}

    def test_both_scope_dimensions_and_summary_content(self):
        index = WorkIndex()
        self.assertEqual([r["work_id"] for r in index.search()], ["W-31", "W-18", "W-09"])
        self.assertEqual(len(index.search("ReVeRb")), 2)
        self.assertEqual(index.search("其他帳戶"), [])
        for hidden in ("W-50", "W-60", "absent"):
            self.assertEqual(index.metadata(hidden), {"decision": "unavailable"})
        self.assertTrue(all("detail" not in row and len(row["sha256"]) == 64 for row in index.search()))

    def test_grant_binds_work_receipt_and_turn(self):
        funcs = self.tools(True)
        self.assertEqual(funcs["request_detail"]("W-31", "R-81")["decision"], "allowed")
        for ids in [("W-50", "R-50"), ("W-18", "R-81"), ("W-31", "R-72")]:
            self.assertEqual(funcs["read_evidence"](*ids), {"decision": "denied"})
        self.assertIn("240", funcs["read_evidence"]("W-31", "R-81")["evidence_text"])
        self.assertEqual(funcs["read_evidence"]("W-31", "R-81"), {"decision": "denied"})
        self.assertEqual(self.tools(True)["read_evidence"]("W-31", "R-81"), {"decision": "denied"})

    def test_denial_omits_detail_and_does_not_prompt_again(self):
        decisions = []
        def deny(*pair):
            decisions.append(pair)
            return False
        tools = lab.agent_for(TestModel(), self.path, "A", self.log, deny).toolsets[0].tools
        for _ in range(2):
            self.assertEqual(tools["request_detail"].function("W-31", "R-81"), {"decision": "denied"})
        self.assertEqual(tools["read_evidence"].function("W-31", "R-81"), {"decision": "denied"})
        self.assertEqual(decisions, [("W-31", "R-81")])
        self.assertNotIn("240 個取樣", self.log.read_text(encoding="utf-8"))

    def test_private_turn_excluded_from_core_history_and_harness_search(self):
        script = iter([
            ToolCallPart("request_detail", {"work_id": "W-31", "receipt": "R-81"}),
            ToolCallPart("read_evidence", {"work_id": "W-31", "receipt": "R-81"}),
            TextPart("實測記錄為 240 個取樣。")])
        def model_reply(messages, info):
            return ModelResponse(parts=[next(script)])
        with patch.object(lab, "build_model", return_value=(FunctionModel(model_reply), AsyncMock())), redirect_stdout(io.StringIO()):
            status = asyncio.run(lab.turn("B", self.path, "請看詳細收據", lambda *_: True))
        self.assertEqual(status, 0)
        persisted = (self.path / "conversation.json").read_text(encoding="utf-8")
        self.assertNotIn("240 個取樣", persisted)
        self.assertNotIn("evidence_text", persisted)
        run = (self.path / "latest").read_text()
        history = lab.harness(self.path)[1].source
        self.assertFalse(asyncio.run(history.list_runs()))
        self.assertEqual(asyncio.run(history.run_history(run_id=run)), [])
        self.assertTrue(any(e.get("private") for e in lab.entries(self.path / f"{run}.jsonl")))

    def test_recovery_never_reexecutes_unfinished_run(self):
        run = str(uuid.uuid4())
        (self.path / "latest").write_text(run)
        lab.note(self.path / f"{run}.jsonl", "start", parent_revision=None)
        with patch.object(lab, "build_model", side_effect=AssertionError), redirect_stdout(io.StringIO()):
            self.assertEqual(asyncio.run(lab.recover(self.path, "B")), 1)
        self.assertFalse((self.path / "conversation.json").exists())


if __name__ == "__main__":
    unittest.main()
