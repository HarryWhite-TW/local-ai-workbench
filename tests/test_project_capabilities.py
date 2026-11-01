"""Real service reuse and CLI I/O boundaries; no provider, HTTP or hardlinks."""
import json
from pathlib import Path
import subprocess
import sys

from api.app.services import task_extractors
from src import project_capabilities

ROOT = Path(__file__).resolve().parents[1]


def call(name, raw=b""):
    return subprocess.run([sys.executable, "-B", "-m", "src.project_capabilities", name],
                          cwd=ROOT, input=raw, capture_output=True, timeout=10)


def test_exports_are_existing_services_and_catalog_is_discoverable():
    assert project_capabilities.extract_requirements_v1 is task_extractors.extract_requirements_v1
    assert project_capabilities.normalize_requirement_text is task_extractors.normalize_requirement_text
    result = call("list")
    assert result.returncode == 0
    catalog = json.loads(result.stdout)
    assert catalog["read_only"] is True
    assert {c["name"] for c in catalog["capabilities"]} == {"extract-requirements", "normalize-requirement"}


def test_real_cli_extracts_requirements_with_provenance_and_deduplication():
    raw = b"# Requirements\n- The workbench must preserve source files.\n- The workbench must preserve source files.\n"
    result = call("extract-requirements", raw)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"method": "extract_requirements_v1", "items": [
        {"text": "The workbench must preserve source files.",
         "source_excerpt": "The workbench must preserve source files.",
         "match_reason": "requirements_heading"}]}


def test_cli_preserves_unicode_and_has_no_arbitrary_command_route():
    result = call("normalize-requirement", " - 保留   文件\t來源 - ".encode("utf-8"))
    assert result.returncode == 0 and json.loads(result.stdout) == {"text": "保留 文件 來源"}
    assert call("shell").returncode == 2


def test_cli_rejects_invalid_encoding_and_oversized_input_without_output():
    for raw in (b"\xff", b"x" * (1_048_576 + 1)):
        result = call("extract-requirements", raw)
        assert result.returncode == 2 and result.stdout == b""
        assert b"\xff" not in result.stderr
