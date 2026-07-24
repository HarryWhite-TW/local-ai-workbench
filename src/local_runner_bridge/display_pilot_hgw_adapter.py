"""Pinned, isolated adapter for the reviewed HGW Result Surface APIs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


HGW_REPOSITORY = "HarryWhite-TW/human-governed-workflow"
HGW_ORIGIN = "https://github.com/HarryWhite-TW/human-governed-workflow.git"
HGW_BRANCH = "main"
HGW_HEAD = "19ef3e0dfcc364b3d90557747db964f919fc6afc"

_ISOLATED_RENDERER = r"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
source = (root / "src").resolve()
sys.path.insert(0, str(source))
import human_governed_workflow.core as core

loaded = Path(core.__file__).resolve()
if not loaded.is_relative_to(source):
    raise RuntimeError("ambient_hgw_module_substitution")

payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
evidence = payload["evidence"]
status = evidence["result"]
if status not in {"success", "blocked"}:
    status = "blocked"

flags = core.default_safety_flags()
runner_flags = evidence["runner_machine_evidence"]["safety_flags"]
if set(runner_flags) != set(flags):
    raise RuntimeError("runner_safety_flags_incomplete_or_unknown")
for name in tuple(flags):
    if name == "runner_invoked":
        if runner_flags[name] is not True:
            raise RuntimeError("runner_invoked_flag_not_true")
        flags[name] = True
    else:
        value = runner_flags[name]
        if type(value) is not bool:
            raise RuntimeError("runner_safety_flag_not_boolean")
        flags[name] = value

surface = core.build_result_surface(
    result_id=payload["result_id"],
    created_at=payload["created_at"],
    source_task_reference={
        "kind": "display_pilot_foreground_request",
        "description": "Display Pilot request " + evidence["request_id"],
    },
    source_task_validation_result=evidence["transport_validation"],
    operation_mode="display_pilot_foreground_candidate",
    status=status,
    summary=(
        "Foreground Display Pilot candidate completed with canonical parent "
        "evidence; ChatGPT review and user approval remain separate."
        if status == "success"
        else "Foreground Display Pilot candidate stopped with explicit blockers."
    ),
    files_changed=evidence["changed_files"],
    tests_run=evidence["verification"],
    safety_flags=flags,
    blocked_reasons=evidence["blocked_reasons"],
    requires_user_approval=True,
    next_recommended_step="chatgpt_review",
)
result = {
    "result": "success",
    "result_surface": surface,
    "reviewer_report": core.render_reviewer_markdown(surface),
    "plain_language_zh_TW": core.render_plain_language_markdown(surface),
}
encoded = json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
sys.stdout.buffer.write(encoded)
"""


def _git_value(
    root: Path,
    *arguments: str,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[int, str]:
    completed = run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "-C",
            str(root),
            *arguments,
        ],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    return completed.returncode, (completed.stdout or "").strip()


def verify_hgw_checkout(
    root: str | Path,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Verify the exact clean reviewed HGW checkout without persistent config."""
    checkout = Path(root).resolve()
    if not checkout.is_dir():
        return {"result": "blocked", "reason": "hgw_checkout_missing"}
    probes = {
        "origin": ("remote", "get-url", "origin"),
        "branch": ("branch", "--show-current"),
        "head": ("rev-parse", "HEAD"),
        "status": ("status", "--short", "--untracked-files=all"),
        "staged": ("diff", "--cached", "--name-only"),
    }
    observed: dict[str, str] = {}
    for name, arguments in probes.items():
        code, value = _git_value(checkout, *arguments, run=run)
        if code != 0:
            return {"result": "blocked", "reason": f"hgw_git_probe_failed:{name}"}
        observed[name] = value
    if (
        observed["origin"] != HGW_ORIGIN
        or observed["branch"] != HGW_BRANCH
        or observed["head"] != HGW_HEAD
        or observed["status"]
        or observed["staged"]
    ):
        return {"result": "blocked", "reason": "hgw_checkout_not_reviewed"}
    return {
        "result": "success",
        "reason": None,
        "repository": HGW_REPOSITORY,
        "branch": HGW_BRANCH,
        "head": HGW_HEAD,
        "clean": True,
        "staged_empty": True,
    }


def render_from_evidence(
    *,
    root: str | Path,
    python_path: str | Path,
    evidence: dict[str, Any],
    result_id: str,
    created_at: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Render in an isolated child so ambient and cached modules cannot win."""
    checkout = verify_hgw_checkout(root, run=run)
    if checkout["result"] != "success":
        return checkout
    source = (Path(root).resolve() / "src").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "human_governed_workflow" and not name.startswith(
            "human_governed_workflow."
        ):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            return {"result": "blocked", "reason": "cached_hgw_module_substitution"}
        try:
            Path(module_file).resolve().relative_to(source)
        except ValueError:
            return {"result": "blocked", "reason": "cached_hgw_module_substitution"}
    reviewed_python = Path(python_path).resolve()
    if not reviewed_python.is_file():
        return {"result": "blocked", "reason": "reviewed_python_missing"}

    payload = json.dumps(
        {
            "evidence": evidence,
            "result_id": result_id,
            "created_at": created_at,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    completed = run(
        [
            str(reviewed_python),
            "-I",
            "-c",
            _ISOLATED_RENDERER,
            str(Path(root).resolve()),
        ],
        input=payload.encode("utf-8"),
        capture_output=True,
        text=False,
        shell=False,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        reason = (completed.stderr or b"").decode(
            "utf-8", errors="replace"
        ).strip()[-1000:]
        if "ambient_hgw_module_substitution" in reason:
            return {
                "result": "blocked",
                "reason": "ambient_hgw_module_substitution",
            }
        return {"result": "blocked", "reason": "isolated_hgw_render_failed"}
    try:
        rendered = json.loads((completed.stdout or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"result": "blocked", "reason": "isolated_hgw_output_invalid"}
    if type(rendered) is not dict or rendered.get("result") != "success":
        return {"result": "blocked", "reason": "isolated_hgw_output_invalid"}
    return rendered
