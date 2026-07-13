# REC-02 Operational Field Evidence — Course Host Quick Restore After Reset

## Status

`ACCEPTED FIELD EVIDENCE`

This record captures one real post-reset course-computer recovery using the existing REC-02 Quick Restore path.

REC-02 remains `DONE`. This record does not reopen REC-02, create a new implementation node, authorize a script change, or activate RV2-P1, RV2-04, repository separation, startup, tray, service, MCP, or any other later node.

## Why This Evidence Matters

The course host was actually restored from a reset state through the repository-native recovery workflow rather than through ad hoc manual setup.

The result proves that the reviewed recovery path can recover the required local environment and converge to a clean `READY` state while preserving the documented safety boundaries.

This is operational field evidence, not a new product claim and not proof that every future reset will always converge in one run.

## Host And Repository Baseline

- Host path: `C:\Users\admin\Desktop\local-ai-workbench`
- Repository: `HarryWhite-TW/local-ai-workbench`
- Branch: `master`
- Canonical HEAD during final acceptance: `a4a42b1e266300aadcb319dc0cc0c31f79415f32`
- Final `HEAD == origin/master`: yes
- Final divergence: `0 0`
- Final working tree: clean
- Final staged area: empty

The preferred wrapper was used:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\course_environment_restore_review.ps1 ... -CompleteRecovery`

No raw temp evidence, authentication material, one-time login code, or host-specific temporary logs are committed by this record.

## Recovery Run 1

Observed result:

- Layer 1 restore status: `ATTENTION`
- Layer 2 Host Check: `SKIPPED: reviewed_paths_missing`
- Verdict: `BLOCKED`
- Wrapper exit: `2`

Component state after the run:

- Python: `READY`
- Dependencies: `READY`
- Git identity: `READY`
- GitHub CLI: `BLOCKED`
- Codex: `BLOCKED`

The apply-stage evidence recorded a historical action failure for `install_requirements_course`, but the same run's final component evidence showed Python and dependencies as `READY`.

Therefore this record does not classify that transient failure as a proven persistent root cause. It is retained only as truthful execution evidence.

## Recovery Run 2

The wrapper conditionally required user-visible GitHub browser/device authentication. Authentication completed successfully for the expected account:

- expected login: `HarryWhite-TW`
- observed login: `HarryWhite-TW`
- login matches: yes
- repository read: `READY`

Observed result after authentication:

- Python: `READY`
- Dependencies: `READY`
- GitHub CLI: `READY`
- GitHub authentication: `READY`
- GitHub repository read: `READY`
- Codex: `READY`
- Git identity: `READY`
- Focused pytest exit: `0`
- Host Check exit: `0`
- Layer 2 Host Check: `READY`

However:

- Layer 1 restore status: `ATTENTION`
- Verdict: `BLOCKED`
- only current blocker: `layer_1_not_ready`

A historical apply-stage action failure for `install_codex_0.141.0` was also present, but final component evidence showed Codex as `READY`.

### Reasonable Inference, Not Proven Defect

The wrapper performs the post-restore audit before the later conditional browser-authentication step. Therefore a plausible explanation is that Layer 1 retained earlier authentication-related `ATTENTION` after authentication had already succeeded.

This is recorded as a reasonable inference only. It is not yet classified as a proven script defect or accepted root cause.

## Recovery Run 3 — Final Convergence

The same canonical Complete Recovery wrapper was run again after authentication had already been established.

Final observed result:

- Layer 1 restore status: `READY`
- Layer 2 Host Check status: `READY`
- Layer 3 drift reasons: none
- Verdict: `READY`
- Wrapper exit: `0`
- Current blockers: none

Final component state:

- Python: `READY`
- Dependencies: `READY`
- GitHub CLI: `READY`
- GitHub authentication: `READY`
- GitHub repository read: `READY`
- Codex: `READY`
- Git identity: `READY`

Final verification exit codes:

- bootstrap audit: `0`
- bootstrap apply: not needed on the final convergence run
- post-restore audit: `0`
- focused pytest: `0`
- Host Check: `0`

## Safety Boundary Preserved

The accepted recovery evidence confirms that the workflow did not invoke or perform:

- live Bridge acceptance;
- Dispatcher;
- Runner;
- Codex runtime task execution;
- GitHub write;
- `gh auth token`;
- permanent PATH modification;
- global Git identity modification.

The final stop markers were present:

- `COURSE_ENVIRONMENT_RESTORE_REVIEW_DONE`
- `NO_LIVE_ACCEPTANCE_NO_DISPATCHER_NO_RUNNER_NO_CODEX_TASK_NO_GITHUB_WRITE`

## Operational Lessons

1. The REC-02 quick-restore path successfully recovered a real reset course host to full `READY` state.
2. Recovery remained bounded and evidence-driven; no broad manual discovery or unrelated environment mutation was required.
3. Re-running the same reviewed wrapper allowed already-recovered components to be reused and the environment to converge cleanly.
4. Conditional browser authentication may leave an earlier Layer 1 `ATTENTION` visible until a later run; this is an improvement candidate, not an accepted defect.
5. The complete recovery required three wrapper runs in this field case.

## Improvement Candidate

Candidate only:

`single-transaction convergence after conditional browser authentication`

Possible future question:

Should the wrapper perform one additional bounded post-auth audit refresh after successful conditional browser authentication so that a now-ready host can converge without requiring another manual wrapper run?

This record does not authorize that change. A separate bounded engineering node and fresh evidence would be required before modifying the script.

## Final Verdict

`REC-02 OPERATIONAL FIELD EVIDENCE = ACCEPTED`

`COURSE HOST QUICK RESTORE = READY`

`REC-02 STATUS = REMAINS DONE`

`NEW IMPLEMENTATION NODE = NOT ACTIVATED`

The recovery workflow demonstrated real operational value on the reset course computer, while the one remaining efficiency candidate is preserved without overstating it as a proven defect or automatically expanding scope.