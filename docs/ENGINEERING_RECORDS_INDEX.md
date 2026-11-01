# Engineering Records Index

> Publication scope: `codex/node01-consolidated-candidate-20261101` carries the
> complete retained NEXUS/Node 01 candidate published through PR #362. Status,
> H/M identities and "uncommitted" descriptions below are dated
> pre-publication evidence. Node 01 local consolidation is technically ACCEPTED.
> [PR #362](https://github.com/HarryWhite-TW/local-ai-workbench/pull/362) publishes
> the candidate; its current merge state is tracked there. Real daily-use
> acceptance remains outstanding. PLANS owns current direction; no later node
> is activated.

## Purpose

This file is a navigation index for engineering records. It is not current truth by itself, does not replace fresh Git or GitHub verification, and does not authorize work.

## First Read Order

Recommended future session read order:

1. `AGENTS.md`
2. `src/local_runner_bridge/AGENTS.md` when the incumbent Bridge, Dispatcher, Runner, Task Packet, or Bridge Operator is used or changed (native Codex alone does not select this route)
3. `PLANS.md`
4. `docs/ENGINEERING_RECORDS_INDEX.md`
5. Roadmap, OPT, and active task documents as needed

## Source-of-Truth Hierarchy

- `AGENTS.md` is the repo-wide rule source.
- Scoped `AGENTS.md` files govern their own folders and bridge/workflow work when applicable.
- `PLANS.md` is the durable project-status source.
- `docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md` governs Roadmap v2 execution.
- Active tracker and node Issues record GitHub state, but they must be freshly verified.
- PRs and comments are historical or append-only evidence unless explicitly identified as current.
- `README.md` owns usage/navigation; the current local NEXUS disposition is in `PLANS.md`.
- Dated research and historical ecosystem roadmaps are evidence/reference, not competing current plans.

## Final Consolidation and Project Capability Library

Current Node 01 scope is in root PLANS; the earlier submission/continuation
sections below are dated engineering evidence, not the latest completion claim.
The new root README owns launch/setup navigation. This index owns feature/source
lookup, the document register and evidence; it does not own another roadmap.

### Reusable Developer Entry

`src/project_capabilities.py` provides a finite local CLI and directly exports
the existing functions in `api/app/services/task_extractors.py`. The source
algorithm is unchanged. Run from the repository root with Python 3.10+; the
chosen tools use only the standard library. `python -B -m src.project_capabilities
list` reports the contracts. This is an uncommitted local addition on H, not M.

| Name / invocation | Input -> output | Safety / verification |
|---|---|---|
| `extract-requirements` / `extract_requirements_v1` | Explicit UTF-8 text -> `{method, items:[{text,source_excerpt,match_reason}]}` | Pure existing regex/heading algorithm, no files/network/model; English markers, not semantic reasoning. Real CLI/source-identity/dedup tests passed |
| `normalize-requirement` / `normalize_requirement_text` | Explicit UTF-8 text -> `{text}` (CLI), `str` (Python) | Original whitespace normalization, Unicode test passed; not document-format extraction |

CLI stdin is bounded to 1 MiB and rejects invalid UTF-8; no arbitrary action,
path, provider, credential or subprocess route is exposed. Python exports are
the same callable objects (`is`, verified), with their existing service contract.
Developer invocation is not NEXUS UI integration or resource-access authorization.
Existing PDF/DOCX functions remain reusable in `file_extractors.py`; this venv
lacks `python-docx`, so no dependency was installed and no format-extraction
success is claimed here. The stdlib requirement extractor was chosen instead.

### Code Ownership and Historical Isolation

- Current daily composition, shared Core/ReviewStore and Native Reader remain
  where the source ledger locates them. No product algorithm, state schema,
  account boundary or original NEXUS test/visual asset was rewritten.
- `companion_core.__main__` and `surface` module descriptions now distinguish
  specialized trusted-host entry from daily SIWC composition. Their executable
  AST remains unchanged apart from the module docstring; line counts are retained.
- Ten unreferenced historical records moved to [archive](archive/README.md),
  plus the repeated prior PLANS ecosystem/history section.
  Only former paths with no explicit caller and no relative Markdown links were
  selected; contents remain byte-identical. All other historical paths remain
  stable, with scoped notices where appropriate. No valid Bridge rule was retired.
- NEXUS's generic top-level docs listing may previously have exposed those old
  records. They are intentionally no longer in that top-level catalogue; their
  archive paths remain available to developers. Existing grants/version checks
  still govern changed catalogues; this is not a new NEXUS document API.
- Structured examples, metrics, schema samples, fixtures, screenshot and reserved
  prompt directory are also registered. Draft/empty items stay UNCERTAIN rather
  than being deleted or treated as adopted functionality.

### Final Consolidation Verification

Actual checks for this final iteration:

- `python -B -m pytest tests/test_project_capabilities.py -q -p no:cacheprovider`:
  **4 passed**. Verifies original function identity, real subprocess CLI result,
  requirement provenance/deduplication, Unicode, finite action selection and
  invalid/oversized UTF-8 rejection. No provider, socket or hardlink involved.
- README's exact list, PowerShell pipe and direct-import example commands ran
  successfully. For input `The workbench must preserve source files.`, output
  was method `extract_requirements_v1`, one identical text/excerpt item and
  match_reason `modal_must`. All three Companion host `--help` commands passed.
- Eighteen Python files parsed (16 existing Companion modules, new capability
  module and its test). The two host changes are module docstrings only;
  existing executable AST/content is unchanged.
- Ten full archived files retain their initial SHA-256 bytes; the relocated
  PLANS section remains verbatim after its archive notice; removal of the single
  notice recovers each of the 69 retained historical documents' starting hash.
- Complete register: **166** files/assets: CURRENT 8, REUSABLE 41,
  SPECIALIZED 30, HISTORICAL 83, UNCERTAIN 4. **200 relative Markdown/image
  links** resolved with zero missing paths; no code/test reference to the ten
  retired source paths was found. Archive documents remain discoverable.
- The original 67 untracked assets, other existing NEXUS sources/tests/visuals,
  governing AGENTS/Bridge specs and requirement extractor retain their starting
  bytes, except the two explicitly described host docstrings. The final source
  manifest/status readback is returned in the same conversation.
- Original extractor version: commit
  `f36a73ed54d20922c6621a4ad6e89b34785669ba`, source SHA-256
  `409c693f82235692fa11825bf6443cd2a82e95903be1f961c43efb9807f90bb1`.
  New capability/tests and archive organization are uncommitted candidate work.
- `git diff --check` passed. No Docker asset changed, so Docker is not applicable.

Prior HTTP 10013 and hardlink 5 failures remain runtime UNKNOWN and were not
retried. API format extraction import is blocked by missing `python-docx`; no
installation or success claim was substituted. This did not block the selected
stdlib capability. No full real-login, game-time or daily-use acceptance is claimed.

Historical executor disposition, before independent technical acceptance:
**READY_FOR_REVIEW — Node 01 final consolidation
and project capability library**. The expanded scope is evidenced by root
navigation, complete register, history separation, actual callable reuse and
preservation checks above. Node 02 still owns future UI/executor integration and
any new authority. Independent technical acceptance of the local consolidation
was subsequently reported by the user.

## NEXUS Node 01 Consolidation — 2026-11-01

Earlier submission/continuation evidence follows; latest scope and verification
are in **Final Consolidation and Project Capability Library** above.

- Current status/capability ownership: root `PLANS.md`, **NEXUS Node 01 — Current
  Consolidation Candidate**. User entry: README's **NEXUS Local Candidate Entry**.
  This index navigates evidence; it neither accepts the candidate nor activates Node 02.
- Source lineage: PR #356 native-first, #358 Companion core, #359 human loop,
  #360 explicit review, #361 daily surface; canonical master observed for this
  node at `661f2b77a6f4d42d8583eb10e396e2a91a35a571`.
- Local HEAD `6c1eac3e8be6f2b6efc5ba58e5289db5972a1f71` contains cancellation and
  the M2-C4 syntax fix. Master's `surface.py:40` still fails Python parsing;
  local candidate has the correction. This affects only that master entry claim.
- The uncommitted daily/chat/resources/native-reader/UI candidate is retained.
  The first submission changed README, PLANS and this index; the continuation
  also clarifies applicability in the Bridge Direction Lock, Operator spec,
  Bridge Roadmap and ECO-01 checkpoint. Those earlier iterations changed no runtime source; the latest developer entry
  and archive work are described above. No Recoverable Baseline is recreated and
  no commit/merge is performed.
- Independent research input:
  [NEXUS_WORKFLOW_Independent_Review_2026-11-01.md](https://chatgpt.com/library?file_id=libfile_aff03447d69881919c23765b1593298e&account_id=personal).
  This is a dated research report, not authority to override the user's current
  NEXUS direction or start new work.
- Existing Native Reader evidence:
  [READY_FOR_REVIEW(1).json](https://chatgpt.com/library?file_id=libfile_5f78174bc2348191b7eb182ada501f93&account_id=personal).
  Its live-history checks still used synthetic SIWC; no full real-login E2E
  acceptance is inferred. Fresh source identity must accompany any later review.
- Node 01 verification: `daily --help` exited 0; all 16 current Companion
  Python modules parsed; `git diff --check` passed. An isolated-data daily
  process printed its loopback URL and was terminated by its owning check;
  HTTP readback was blocked by `WinError 10013`, so asset/browser availability
  is UNVERIFIED, not passed. No real login or model request was made.
- Targeted pytest: **19 passed, 10 failed** (29 selected). Six failures concern
  durable work/result readback; four concern HTTP requests. A separate scratch
  probe confirms `os.link` fails with `WinError 5`, while ReviewStore deliberately
  requires atomic hardlinks. These environment restrictions prevent current
  end-to-end verification; no filesystem fallback, permission repair or product
  change was attempted. They do not establish a newly introduced docs regression.
- Reproduce the targeted selection with the existing venv Python, `-B -m pytest`,
  `-q -p no:cacheprovider`, and these paths/nodes:
  `tests/companion_core/test_native_codex.py`,
  `tests/companion_core/test_conversation_work.py`,
  `tests/companion_core/test_daily.py::test_conversation_followup_restart_sources_and_review_separation`,
  `tests/companion_core/test_daily.py::test_natural_chat_needs_no_sources_preview_or_citations`,
  `tests/companion_core/test_daily.py::test_document_handoff_exact_model_payload_single_send_and_historical_source`,
  `tests/companion_core/test_surface.py::test_fixed_preview_port_is_local_exclusive_and_reusable`,
  `tests/companion_core/test_surface.py::test_http_happy_path_and_no_credential_surface`.
  Use a fresh temporary `--basetemp` outside the repository. These use synthetic
  providers; they do not prove real SIWC availability or accept the full candidate.
- First-submission disposition: document work retained, **overall Node 01 PARTIAL**
  after independent review against the original outcome. The first READY_FOR_REVIEW
  covered document alignment only and must not be read as overall completion.
  The continuation source/branch evidence below addresses the omitted coverage.
  Docker is not exercised: no Docker behaviour or assets changed.
- HGW and HAG remain independent repositories, referenced by PLANS's Repository
  Roles and retained ECO-CP1 history. No source cutover into NEXUS was performed.
- Visual research assets remain independent references; the daily UI and its
  optional synthetic experience are not proof of integrated Project Universe data.

Later local or remote changes require fresh identity checks. Historical PR
acceptance, Issue open/closed status, source presence and a passing synthetic
fixture are distinct evidence; none alone proves current real daily use.

## Node 01 Source Connections and Reuse

Continuation observation: 2026-11-01; entry/source wiring is statically verified,
not a fresh real-login or daily-use acceptance. Short commits below identify
Git objects; remote master was read again, not inferred from local `master`.
`M` = published master `661f2b77a6f4d42d8583eb10e396e2a91a35a571`;
`H` = local submitted HEAD `6c1eac3e8be6f2b6efc5ba58e5289db5972a1f71`;
`L` = retained working-tree modifications/untracked files on H. The full local
candidate is H + L + this documentation diff. No release/tag is implied by M.

### Calls, Dependencies and State Ownership

Source locations are relative to the repository root. Function/line anchors
refer to the unchanged runtime source inspected for this continuation.

| Family / current disposition | Actual entry and call boundary | State/dependencies and reuse limit | Version / applicable evidence |
|---|---|---|---|
| Daily composition — 現役 | `Open-Companion.cmd:8` -> `daily.main:45-51` constructs Vault, SignIn, Conversations, ProjectWork, Surface/ReviewStore, NativeCodex and `make_server` | Existing venv + `requirements-companion.txt`; foreground loopback. Workspace is startup-selected, not a request-supplied arbitrary path | L launcher/daily/SIWC/chat/work/reader; H core/store + L surface. Previous help/bind proof only; HTTP blocked |
| Chat — 現役 | `static/chat.js:89` `/api/chat/*` -> `surface.py:279-340` -> `Conversations.submit:289` -> `_run:479` -> `_infer:358` | `conversations.sqlite3`: chats/turns; SIWC model selection + streamed Responses, no tools; selected sources/historical provenance only | L `chat.py`, `siwc.py`, `chat.js`; existing `test_daily.py` synthetic stream/followup tests; not real provider acceptance |
| Project context — 現役 | chat.js project-preview/project-confirm -> `surface.py:297-308` -> `chat.py:187-236`; project-context also embeds the existing `surface.snapshot()` | Same conversations DB `chat_projects`, account/workspace-bound association; explicit preview/confirm. No second project runtime or multi-root registry | L; `test_project_context.py`, `verify_project_context.cjs` exist; no new execution in this continuation |
| Documents / links — 現役 | `nexus.js:290,376,456` resource-* -> `surface.py:309-320` -> `ProjectResources.documents/preview/preview_source/source`; source grant -> `openDocumentCompanion` -> chat selected_sources | `resources.py`: bounded md/txt/rst text and URL references, owner-scoped grants; `chat.py:333-340` resolves explicit source; no PDF/DOCX parser/API request | L; `test_resources.py`, existing document-handoff tests and `verify_document_handoff.cjs`. A previewed link is not autonomous web research |
| Work proposal / result return — 現役 | `chat.js:529-530` work-create -> `surface.py:326-336` -> `work.py:create/preview/confirm` -> `Surface.start:80` -> `Companion.run` -> `ProjectWork.run:156` | `work_proposals` in same chat DB stores lineage; fixed seven-file AST/hash audit; `_finished` records non-result outcomes, successful result authority stays ReviewStore. `/api/start` rejects proposal bypass (`surface.py:347-349`) | L work/chat/surface integration on H Core; existing `test_conversation_work.py`; durable-path verification limited by hardlink environment |
| Result review / explicit chat reuse — 現役 | `Surface._execute:96` publishes -> `ReviewStore`; target/review routes -> `Surface.decide:141`; `chat.selected_sources` resolves work:* -> `ProjectWork.context:251` -> exact saved `store.get` | Core is reused, not copied for daily. Task/result digest-bound files outside repo; atomic hardlink required. Work result can be explicitly selected as chat source; this does not grant acceptance or external effects | M review (`9db27d2`), H cancellation/Core (`6c1eac3`), L account/work links; old review tests + work tests; no new pass claimed |
| Native Codex history — 現役 | native-codex.js -> `/api/chat/codex-*` -> `NativeCodex.respond/handle:161` -> `ReadClient.call` allowlist: thread/list, thread/read, thread/turns/list | Short-lived app-server uses installed user's native Codex state; account/workspace grant and revocation, bounded text projection. Does not save transcript to chat/ReviewStore; live state UNKNOWN | L; `test_native_codex.py`, existing READY_FOR_REVIEW(1) five-file identity and live-history evidence (synthetic SIWC), not current control capability |
| UI continuity / floating view — 現役 | chat.js continuity-get/save -> surface -> `chat.continuity` -> `Continuity.get/save`; `index.html:197` page `<dialog>` and UI listeners | Continuity rows in chat DB, DPAPI and owner/revision checks. UI preferences/localStorage do not own tasks; reading.js is presentation, not a document index | L; `test_continuity.py`, UI verifier assets. No OS tray/always-on-top or semantic memory claim |
| Legacy Companion Codex adapter — 待接入 | `__main__.main` CLI and separate `surface.main:376` -> `CodexRuntime.run:198` -> `_execute:269` -> thread/start, turn/start, interrupt; both reuse same Core/ReviewStore | Trusted host supplies short-lived credential, temporary CODEX_HOME isolates inherited configuration; readOnly + no network policy. Same protocol family as Reader, different session/home/auth contract. Daily binds ProjectWork, not this runtime | M/H; cancellation update H; no standalone SIWC host integration. Existing `test_codex.py`, `test_cancellation.py`, `test_review.py`; CLI/surface presence is not full current daily UX proof |
| Document showcase / service reuse — independent showcase; 待接入 relative to NEXUS | `web/src/App.tsx` -> `web/src/api.ts` -> FastAPI `api/app/main.py` -> `routes/documents.py:48-159` -> services documents/file_extractors/summary/decisions/obsidian_export | API SQLite is separate from conversations DB. Existing extraction/index/summary/decision/preview/export; export has its own approval/destination contract. No Companion import or fetch to this API in inspected NEXUS entry | M/H unchanged; decisions `27a7a30`, extractor hardening `d76a2b5`; `tests/api`. Reuse service contract, do not merge databases or redo PDF/DOCX |
| Bridge / Operator / Dispatcher / Runner — 獨立／備用 | `bridge_operator_b3._delegate_b3_request:2527`, `build_dispatcher_command` in b2 -> `scripts/local_dispatcher_v1.ps1:1647` -> `local_runner_v1.ps1:5273` -> Codex exec | Durable in-flight/processed/review records; dispatch ownership persisted before spawn (b3:2737). Runner uses governed workspace-write ReviewBundle, unlike read-only Companion. No daily.py call into this chain | M/H; first-party tests/local_runner_bridge and retained closeouts; not executed now. Reusing dispatch requires existing route governance, not a new daily import |
| Bridge notifications — 獨立／備用 | b3 imports processor (79-81), calls `_process_workflow_notifications` -> `workflow_result_notifications.process_new_workflow_result_notifications:308` -> `submit_windows_desktop_notification:67` | Bridge terminal records, opt-in flag, durable notification dedup/receipt, Windows helper under LocalAppData. API submission and user-visible delivery are different; not connected to native Reader or daily result events | Introduced `9ff5488`, present M/H; existing notification tests. Reuse only after choosing event owner; no native completion notification claimed |
| Observability / Panel / Sanctuary / Unified Shell — 獨立／備用 | `workflow_panel.py:33,41` imports EventStore and project_sanctuary; main:1293 -> create_workflow_panel_server; `/api/snapshot`, `/api/sanctuary` at 1175-1190 read same snapshot/events; `/sanctuary` serves world | Incumbent lifecycle/final-verdict files plus observation EventStore/SSE; Sanctuary is derived presentation, Unified Shell is its existing world/inspector UI. No new executor; no NEXUS daily invocation | Spine introduced `2a79832`, Panel `a118d10`, Shell `2d9a1a2` (PR #353), observation correction `d3b17b6`; M/H. Existing projection/Panel/observation tests; not current native telemetry |
| HGW / HAG — 獨立／備用 | HGW `core/runtime_contract_binding.py` calls its validators/contracts; HAG `LocalApplication.__init__:205-240` composes approvals/audit/execution with DeterministicFakeGitHubIssueAdapter | Separate published repos, not dependencies imported by daily/API/Bridge production Python. HGW frozen compatibility comes from LAWB `52e59d45...` with required transformations; not a drop-in latest parser. HAG demo owns fake proposals/JSONL, not Companion review | HGW main `e5f0f3d94215babeb0b9b120c76b06cf1ae3f3e9`; HAG main `6e5515cfc75e245c4bb301bd1c8534ea6686e77f`; exact links below. No runtime cutover or new external verification |

Static checks covered production Python import namespaces and UI API targets;
negative integration statements are scoped to these actual entry/call paths,
not a claim about every possible future plugin or dynamic configuration.

### Important Versions and Retained Branches

| Source/version | Evidence and retained value | Use decision |
|---|---|---|
| Published LAWB master M | PR #358 core, #359 human loop, #360 review, #361 thin surface; source at M still contains surface.py:40 SyntaxError | Published code is traceable, not presently launchable through that affected Companion host; preserve other accepted components |
| Submitted local H / remote `codex/m2c6-running-cancellation` | `6c1eac3...`: 14-file diff over M, cancellation + syntax fix | Base of current candidate, not merged master |
| Local `master` | `4c38c672f09a25f5fa3754b2265afe4a110b63ca` | Stale name, not the authoritative current version; no reset performed |
| Local `codex/lc01-daily-workflow`, `codex/lc-bridge01-surface-integration`, `codex/lc-workux01-observation-reader` | All point to H; Git refs inspected | Names do not identify separate committed feature sets; their uncommitted working-tree content must be reviewed |
| Merged retained source branches | `codex/product-extract-decisions-317` -> `27a7a30`; `codex/unified-shell-activity-semantics-publication` -> `2d9a1a2`; `codex/post-rebaseline-observability-correctness-closeout` -> `d3b17b6`; each is in H ancestry | Features already retained in current committed code; do not reimplement or cherry-pick them again |
| Unmerged controlled-development Skill | `feat/lawb-controlled-development-skill` at `b59d3fe4932b15937d61ebf1cf90996ffac48119`; compare with M: ahead 1 / behind 238; `.agents/skills/lawb-controlled-development/SKILL.md` + agent YAML + old AGENTS changes | Independent historical reference, not installed or governing this task. Explicit-invocation bounded-cycle ideas may be reused after review; do not merge old AGENTS or import old task/approval requirements |
| Unmerged document guided-flow lab | `ui-224-beginner-mode-lab` at `435554b717d0c5b330384d96083743563bd2910b`; compare with M: ahead 2 / behind 307; App imports `deriveGuidedFlowState/getGuidedDocumentId` from `web/src/guidedFlow.ts` | Retain reusable pure document-identity/step derivation. Not NEXUS project manager, not in current App; old UI/base and AGENTS edits must not be bulk merged; compatibility not tested now |
| Backend-task-contract branch | `codex/v1.1-backend-task-contract`: GitHub compare against M is behind 498 / ahead 0, no unique files | Already contained history, not an unmerged new executor |
| OPT07 | `docs/POST_RV2_03_CODEBASE_MEMORY_BENCHMARK_OPT07.md`, existing NO-GO | Retain benchmark/lessons; no adopted memory dependency |
| #147 and pre-closeout roadmaps | Historical relay and sequencing; fixed incumbent #279 route documented separately | No new activation or inferred latest/next task |

Branch comparisons were read-only GitHub compare calls; retained component
ancestry was checked against local H. No fetch, checkout, reset or publication
was needed. No claim is made that every old branch was exhaustively audited.

### Uncommitted Sources Are Product Assets

All 67 untracked paths were enumerated, not discarded as scratch:

| Group | Count | Exact location / purpose |
|---|---:|---|
| Launchers/dependencies | 4 | `Open-Companion.cmd` (real daily), `requirements-companion.txt`; `Open-LC-Bridge-01-Test.cmd` and `Open-LC-WorkUX-01-Test.cmd` both call `tests/companion_core/browser_fixture.py --interactive` with distinct test data dirs |
| Product Python | 7 | `src/companion_core/{daily,siwc,chat,resources,work,continuity,native_codex}.py` |
| Product/UI assets | 9 | `static/{chat.css,chat.js,nexus.css,nexus.js,reading.js,native-codex.css,native-codex.js,experience.css,experience.js}` under companion_core; experience is optional synthetic material, not runtime truth |
| Test/fixture/verifier/documentation | 32 | Untracked files directly under `tests/companion_core/`; tests for account/project/resources/work/continuity/reader and browser verifiers, plus two LC test instructions |
| Visual baseline | 15 | `tests/companion_core/visual_baseline/`: 14 PNGs + manifest.json; preserve as existing visual acceptance material |

The original ten tracked modifications (five product files and five test files)
are separate from those 67 paths. The continuation begins with three additional
tracked document changes from the first Node 01 submission. A HEAD checkout
alone omits this product functionality; no staging/publication is implied here.

### External Retained Source Locators

- [HGW runtime binding](https://github.com/HarryWhite-TW/human-governed-workflow/blob/e5f0f3d94215babeb0b9b120c76b06cf1ae3f3e9/src/human_governed_workflow/core/runtime_contract_binding.py),
  [migration provenance](https://github.com/HarryWhite-TW/human-governed-workflow/blob/e5f0f3d94215babeb0b9b120c76b06cf1ae3f3e9/migration/provenance-map.json).
- [HAG actual application composition](https://github.com/HarryWhite-TW/human-approval-automation-gateway/blob/6e5515cfc75e245c4bb301bd1c8534ea6686e77f/human_approval_gateway/local_application.py#L205).
- [Unmerged Skill](https://github.com/HarryWhite-TW/local-ai-workbench/blob/b59d3fe4932b15937d61ebf1cf90996ffac48119/.agents/skills/lawb-controlled-development/SKILL.md),
  [guided-flow implementation](https://github.com/HarryWhite-TW/local-ai-workbench/blob/435554b717d0c5b330384d96083743563bd2910b/web/src/guidedFlow.ts#L148).
- [Visual/UI research handoff, 2026-10-22](https://chatgpt.com/library?file_id=libfile_b61922239cd48191838a06d1005b68be&account_id=personal):
  locator for Visual Kit/Liquid Ceramic/Project Universe and original asset
  provenance, not a verified runtime dependency. Independent visual ZIPs are
  not silently imported into the current candidate or declared byte-compatible.

### Overlap Decisions and Necessary Integration Check

Preserve the shared Core/ReviewStore and daily chat/work/source handoff; they
are already wired. Keep native history reading separate from execution, and
keep Bridge's broader governed Runner separate from read-only Companion.
Do not substitute HAG fake approvals for either review authority. Preserve
Document API extraction/export rather than rebuilding it in text previews.
Panel/Sanctuary share observation inputs; they are not duplicate runtimes.

No known missing low-risk edge was found in the scoped current entry. This is
supported by the caller-to-handler-to-service paths above and static checks of
served assets/imports. Linking a new executor, PDF pipeline, native notification
source or OS window requires a product/data/authority choice, so it is not a
forgotten wiring repair. Existing HTTP/hardlink failures remain UNKNOWN for
live behaviour; no environment repair, repeated blocked test run or safety
fallback was attempted.

### Earlier Continuation Verification and Review Coverage

Static/source checks (this continuation, not a rerun of blocked runtime tests):
16 Companion modules parsed; all nine initial HTML JS/CSS assets exist and are
in the server allowlist; seven selected project/work/continuity UI action names
have server handlers; no production Python imports of HGW/HAG in Companion,
Bridge or API; three retained implementation commits are ancestors of H; three
local daily branch aliases resolve to H. Relative documentation links/fences,
`git diff --check`, and pre-existing runtime/test/asset byte preservation passed.
These are source observations, not nine successful HTTP fetches or UI tests.

| Original criterion | Evidence / disposition |
|---|---|
| 1. Source, entry, dependency, version and use | VERIFIED for inspected source relationships: Calls/Dependencies table, actual route and composition anchors; live behaviour still limited as stated |
| 2. Existing unintegrated capabilities remain discoverable | VERIFIED: Document API, legacy adapter, notifications, HGW/HAG and branch assets have explicit owners and reuse constraints |
| 3. Retained/history/replaced assets have locators | VERIFIED: version/branch table, exact external source links, full untracked grouping and existing historical anchors |
| 4. No omitted necessary low-risk wiring | VERIFIED for static scoped composition: every selected current edge and asset has a destination; no known disconnected approved daily edge found; general executor/PDF/OS features require a new product contract, not a missing invocation |
| 5. Current documents do not compete | VERIFIED for inspected canonical/active direction sources: README entry, PLANS decisions, this evidence index; Bridge Direction Lock/Operator/Roadmap applicability notes preserve route governance; ECO-01 marked historical |
| 6. Latest local work preserved | VERIFIED by start/end SHA-256 comparison across all git-listed tracked/untracked nonignored files; only seven existing documents changed; no file added/deleted, HEAD/index unchanged |
| 7. Node 02 decisions separated | VERIFIED as planning input: PLANS lists only executor contract, rich-document integration, state/reviewer ownership, notifications/navigation, UI-data and any formal identity/authority choice; this continuation resolves the prior source/branch lookup gaps |

Historical continuation executor disposition: **READY_FOR_REVIEW — Node 01 consolidation candidate**.
The first submission's premature overall completion is superseded by the
criterion-level evidence above. At that time independent final review was pending;
no final ACCEPTED, runtime restoration, publication or
Node 02 activation was claimed. HTTP/hardlink restrictions and real-login/game-time
unknowns remain limitations of product verification, not hidden passes.

In that earlier continuation no executable behaviour changed, so its
environment-blocked tests were not repeated. No current product regression was established by this
continuation. The inability to verify live behaviour remains explicit rather
than being reassigned to Node 02 as uncompleted source-consolidation work.

## Phase 0 Final Daily-Use and Grand Audit Anchors

- The accepted Phase 0 Final Daily-Use Acceptance is the current Workflow
  baseline described by `PLANS.md`. Its supported scope is the already merged,
  visible localhost single-user path; local readiness is not evidence that
  external model execution is available, and no continuous end-to-end telemetry,
  service, tray, VM executor, new external API, publication automation, or
  expanded approval authority is claimed.
- Phase 0 implementation anchors include Human View closure PR #320, durable
  final-review synchronization PRs #322 and #324, local-only automatic startup
  PR #325, and startup/runbook reconciliation PR #326. These are evidence
  anchors, not independent activation authority.
- Grand Audit R1 contract-integrity remediation: PR #330, implementation commit
  `689ce71b09232833018716c01c59a795500b4cbb`, canonical merge
  `d7295ad8f226152a9c2ffbc7eabb87493f2ac713`. Duplicate fields and unconsumed
  non-comment Task Packet lines fail closed without execution authority.
- Grand Audit R2 lifecycle-truth remediation: PR #332, implementation commit
  `0a25903136f6b44258214207596535e053c85b88`, canonical merge
  `c7a167d31a9c333af26c65c7160aa069ffef9761`. Unresolved exact-request final
  reviews remain visible across requests, dispatch is not claimed before its
  durable transition, and local readiness is distinct from external execution
  availability.
- The final-regression freeze gate and post-freeze thaw conditions are normative
  in `PLANS.md`. This index only navigates to that policy; it does not satisfy
  the gate, freeze the baseline, or authorize a thaw.

## Historical Workflow v1 and Daily-UX Anchors

- Roadmap v2 tracker: Issue `#168` (historical Workflow v1 tracker)
- ChatGPT-first daily-UX closeout record: `docs/CHATGPT_FIRST_DAILY_UX_PILOT_CLOSEOUT_2026-07-31.md`. Its evidence-supported verdict is `CHATGPT-FIRST CORE DAILY UX ACCEPTED — MANUAL FOREGROUND, BOUNDED, NO ROUTINE TASK/RESULT RELAY`. It is a historical predecessor to Phase 0 Final Daily-Use Acceptance, not the current Workflow status. Evidence anchors include HAG Issue `#6` Runner ReviewBundle comment `5139431417`, HAG Issue `#6` matching `LAWBRUNNER-RESULT` comment `5139431571`, LAWB Issue `#147` launcher-preflight fail-closed status comment `5139709504`, and LAWB Issue `#147` Operator exact-dispatch fail-closed status comment `5139364732`.
- Workflow v1 Final Closeout record: `docs/WORKFLOW_V1_FINAL_CLOSEOUT.md`; it is the primary architecture, evidence, limitation, demonstration, and conditional final-transition record
- Accepted correction/publication PR: #211 on retained branch `workflow-v1-phase-c-powershell-env-correction`; accepted reviewed head `4d3b649da9c953480c5053ae8e0b1707315de3e6`; external Codex exact-head review completed with no major issues; canonical merge `38d3e96263b671a72141d0ab92b61b91a85e6c36`; post-merge canonical verification completed
- Tracker #168 historical intermediate synchronization: comment `5005537101`; it records PR #212 post-merge evidence and the then-current `REVIEW` state
- Tracker #168 reviewer-controlled final residual-review result anchor: comment `5010099708`; it records `ACCEPTED — FINAL RESIDUAL REVIEW PASSED`
- PR #213 final durable-status transition: exact reviewed head `60be637db0c237db3d53408a272fd3aaba98ec8b`; canonical merge `317cd7e9fedb153daa034c1e698819042e2e4564`; post-merge canonical verification completed
- Tracker #168 final `DONE` publication: comment `5010353117`
- Acceptance-integrity correction baseline: `a95d05388ad77963ee8cb44c0b7710a49a9d8421`
- Phase C evidence Issues: #207 first `maybe-status-check` failure; #208 corrected success; #209 first `run-reviewbundle` failure; #210 restored-CLI success and independent PASS
- PR #203: Final Closeout candidate publication; commit `368934f5c93d210c485d49180bc1c347d7d3647c`; canonical merge `c36a1b820e6f6786267057aa05d25697b9f1deca`
- PR #204: attempted `REVIEW` -> `DONE` transition; commit `240e47a77da753c9ffb619e79be1c15e20b23e7a`; canonical merge `b20a12c07cd2de7105b94b34ed2996b06f59b84a`
- RV2-03 accepted historical node: Issue `#175`
- Deferred workflow-hardening anchor: Issue `#188`
- Records and closeout planning anchor: Issue `#190`
- RV2-03 lessons publication lane: PR `#186`
- Canonical branch: `master`; PR #211 was opened against observed base snapshot `a3be6ad46e0a2a93f7fe87dfdd3c476ed3695abb`, with any later HEAD always requiring fresh verification

This section is historical navigation. `PLANS.md` remains the current
project-status authority, and this index does not itself accept, activate, or
grant authority for work. Post-merge automated P2 findings on PR #203 and PR
#204 invalidated the earlier acceptance, so both remain historical
integrity-incident evidence. PR #211 supplied the accepted correction. PR #212
was rereviewed at exact head `dd6046409505e009e95e3a68433bca147542a088`,
merged canonically at `ee4f9c06dc48719b8165b75607e51d38e7344c6b`, and
passed post-merge canonical verification. Tracker #168 comment `5005537101`
remains historical intermediate `REVIEW` evidence, and reviewer-controlled
comment `5010099708` anchors `ACCEPTED — FINAL RESIDUAL REVIEW PASSED`. PR #213
was exact-head reviewed at `60be637db0c237db3d53408a272fd3aaba98ec8b`,
merged canonically at `317cd7e9fedb153daa034c1e698819042e2e4564`, and
post-merge verified; Tracker #168 comment `5010353117` published final `DONE`.
Workflow v1 Final Closeout remains historical `DONE — FINAL DURABLE TRUTH
SYNCHRONIZED` evidence. It does not supersede the current Phase 0 baseline or
activate a later node.

## ECO-DOC-01 Durable Records

- `docs/ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md` — historical ECO-01 strategy checkpoint for the Human-Governed AI Work System, including Workflow Mainline first priority, n8n/Gateway role, bounded Workbench role, dual-track strategy, and unauthorized separation boundary.
- `docs/LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md` — ECO-02 product-validation evidence record for Workbench Phase 5.1–5.3, including the exact `PASS WITH SMALL GAPS — BOUNDED FOLLOW-UP JUSTIFIED` verdict and its limitations.

These records are durable navigation and evidence surfaces. They do not replace `PLANS.md`, fresh Git/GitHub verification, or task-specific authority. They do not activate Phase 5.4, RV2-04, repository separation, or any later node.

## WF-REENTRY Durable Record

- `docs/WF_REENTRY_NATIVE_CAPABILITY_OVERLAP_REVIEW.md` — accepted capability-overlap adjudication and native-vs-Bridge strategy checkpoint, including `KEEP`, `THIN`, `REPLACE_BY_NATIVE CANDIDATE`, and `DEFER` classifications.

This entry is navigation, not implementation authority or a replacement for current-state verification. Fresh platform, Git, GitHub, authentication, and task-specific authority verification remains required.

## OPT Records

- OPT-01: `docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.md` defines workflow optimization contracts.
- OPT-02: `docs/POST_RV2_03_MINIMAL_EVIDENCE_COLLECTOR_V1.md` documents the minimal local facts-only evidence collector prototype.
- OPT-03: `docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.md` records the historical A/B workflow benchmark.
- OPT-04: `docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.md` records the mockup-first benchmark and UI contract pattern.
- OPT-05: `docs/POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.md` records the systematic debugging profile benchmark.
- OPT-06: completed as a Chat-only REC-02 retrospective; result `GO — conditional default` for ambiguous, safety-relevant, environment-sensitive, or evidence-heavy debugging. It created no repository artifact and added no authority.
- OPT-07: `docs/POST_RV2_03_CODEBASE_MEMORY_BENCHMARK_OPT07.md` records the isolated `codebase-memory-mcp` v0.9.0 CLI benchmark; result `DONE / NO-GO`, with `13.04%` exploration-cost reduction, incomplete safety-critical relations, complete rollback, and no adoption for the current workflow.

## OPT-06 / OPT-07 Status

- OPT-06 resolved the earlier naming ambiguity by keeping the repository-native systematic-debugging follow-up as OPT-06.
- The older external codebase-memory benchmark concept was renumbered to OPT-07 before execution.
- OPT-06 is complete as a read-only retrospective and is a conditional workflow recommendation, not mandatory process.
- OPT-07 is complete and accepted as `NO-GO`; `codebase-memory-mcp` is not adopted as a required or default Local AI Workbench exploration tool.
- Neither result activates RV2-04, Issue #188, another OPT node, MCP, watchers, services, or new authority.

## Historical RV2 / Product Checkpoint

- RV2-03, RV2-P1-SYNC, RV2-04N, and Cross-Repository Bounded Proof are historical
  `DONE` evidence; they are not the current Workflow status.
- The first three mandatory Workflow v1 nodes are `DONE`: `RV2-P1-SYNC`, `RV2-04N`, and Cross-Repository Bounded Proof. Workflow v1 Final Closeout is `DONE — FINAL DURABLE TRUTH SYNCHRONIZED`.
- Accepted PR #211 candidate verification recorded targeted pycache regressions `10 passed`, Runner v1 `89 passed`, Runner v2 compatibility `4 passed`, related Runner/Bridge `810 passed`, full repository `1112 passed`, `0 failed`, and `git diff --check` exit `0`.
- Historical RV2-04 was narrowed into completed RV2-04N; historical RV2-05/07/08/09 remain deferred and RV2-06 remains partially absorbed.
- Tracker #168 comment `5005537101` remains historical intermediate `REVIEW` evidence; comment `5010099708` remains the final residual-review anchor; comment `5010353117` is the final `DONE` publication paired with PR #213 canonical merge `317cd7e9fedb153daa034c1e698819042e2e4564`.
- This final `DONE` status does not activate another node, Issue #188, Issue #190, Workbench Phase 5.4, RV2-05/07/08/09, unabsorbed RV2-06 work, a benchmark, startup, tray, service, MCP, physical separation, deferred scope, or new runtime, trusted-actor, allowlist, GitHub, or approval authority.

## Stale Surface Warnings

- Pre-Node-01 README revisions contain stale current-status and proposed-publication language; use the aligned README for entrypoints and PLANS for current disposition.
- Issue bodies may lag behind append-only comments.
- Interpret the ChatGPT-first daily-UX record by repository location: feature branch/open PR means candidate publication content; canonical `master` means durable evidence-supported content. In either case, independent post-merge verification is required before declaring operational synchronization complete.
- Tracker #168 comment `4998971940` is a historical pre-PR-#212 `REVIEW` checkpoint. Comment `5005537101` is the intermediate PR #212 evidence synchronization that retained `REVIEW`. Comment `5010099708` is the reviewer-controlled final residual-review result anchor. Comment `5010353117` is the paired tracker final `DONE` publication.
- Old PR bodies and old handoffs are historical evidence, not current truth.
- `docs/SEMI_AUTOMATED_WORKFLOW_V1.md` and `docs/SEMI_AUTOMATED_WORKFLOW_V1_PROOF_REPORT.md` are historical operating/proof evidence, not current Workflow v1 completion truth.
- `docs/SEMI_AUTOMATED_WORKFLOW_BASELINE.md` is a historical RV2-03-era operational snapshot; its commands and evidence require fresh applicability checks.
- Phase statements in `docs/CHATGPT_CODEX_BRIDGE_REPOSITORY_SEPARATION_PLAN.md` are historical design context and do not override current `PLANS.md`; the separation design remains unimplemented and unauthorized.
- Exact branch, HEAD, auth, and working tree must be freshly verified.

## Raw Evidence Boundary

- Local raw evidence, temp evidence roots, command logs, and host-specific artifacts should not be committed unless specifically approved.
- Summaries must not replace raw evidence for review.

## REC-02 Operational Field Evidence

- `docs/REC_02_OPERATIONAL_FIELD_EVIDENCE_COURSE_HOST_QUICK_RESTORE.md` — accepted real-reset field evidence showing the existing REC-02 Quick Restore path converged the course computer from a restored environment to full `READY` state across three bounded wrapper runs, with final focused pytest and Host Check exit `0`, clean Git state, and safety boundaries preserved.

This record does not reopen REC-02, classify the observed stale Layer 1 `ATTENTION` as a proven defect, authorize a script repair, or activate any later node. REC-02 remains `DONE`; single-transaction convergence after conditional browser authentication is preserved only as an improvement candidate.

## Course Host Quick Restore

- `docs/COURSE_HOST_QUICK_RESTORE_RUNBOOK.md` is the daily quick-restore runbook for reset course machines.
- `docs/COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md` remains the detailed recovery reference.
- `scripts/course_environment_restore_review.ps1` is the preferred wrapper entry point.
- `scripts/bootstrap_course_environment.ps1` is the lower-level bootstrap script and should not be the first daily manual entry unless the wrapper fails.

## Deferred Candidate Nodes

These are candidates only and are not activated by this index:

- REC-01 full records closeout
- OPS-01 Course Host Quick Restore Compression
- Issue #188 repository-native execution-gate work
- RV2-05 thin CLI facade
- unabsorbed RV2-06 execution-profile work
- RV2-07 visible operator UX
- RV2-08 login startup
- RV2-09 connector feasibility
- Native-vs-Bridge benchmark only if later evidence requires it
- physical repository separation under a separately approved migration node

## Complete Document Register

Snapshot: 2026-11-01, after Node 01 final organization. Covers every existing
tracked/nonignored-untracked md/rst/txt document, plus all docs/ structured
examples, metrics, image and placeholder assets. Binary source fixtures outside
docs are test assets, not new planning authority. No ignored credential/runtime
folders were inspected. Classification used full text, explicit reference scan,
current source ledger and scoped contracts, not filename/date alone.

CURRENT = effective entry/rules/dependencies; REUSABLE = existing reusable
interface/example/fixture; SPECIALIZED = retained scoped system/contract or pinned
compatibility evidence; HISTORICAL = prior planning/results, no current activation;
UNCERTAIN = preserved unadopted draft/placeholder. A test pin requires a stable
path, not current product authority. Reference counts below are pre-reorganization
explicit path/basename references; generic directory enumeration is noted above.
Existing Markdown/text bodies were read; source/test consumers and earlier
capability lineage informed the classifications. No historical approval is consumed.

<details>
<summary>All registered documents/assets and their retention reasons</summary>

| Path | Classification | Reference/retention basis |
|---|---|---|
| [AGENTS.md](../AGENTS.md) | CURRENT | Code/test pin: `src/companion_core/chat.py`, `src/companion_core/daily.py`, `src/companion_core/resources.py`, `tests/companion_core/test_daily.py`, `tests/companion_core/test_resources.py`, `tests/companion_core/verify_continuity.cjs`, `tests/companion_core/verify_daily_flow.cjs`, `tests/companion_core/verify_document_handoff.cjs`, `tests/companion_core/verify_experience_smoke.cjs`, `tests/companion_core/verify_resources.cjs`; retain stable path |
| [PLANS.md](../PLANS.md) | CURRENT | Code/test pin: `tests/test_local_runner_v1_timeout_guard.py`, `tests/test_local_runner_v2_compatibility.py`; retain stable path |
| [README.md](../README.md) | CURRENT | Code/test pin: `src/companion_core/chat.py`, `src/companion_core/resources.py`, `tests/companion_core/test_chat_isolation.py`, `tests/companion_core/test_chat_ui.cjs`, `tests/companion_core/test_daily.py`, `tests/companion_core/test_resources.py`, `tests/companion_core/verify_account_initialization.cjs`, `tests/companion_core/verify_continuity.cjs`, `tests/companion_core/verify_daily_flow.cjs`, `tests/companion_core/verify_document_handoff.cjs`, `tests/companion_core/verify_resource_isolation.cjs`, `tests/companion_core/verify_resources.cjs`, `tests/local_runner_bridge/test_runtime_contract_binding.py`, `tests/test_local_runner_v1_timeout_guard.py`; retain stable path |
| [api/requirements.txt](../api/requirements.txt) | CURRENT | Code/test pin: `scripts/bootstrap_course_environment.ps1`; retain stable path |
| [docs/APPROVAL_ONLY_END_TO_END_SMOKE_134.md](APPROVAL_ONLY_END_TO_END_SMOKE_134.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/APPROVAL_RECORD_VALIDATOR_SUCCESS_DECISION_NOTE_185.md](APPROVAL_RECORD_VALIDATOR_SUCCESS_DECISION_NOTE_185.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 5 explicit incoming reference(s) before reorganization |
| [docs/AWAY_TO_HOME_ADOPTION_PACKETS.md](AWAY_TO_HOME_ADOPTION_PACKETS.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/B4D_FRESH_REBOOT_SMOKE_TEST_PLAN.md](B4D_FRESH_REBOOT_SMOKE_TEST_PLAN.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md](BOUNDED_CODEX_SIDE_ACTION_PROOF_131.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 5 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_RESULT_SURFACE_PLANNING_158.md](BOUNDED_RESULT_SURFACE_PLANNING_158.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_RESULT_SURFACE_WRITEBACK_PLANNING_168.md](BOUNDED_RESULT_SURFACE_WRITEBACK_PLANNING_168.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_APPROVAL_GATE_PLANNING_180.md](BOUNDED_WRITEBACK_APPROVAL_GATE_PLANNING_180.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_APPROVAL_RECORD_SAMPLE_181.md](BOUNDED_WRITEBACK_APPROVAL_RECORD_SAMPLE_181.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 5 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_IMPLEMENTATION_BOUNDARY_PLANNING_192.md](BOUNDED_WRITEBACK_IMPLEMENTATION_BOUNDARY_PLANNING_192.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_IMPLEMENTATION_BOUNDARY_SAMPLE_193.md](BOUNDED_WRITEBACK_IMPLEMENTATION_BOUNDARY_SAMPLE_193.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_IMPLEMENTATION_BOUNDARY_VALIDATION_PLAN_194.md](BOUNDED_WRITEBACK_IMPLEMENTATION_BOUNDARY_VALIDATION_PLAN_194.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_READINESS_GATE_PLANNING_186.md](BOUNDED_WRITEBACK_READINESS_GATE_PLANNING_186.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 5 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_READINESS_GATE_SAMPLE_187.md](BOUNDED_WRITEBACK_READINESS_GATE_SAMPLE_187.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 5 explicit incoming reference(s) before reorganization |
| [docs/BOUNDED_WRITEBACK_TARGET_CONTRACT_PLAN_169.md](BOUNDED_WRITEBACK_TARGET_CONTRACT_PLAN_169.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 7 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_DIRECTION_REBASELINE_126.md](BRIDGE_DIRECTION_REBASELINE_126.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 10 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_FEASIBILITY_PROBE.md](BRIDGE_FEASIBILITY_PROBE.md) | SPECIALIZED | Code/test pin: `tests/test_bridge_feasibility_probe.py`; retain stable path |
| [docs/BRIDGE_OPERATOR_ACCELERATION_AND_PHASE3_ROADMAP_143.md](BRIDGE_OPERATOR_ACCELERATION_AND_PHASE3_ROADMAP_143.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_OPERATOR_B1_CLOSEOUT.md](BRIDGE_OPERATOR_B1_CLOSEOUT.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_OPERATOR_B1_RUNBOOK.md](BRIDGE_OPERATOR_B1_RUNBOOK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 1 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_OPERATOR_B2_RUNBOOK.md](BRIDGE_OPERATOR_B2_RUNBOOK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_OPERATOR_B3_RUNBOOK.md](BRIDGE_OPERATOR_B3_RUNBOOK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_OPERATOR_V0_SPEC.md](BRIDGE_OPERATOR_V0_SPEC.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 12 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_POLICY_PROFILES.md](BRIDGE_POLICY_PROFILES.md) | UNCERTAIN | Unadopted draft or empty placeholder; preserve, do not execute or delete; 0 explicit incoming reference(s) before reorganization |
| [docs/BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md](BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md) | SPECIALIZED | Code/test pin: `tests/test_local_runner_v2_compatibility.py`; retain stable path |
| [docs/CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md](CHATGPT_CODEX_BRIDGE_DIRECTION_LOCK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 26 explicit incoming reference(s) before reorganization |
| [docs/CHATGPT_CODEX_BRIDGE_REPOSITORY_SEPARATION_PLAN.md](CHATGPT_CODEX_BRIDGE_REPOSITORY_SEPARATION_PLAN.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/CHATGPT_FIRST_DAILY_UX_PILOT_CLOSEOUT_2026-07-31.md](CHATGPT_FIRST_DAILY_UX_PILOT_CLOSEOUT_2026-07-31.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/CHATGPT_TASK_PACKET_PUBLICATION_PROOF_129.md](CHATGPT_TASK_PACKET_PUBLICATION_PROOF_129.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 7 explicit incoming reference(s) before reorganization |
| [docs/CODEX_TASK_TEMPLATE.md](CODEX_TASK_TEMPLATE.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/CODEX_WORKFLOW.md](CODEX_WORKFLOW.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/CONTROLLED_VALID_TASK_SURFACE_COMMENT_DRAFT_155.md](CONTROLLED_VALID_TASK_SURFACE_COMMENT_DRAFT_155.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md](COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md) | SPECIALIZED | Code/test pin: `tests/local_runner_bridge/test_course_computer_environment_recovery.py`; retain stable path |
| [docs/COURSE_HOST_QUICK_RESTORE_RUNBOOK.md](COURSE_HOST_QUICK_RESTORE_RUNBOOK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 2 explicit incoming reference(s) before reorganization |
| [docs/COURSE_MACHINE_ENVIRONMENT_SETUP_RUNBOOK_152.md](COURSE_MACHINE_ENVIRONMENT_SETUP_RUNBOOK_152.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/DISPLAY_PILOT_FOREGROUND_OPERATOR_RUNBOOK.md](DISPLAY_PILOT_FOREGROUND_OPERATOR_RUNBOOK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 1 explicit incoming reference(s) before reorganization |
| [docs/ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md](ECOSYSTEM_CURRENT_STRATEGY_CHECKPOINT.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/ENGINEERING_RECORDS_INDEX.md](ENGINEERING_RECORDS_INDEX.md) | CURRENT | Code/test pin: `tests/test_local_runner_v2_compatibility.py`; retain stable path |
| [docs/EXPLICIT_GITHUB_TASK_SURFACE_FETCH_PLAN_144.md](EXPLICIT_GITHUB_TASK_SURFACE_FETCH_PLAN_144.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/EXPORT_DESTINATION_INTELLIGENCE_DESIGN_214.md](EXPORT_DESTINATION_INTELLIGENCE_DESIGN_214.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/GITHUB_READBACK_PROOF.md](GITHUB_READBACK_PROOF.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/GITHUB_VISIBLE_MARKERS_AND_READBACK.md](GITHUB_VISIBLE_MARKERS_AND_READBACK.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/HIGH_RISK_APPROVAL_PACKAGE_STANDARD.md](HIGH_RISK_APPROVAL_PACKAGE_STANDARD.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 1 explicit incoming reference(s) before reorganization |
| [docs/HOST_CHECK_HARNESS_V1.md](HOST_CHECK_HARNESS_V1.md) | SPECIALIZED | Code/test pin: `tests/test_host_check_v1_script.py`; retain stable path |
| [docs/IMPLEMENTATION_READINESS_GATE_135.md](IMPLEMENTATION_READINESS_GATE_135.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md](LOCAL_AI_WORKBENCH_PRODUCT_VALIDATION_PHASE5_1_TO_5_3.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_APPROVAL_RECORD_VALIDATION_PLAN_182.md](LOCAL_APPROVAL_RECORD_VALIDATION_PLAN_182.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 4 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_APPROVAL_RECORD_VALIDATOR_SMOKE_EVIDENCE_184.md](LOCAL_APPROVAL_RECORD_VALIDATOR_SMOKE_EVIDENCE_184.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_OPERATOR.md](LOCAL_OPERATOR.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 1 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_RELAY_READBACK_SMOKE.md](LOCAL_RELAY_READBACK_SMOKE.md) | SPECIALIZED | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/LOCAL_RESULT_SURFACE_DRAFT_AND_READBACK_PLAN_159.md](LOCAL_RESULT_SURFACE_DRAFT_AND_READBACK_PLAN_159.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_RUNNER_BRIDGE_V0_ARCHITECTURE.md](LOCAL_RUNNER_BRIDGE_V0_ARCHITECTURE.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_RUNNER_RESULT_PACKET_V1.md](LOCAL_RUNNER_RESULT_PACKET_V1.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 11 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_RUNNER_TASK_PACKET_V1.md](LOCAL_RUNNER_TASK_PACKET_V1.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 10 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_BUILDER_PLAN_176.md](LOCAL_WRITEBACK_DRY_RUN_PREVIEW_BUILDER_PLAN_176.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_PLANNING_174.md](LOCAL_WRITEBACK_DRY_RUN_PREVIEW_PLANNING_174.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SAMPLE_175.md](LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SAMPLE_175.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SMOKE_EVIDENCE_178.md](LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SMOKE_EVIDENCE_178.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 6 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SUCCESS_DECISION_NOTE_179.md](LOCAL_WRITEBACK_DRY_RUN_PREVIEW_SUCCESS_DECISION_NOTE_179.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 8 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_IMPLEMENTATION_BOUNDARY_VALIDATOR_SMOKE_EVIDENCE_196.md](LOCAL_WRITEBACK_IMPLEMENTATION_BOUNDARY_VALIDATOR_SMOKE_EVIDENCE_196.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_READINESS_GATE_VALIDATION_PLAN_188.md](LOCAL_WRITEBACK_READINESS_GATE_VALIDATION_PLAN_188.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 4 explicit incoming reference(s) before reorganization |
| [docs/LOCAL_WRITEBACK_READINESS_GATE_VALIDATOR_SMOKE_EVIDENCE_190.md](LOCAL_WRITEBACK_READINESS_GATE_VALIDATOR_SMOKE_EVIDENCE_190.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/LV45_OPERATING_SOP.md](LV45_OPERATING_SOP.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 3 explicit incoming reference(s) before reorganization |
| [docs/LV5_SAFE_DESIGN.md](LV5_SAFE_DESIGN.md) | UNCERTAIN | Unadopted draft or empty placeholder; preserve, do not execute or delete; 1 explicit incoming reference(s) before reorganization |
| [docs/LV5_SAFE_QUEUE_RUNNER_DESIGN.md](LV5_SAFE_QUEUE_RUNNER_DESIGN.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 2 explicit incoming reference(s) before reorganization |
| [docs/MINIMAL_BRIDGE_RUNNER_PLAN_136.md](MINIMAL_BRIDGE_RUNNER_PLAN_136.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/NO_AGENT_LOCAL_COMMIT_RAIL_SOP.md](NO_AGENT_LOCAL_COMMIT_RAIL_SOP.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 1 explicit incoming reference(s) before reorganization |
| [docs/NO_COPY_NO_PASTE_BRIDGE_SMOKE_133.md](NO_COPY_NO_PASTE_BRIDGE_SMOKE_133.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/PHASE3_CONTROLLED_FETCH_VALIDATION_SUCCESS_DECISION_NOTE_157.md](PHASE3_CONTROLLED_FETCH_VALIDATION_SUCCESS_DECISION_NOTE_157.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/PHASE3_LIVE_FETCH_PROBE_DECISION_NOTE_154.md](PHASE3_LIVE_FETCH_PROBE_DECISION_NOTE_154.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/PHASE3_LIVE_FETCH_TO_RESULT_SURFACE_SUCCESS_DECISION_NOTE_167.md](PHASE3_LIVE_FETCH_TO_RESULT_SURFACE_SUCCESS_DECISION_NOTE_167.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 5 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_CODEBASE_MEMORY_BENCHMARK_OPT07.md](POST_RV2_03_CODEBASE_MEMORY_BENCHMARK_OPT07.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_MINIMAL_EVIDENCE_COLLECTOR_V1.md](POST_RV2_03_MINIMAL_EVIDENCE_COLLECTOR_V1.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 2 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.md](POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.metrics.json](POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.metrics.json) | HISTORICAL | Observed benchmark data, retained with referenced benchmark report; 0 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.profile.json](POST_RV2_03_SYSTEMATIC_DEBUGGING_PROFILE_BENCHMARK_OPT05.profile.json) | REUSABLE | Existing example/schema/presentation asset; not an execution or approval capability; 2 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.md](POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.metrics.json](POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.metrics.json) | HISTORICAL | Observed benchmark data, retained with referenced benchmark report; 1 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.mockup.html](POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.mockup.html) | REUSABLE | Existing example/schema/presentation asset; not an execution or approval capability; 1 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.ui_contract.json](POST_RV2_03_UI_MOCKUP_FIRST_BENCHMARK_OPT04.ui_contract.json) | REUSABLE | Existing example/schema/presentation asset; not an execution or approval capability; 3 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.md](POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.metrics.json](POST_RV2_03_WORKFLOW_OPTIMIZATION_BENCHMARK_OPT03.metrics.json) | HISTORICAL | Observed benchmark data, retained with referenced benchmark report; 0 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CLOSEOUT.md](POST_RV2_03_WORKFLOW_OPTIMIZATION_CLOSEOUT.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.md](POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 3 explicit incoming reference(s) before reorganization |
| [docs/POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.schema.examples.json](POST_RV2_03_WORKFLOW_OPTIMIZATION_CONTRACTS_V1.schema.examples.json) | REUSABLE | Existing example/schema/presentation asset; not an execution or approval capability; 1 explicit incoming reference(s) before reorganization |
| [docs/PRODUCT_DIRECTION_ALIGNMENT_204.md](PRODUCT_DIRECTION_ALIGNMENT_204.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/PROJECT_DEMO_FLOW_OVERVIEW_198.md](PROJECT_DEMO_FLOW_OVERVIEW_198.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 2 explicit incoming reference(s) before reorganization |
| [docs/QUEUE_RUNNER_OPERATOR_EXAMPLE.md](QUEUE_RUNNER_OPERATOR_EXAMPLE.md) | SPECIALIZED | Code/test pin: `tests/test_local_runner_v2_operator_smoke.py`; retain stable path |
| [docs/READINESS_GATE_VALIDATOR_SUCCESS_DECISION_NOTE_191.md](READINESS_GATE_VALIDATOR_SUCCESS_DECISION_NOTE_191.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/READ_ONLY_VALIDATOR_IMPLEMENTATION_PLAN_137.md](READ_ONLY_VALIDATOR_IMPLEMENTATION_PLAN_137.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/REC_02_OPERATIONAL_FIELD_EVIDENCE_COURSE_HOST_QUICK_RESTORE.md](REC_02_OPERATIONAL_FIELD_EVIDENCE_COURSE_HOST_QUICK_RESTORE.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/RELAY_TASK_FETCH_PROOF_130.md](RELAY_TASK_FETCH_PROOF_130.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 6 explicit incoming reference(s) before reorganization |
| [docs/RESULT_PACKET_WRITEBACK_PROOF_132.md](RESULT_PACKET_WRITEBACK_PROOF_132.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 4 explicit incoming reference(s) before reorganization |
| [docs/REVIEWER_DEMO_SMOKE_CHECKLIST_201.md](REVIEWER_DEMO_SMOKE_CHECKLIST_201.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/RISK_LEVELS_AND_APPROVAL_GATES.md](RISK_LEVELS_AND_APPROVAL_GATES.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/RUNNER_V0.md](RUNNER_V0.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/RUNNER_V1.md](RUNNER_V1.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/RUNNER_V1_CODEX_CLI_SMOKE.md](RUNNER_V1_CODEX_CLI_SMOKE.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/RUNNER_V2.md](RUNNER_V2.md) | SPECIALIZED | Code/test pin: `tests/test_local_dispatcher_v1.py`, `tests/test_local_runner_v2_runner_result_summary.py`; retain stable path |
| [docs/RV2_03_PUBLICATION_PREFLIGHT_V1.md](RV2_03_PUBLICATION_PREFLIGHT_V1.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/RV2_03_REQUEST_LIFECYCLE_V1.md](RV2_03_REQUEST_LIFECYCLE_V1.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 0 explicit incoming reference(s) before reorganization |
| [docs/SEMI_AUTOMATED_WORKFLOW_BASELINE.md](SEMI_AUTOMATED_WORKFLOW_BASELINE.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/SEMI_AUTOMATED_WORKFLOW_V1.md](SEMI_AUTOMATED_WORKFLOW_V1.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 2 explicit incoming reference(s) before reorganization |
| [docs/SEMI_AUTOMATED_WORKFLOW_V1_PROOF_REPORT.md](SEMI_AUTOMATED_WORKFLOW_V1_PROOF_REPORT.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 1 explicit incoming reference(s) before reorganization |
| [docs/TASK_AND_RESULT_SURFACE_V1.md](TASK_AND_RESULT_SURFACE_V1.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 8 explicit incoming reference(s) before reorganization |
| [docs/TASK_FIRST_UI_REDESIGN_TARGET_223.md](TASK_FIRST_UI_REDESIGN_TARGET_223.md) | UNCERTAIN | Unadopted draft or empty placeholder; preserve, do not execute or delete; 0 explicit incoming reference(s) before reorganization |
| [docs/TASK_PACKET_V1_1_DISCIPLINE_REPORT.md](TASK_PACKET_V1_1_DISCIPLINE_REPORT.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/UI_PRESENTATION_REDESIGN_PLAN_219.md](UI_PRESENTATION_REDESIGN_PLAN_219.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/VALIDATOR_HARDENING_PLAN_139.md](VALIDATOR_HARDENING_PLAN_139.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 0 explicit incoming reference(s) before reorganization |
| [docs/WF_REENTRY_NATIVE_CAPABILITY_OVERLAP_REVIEW.md](WF_REENTRY_NATIVE_CAPABILITY_OVERLAP_REVIEW.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 2 explicit incoming reference(s) before reorganization |
| [docs/WORKFLOW_ACCEPTANCE_INTEGRITY_PROTOCOL.md](WORKFLOW_ACCEPTANCE_INTEGRITY_PROTOCOL.md) | CURRENT | Current entry, governing authority or declared runtime dependency; 3 explicit incoming reference(s) before reorganization |
| [docs/WORKFLOW_V1_FINAL_CLOSEOUT.md](WORKFLOW_V1_FINAL_CLOSEOUT.md) | SPECIALIZED | Code/test pin: `tests/test_local_runner_v2_compatibility.py`; retain stable path |
| [docs/WRITEBACK_BOUNDARY_CHAIN_COMPLETION_DECISION_NOTE_197.md](WRITEBACK_BOUNDARY_CHAIN_COMPLETION_DECISION_NOTE_197.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/WRITEBACK_TARGET_CONTRACT_LOCAL_VALIDATION_PLAN_171.md](WRITEBACK_TARGET_CONTRACT_LOCAL_VALIDATION_PLAN_171.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 3 explicit incoming reference(s) before reorganization |
| [docs/WRITEBACK_TARGET_CONTRACT_SAMPLE_170.md](WRITEBACK_TARGET_CONTRACT_SAMPLE_170.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 4 explicit incoming reference(s) before reorganization |
| [docs/WRITEBACK_TARGET_CONTRACT_VALIDATOR_SUCCESS_DECISION_NOTE_173.md](WRITEBACK_TARGET_CONTRACT_VALIDATOR_SUCCESS_DECISION_NOTE_173.md) | HISTORICAL | Prior planning/result evidence; no production/test caller; current decisions belong to PLANS.md; 7 explicit incoming reference(s) before reorganization |
| [docs/archive/AUTHENTICATED_EXPLICIT_COMMENT_RETRY_SMOKE_EVIDENCE_151.md](archive/AUTHENTICATED_EXPLICIT_COMMENT_RETRY_SMOKE_EVIDENCE_151.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/AUTHENTICATED_EXPLICIT_COMMENT_RETRY_SMOKE_EVIDENCE_153.md](archive/AUTHENTICATED_EXPLICIT_COMMENT_RETRY_SMOKE_EVIDENCE_153.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/AUTHENTICATED_LIVE_EXPLICIT_FETCH_SMOKE_EVIDENCE_150.md](archive/AUTHENTICATED_LIVE_EXPLICIT_FETCH_SMOKE_EVIDENCE_150.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/BOUNDED_LIVE_EXPLICIT_FETCH_SMOKE_EVIDENCE_149.md](archive/BOUNDED_LIVE_EXPLICIT_FETCH_SMOKE_EVIDENCE_149.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/CONTROLLED_LIVE_EXPLICIT_FETCH_TO_RESULT_SURFACE_SMOKE_EVIDENCE_166.md](archive/CONTROLLED_LIVE_EXPLICIT_FETCH_TO_RESULT_SURFACE_SMOKE_EVIDENCE_166.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/CONTROLLED_VALID_TASK_SURFACE_ISSUE_BODY_LIVE_FETCH_SMOKE_EVIDENCE_156.md](archive/CONTROLLED_VALID_TASK_SURFACE_ISSUE_BODY_LIVE_FETCH_SMOKE_EVIDENCE_156.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/CURRENT_PRODUCT_ROADMAP_212.md](archive/CURRENT_PRODUCT_ROADMAP_212.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/EXPLICIT_FETCH_SMOKE_EVIDENCE_147.md](archive/EXPLICIT_FETCH_SMOKE_EVIDENCE_147.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/LOCAL_RESULT_SURFACE_STDOUT_SMOKE_EVIDENCE_160.md](archive/LOCAL_RESULT_SURFACE_STDOUT_SMOKE_EVIDENCE_160.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/LOCAL_TEXT_FILE_SMOKE_EVIDENCE_148.md](archive/LOCAL_TEXT_FILE_SMOKE_EVIDENCE_148.md) | HISTORICAL | Archived prior record, no pre-existing in-repository caller; original bytes preserved; 0 explicit incoming reference(s) before reorganization |
| [docs/archive/README.md](archive/README.md) | CURRENT | Archive navigation only; does not own policy or planning; 0 explicit incoming reference(s) before reorganization |
| [docs/bridge_result_packet.codex_capability_probe.example.json](bridge_result_packet.codex_capability_probe.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_result_packet.codex_command_smoke.example.json](bridge_result_packet.codex_command_smoke.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_result_packet.example.json](bridge_result_packet.example.json) | REUSABLE | Code/test pin: `tests/test_bridge_feasibility_probe.py`; retain stable path |
| [docs/bridge_result_packet.github_readback_smoke.example.json](bridge_result_packet.github_readback_smoke.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_result_packet.readback_smoke.example.json](bridge_result_packet.readback_smoke.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_task_packet.codex_capability_probe.example.json](bridge_task_packet.codex_capability_probe.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_task_packet.codex_command_smoke.example.json](bridge_task_packet.codex_command_smoke.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_task_packet.example.json](bridge_task_packet.example.json) | REUSABLE | Code/test pin: `tests/test_bridge_feasibility_probe.py`; retain stable path |
| [docs/bridge_task_packet.github_readback_smoke.example.json](bridge_task_packet.github_readback_smoke.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/bridge_task_packet.readback_smoke.example.json](bridge_task_packet.readback_smoke.example.json) | REUSABLE | Code/test pin: `tests/test_local_bridge_relay_smoke.py`; retain stable path |
| [docs/examples/approval_only_end_to_end_smoke.example.md](examples/approval_only_end_to_end_smoke.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 1 explicit incoming reference(s) before reorganization |
| [docs/examples/bounded_codex_side_action.example.md](examples/bounded_codex_side_action.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 1 explicit incoming reference(s) before reorganization |
| [docs/examples/chatgpt_task_packet_publication.example.md](examples/chatgpt_task_packet_publication.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 1 explicit incoming reference(s) before reorganization |
| [docs/examples/implementation_readiness_gate.example.md](examples/implementation_readiness_gate.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/examples/local_runner_result_packet.example.md](examples/local_runner_result_packet.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 2 explicit incoming reference(s) before reorganization |
| [docs/examples/local_runner_task_packet.example.md](examples/local_runner_task_packet.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 1 explicit incoming reference(s) before reorganization |
| [docs/examples/minimal_bridge_runner_plan.example.md](examples/minimal_bridge_runner_plan.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/examples/no_copy_no_paste_bridge_smoke.example.md](examples/no_copy_no_paste_bridge_smoke.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/examples/read_only_validator_implementation_plan.example.md](examples/read_only_validator_implementation_plan.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/examples/relay_task_fetch.example.md](examples/relay_task_fetch.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/examples/result_packet_writeback.example.md](examples/result_packet_writeback.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 1 explicit incoming reference(s) before reorganization |
| [docs/examples/task_result_surface.example.md](examples/task_result_surface.example.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [docs/images/local-document-workbench-overview.png](images/local-document-workbench-overview.png) | REUSABLE | Existing example/schema/presentation asset; not an execution or approval capability; 1 explicit incoming reference(s) before reorganization |
| [docs/prompts/.gitkeep](prompts/.gitkeep) | UNCERTAIN | Empty reserved prompt directory, not a prompt registry; 0 explicit incoming reference(s) before reorganization |
| [docs/queue_runner_reviewbundle_handoff_queue.example.json](queue_runner_reviewbundle_handoff_queue.example.json) | REUSABLE | Code/test pin: `tests/test_local_runner_v2_operator_smoke.py`; retain stable path |
| [requirements-companion.txt](../requirements-companion.txt) | CURRENT | Code/test pin: `Open-Companion.cmd`; retain stable path |
| [requirements-course.txt](../requirements-course.txt) | SPECIALIZED | Code/test pin: `tests/test_bootstrap_course_environment.py`; retain stable path |
| [src/local_runner_bridge/AGENTS.md](../src/local_runner_bridge/AGENTS.md) | SPECIALIZED | Retained scoped execution/operating contract; not the NEXUS daily entry; 5 explicit incoming reference(s) before reorganization |
| [tests/companion_core/LC-Bridge-01-Test.md](../tests/companion_core/LC-Bridge-01-Test.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [tests/companion_core/LC-WorkUX-01-Test.md](../tests/companion_core/LC-WorkUX-01-Test.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [tests/fixtures/documents/sample_log.txt](../tests/fixtures/documents/sample_log.txt) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [tests/fixtures/documents/sample_note.md](../tests/fixtures/documents/sample_note.md) | REUSABLE | Reusable fixture, example, design constraint or demonstrated method; not activation authority; 0 explicit incoming reference(s) before reorganization |
| [tests/fixtures/task_requirements/requirements_no_match.md](../tests/fixtures/task_requirements/requirements_no_match.md) | REUSABLE | Code/test pin: `tests/api/test_tasks.py`; retain stable path |
| [tests/fixtures/task_requirements/requirements_sample.md](../tests/fixtures/task_requirements/requirements_sample.md) | REUSABLE | Code/test pin: `tests/api/test_tasks.py`; retain stable path |

| [docs/archive/PLANS_ECOSYSTEM_CHECKPOINT.md](archive/PLANS_ECOSYSTEM_CHECKPOINT.md) | HISTORICAL | Prior PLANS ecosystem/history moved verbatim; current freeze rules retained in PLANS |

</details>
