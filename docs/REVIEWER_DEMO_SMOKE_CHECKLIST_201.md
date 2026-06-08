# Reviewer Demo Smoke Checklist (#201)

## 1. Purpose

This note records a manual reviewer-facing demo smoke check for Local AI Workbench after the README and demo flow updates.

The goal was to verify that a reviewer can run the documented safe local CLI demo commands from a clean repository state.

## 2. Environment

- Machine type: course / school computer
- Repo path: `C:\Users\admin\Desktop\ai-1\local-ai-workbench`
- Branch: `master`
- HEAD: `eea40f3eb954b547d27cfd8a2d21b262a974ecaa`
- origin/master: `eea40f3eb954b547d27cfd8a2d21b262a974ecaa`
- Latest commit: `docs: update stable CLI demo commands`

## 3. Commands Verified

Command:

`$env:PYTHONPATH='src'; python -m local_runner_bridge.result_surface_cli --sample`

Result: passed. The command emitted local Result Surface JSON with `status=success`.

Command:

`$env:PYTHONPATH='src'; python -m local_runner_bridge.writeback_target_contract_cli --help`

Result: passed. The command printed help text and included `--contract-file`.

Command:

`$env:PYTHONPATH='src'; python -m local_runner_bridge.writeback_implementation_boundary_cli --help`

Result: passed. The command printed help text and included `--boundary-file`.

## 4. Safety Boundary

This smoke check did not perform:

- live GitHub fetch
- GitHub writeback
- GitHub comment write
- GitHub issue body update
- Result Packet write
- runner invocation
- dispatcher invocation
- watcher invocation
- PR creation
- merge
- issue close
- label change

## 5. Final Git Status

Final `git status --short` produced no output.

The repository remained clean after running the demo commands.

## 6. Conclusion

The reviewer-facing local CLI demo path is currently smoke-tested and usable from a clean clone on the course machine.

This supports the current project status after #200:

- README demo commands are runnable.
- Local-only CLI demos are stable.
- No new boundary layer was added.
- The project remains in normal project work mode.