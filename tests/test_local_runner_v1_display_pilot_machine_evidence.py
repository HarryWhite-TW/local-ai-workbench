from pathlib import Path
SCRIPT=Path("scripts/local_runner_v1.ps1").read_text()
def test_old_invocation_defaults_unchanged(): assert '[string]$Mode = "ReviewBundle"' in SCRIPT
def test_suppress_requires_machine_path(): assert "SuppressReviewBundleComment requires MachineEvidencePath" in SCRIPT
def test_non_reviewbundle_machine_path_blocked(): assert "MachineEvidencePath is ReviewBundle-only" in SCRIPT
def test_machine_evidence_contract_is_opt_in_only(): assert "$MachineEvidencePath" in SCRIPT and "$SuppressReviewBundleComment" in SCRIPT
def test_no_review_comment_when_valid_suppression_requested_contract(): assert "SuppressReviewBundleComment" in SCRIPT
