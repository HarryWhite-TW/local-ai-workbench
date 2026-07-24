import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge import display_pilot_hgw_adapter as adapter


def fake_git(**overrides):
    values = {
        "remote get-url origin": adapter.HGW_ORIGIN,
        "branch --show-current": adapter.HGW_BRANCH,
        "rev-parse HEAD": adapter.HGW_HEAD,
        "status --short --untracked-files=all": "",
        "diff --cached --name-only": "",
    }
    values.update(overrides)

    def run(command, **kwargs):
        joined = " ".join(command)
        matched = next((value for key, value in values.items() if key in joined), None)
        if matched is None:
            return type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "bad"})()
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": matched + ("\n" if matched else ""), "stderr": ""},
        )()

    return run


@pytest.fixture
def synthetic_hgw(tmp_path):
    package = tmp_path / "src" / "human_governed_workflow"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text(
        """
import json

FLAGS = (
    "github_write_performed", "result_packet_written",
    "codex_side_action_executed", "runner_invoked", "dispatcher_invoked",
    "watcher_invoked", "broad_scan_performed", "commit_performed",
    "push_performed", "pr_created", "merge_performed", "issue_closed",
    "label_changed",
)

def default_safety_flags():
    return {name: False for name in FLAGS}

def build_result_surface(**values):
    return values

def render_reviewer_markdown(surface):
    return "review:" + surface["status"] + ":" + ",".join(surface["blocked_reasons"])

def render_plain_language_markdown(surface):
    return "plain:" + surface["status"] + ":" + ",".join(surface["blocked_reasons"])
""".lstrip(),
        encoding="utf-8",
    )
    git_run = fake_git()

    def run(command, **kwargs):
        if command[0] == "git":
            return git_run(command, **kwargs)
        return subprocess.run(command, **kwargs)

    return tmp_path, run


def canonical_evidence(*, result="success", blocked_reasons=None, test_result="success"):
    runtime_contract = {
        "protocol": "lawb.local_runner.task_packet.v1.1",
        "packet_id": "dp4-br-9",
        "logical_issue": 9,
        "repository": "HarryWhite-TW/human-approval-automation-gateway",
        "branch": "feature/display-pilot",
        "expected_head": "a" * 40,
        "task_mode": "PATCH_ONLY",
        "objective": "Implement one bounded change.",
        "allowed_files": ["src/example.py"],
        "max_allowed_files": 1,
        "verification_command_policy": "explicit_only",
        "verification_commands": ["python -m pytest -q tests/test_example.py"],
        "scope_expansion_allowed": False,
    }
    safety = {
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": True,
        "runner_invoked": True,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "broad_scan_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "pr_created": False,
        "merge_performed": False,
        "issue_closed": False,
        "label_changed": False,
    }
    return {
        "protocol": "hgw.display_pilot.canonical_evidence.v1",
        "request_id": "req-9",
        "transport_validation": {
            "protocol": "lawb.local_runner.task_surface_validation_summary.v1",
            "result": "success",
            "errors": [],
            "runtime_contract": runtime_contract,
        },
        "runtime_contract": runtime_contract,
        "runner_machine_evidence": {
            "safety_flags": safety,
        },
        "verification": [
            {
                "command": "python -m pytest -q tests/test_example.py",
                "result": test_result,
                "reason": "exit_code_0" if test_result == "success" else "exit_code_1",
            }
        ],
        "result": result,
        "changed_files": ["src/example.py"],
        "blocked_reasons": list(blocked_reasons or []),
        "safety_flags": safety,
        "created_at": "2026-07-24T00:00:00+00:00",
    }


def test_exact_checkout_is_accepted(tmp_path):
    result = adapter.verify_hgw_checkout(tmp_path, run=fake_git())
    assert result == {
        "result": "success",
        "reason": None,
        "repository": adapter.HGW_REPOSITORY,
        "branch": adapter.HGW_BRANCH,
        "head": adapter.HGW_HEAD,
        "clean": True,
        "staged_empty": True,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"remote get-url origin": "https://github.com/Other/repo.git"},
        {"branch --show-current": "other"},
        {"rev-parse HEAD": "b" * 40},
        {"status --short --untracked-files=all": " M file.py"},
        {"diff --cached --name-only": "file.py"},
    ],
)
def test_wrong_origin_branch_head_dirty_or_staged_checkout_blocks(tmp_path, overrides):
    result = adapter.verify_hgw_checkout(tmp_path, run=fake_git(**overrides))
    assert result["result"] == "blocked"
    assert result["reason"] == "hgw_checkout_not_reviewed"


def test_cached_ambient_module_substitution_is_blocked(tmp_path, monkeypatch):
    fake = ModuleType("human_governed_workflow")
    fake.__file__ = r"C:\elsewhere\human_governed_workflow\__init__.py"
    monkeypatch.setitem(sys.modules, "human_governed_workflow", fake)
    monkeypatch.setattr(
        adapter,
        "verify_hgw_checkout",
        lambda root, run=None: {"result": "success"},
    )

    result = adapter.render_from_evidence(
        root=tmp_path,
        python_path=sys.executable,
        evidence=canonical_evidence(),
        result_id="req-9",
        created_at="2026-07-24T00:00:00+00:00",
    )
    assert result["reason"] == "cached_hgw_module_substitution"


def test_success_evidence_produces_hgw_valid_surface_and_two_views(synthetic_hgw):
    root, run = synthetic_hgw
    result = adapter.render_from_evidence(
        root=root,
        python_path=sys.executable,
        evidence=canonical_evidence(),
        result_id="req-9",
        created_at="2026-07-24T00:00:00+00:00",
        run=run,
    )

    assert result["result"] == "success"
    surface = result["result_surface"]
    assert surface["status"] == "success"
    assert surface["requires_user_approval"] is True
    assert surface["tests_run"][0]["result"] == "success"
    assert all(type(value) is bool for value in surface["safety_flags"].values())
    assert "success" in result["reviewer_report"]
    assert "success" in result["plain_language_zh_TW"]


def test_blocked_evidence_has_reasons_and_recognized_failed_test_record(
    synthetic_hgw,
):
    root, run = synthetic_hgw
    result = adapter.render_from_evidence(
        root=root,
        python_path=sys.executable,
        evidence=canonical_evidence(
            result="blocked",
            blocked_reasons=["parent_verification_failed"],
            test_result="failed",
        ),
        result_id="req-9",
        created_at="2026-07-24T00:00:00+00:00",
        run=run,
    )

    surface = result["result_surface"]
    assert surface["status"] == "blocked"
    assert surface["blocked_reasons"] == ["parent_verification_failed"]
    assert surface["tests_run"][0] == {
        "command": "python -m pytest -q tests/test_example.py",
        "result": "failed",
        "reason": "exit_code_1",
    }
    assert "parent_verification_failed" in result["reviewer_report"]
    assert "parent_verification_failed" in result["plain_language_zh_TW"]


def test_missing_runner_safety_flag_cannot_be_defaulted_false(synthetic_hgw):
    root, run = synthetic_hgw
    evidence = canonical_evidence()
    evidence["runner_machine_evidence"]["safety_flags"].pop("commit_performed")

    result = adapter.render_from_evidence(
        root=root,
        python_path=sys.executable,
        evidence=evidence,
        result_id="req-9",
        created_at="2026-07-24T00:00:00+00:00",
        run=run,
    )

    assert result == {
        "result": "blocked",
        "reason": "isolated_hgw_render_failed",
    }
