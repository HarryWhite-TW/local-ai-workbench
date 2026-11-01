# Local Document-to-Knowledge Workbench

`local-ai-workbench` is a localhost, single-user, local-first document-to-knowledge
portfolio project. The repository also contains the **local NEXUS candidate**,
which is intended to become the user's personal AI entrypoint. That future
blueprint does not rename the public showcase or grant execution authority.

## Start Here

| Question | Source |
|---|---|
| What is the current direction and active task? | [PLANS.md](PLANS.md) — the sole current product/status plan |
| What rules and permissions apply? | [AGENTS.md](AGENTS.md); scoped Bridge rules apply only when that route is used/changed |
| Is a feature already implemented, and where? | [Source connections and reuse](docs/ENGINEERING_RECORDS_INDEX.md#node-01-source-connections-and-reuse) |
| Which documents are current or historical? | [Complete document register](docs/ENGINEERING_RECORDS_INDEX.md#complete-document-register) |
| How can development tools reuse a capability? | [Project capability library](#project-capability-library) |
| Where are isolated old records? | [Historical archive](docs/archive/README.md) |

## Effective Version and Architecture

This **Draft PR candidate**, on `codex/node01-consolidated-candidate-20261101`,
contains the retained NEXUS sources and Node 01 consolidation. It is not merged
into master or a released daily-use product. The pre-publication source was HEAD
`6c1eac3e8be6f2b6efc5ba58e5289db5972a1f71` plus retained working-tree sources.
HEAD alone omits the daily/chat/resources/native-reader work. GitHub master was
last observed at `661f2b77a6f4d42d8583eb10e396e2a91a35a571`; its Companion
surface has the known syntax defect corrected in local HEAD. These are dated
source identities, not a claim that a published release contains the candidate.

| Entry / owner | Implemented capability | Boundary |
|---|---|---|
| `Open-Companion.cmd` -> `src.companion_core.daily` | SIWC chat, project association, bounded text/link previews, explicit work proposal/review, UI continuity, optional native Codex history | Candidate-only NEXUS source; work is a seven-file read-only AST audit, not general engineering |
| `web/` -> `api/` | Document scan/index/search, deterministic summaries/decisions, PDF/DOCX extraction and approved Markdown export | Formal document showcase; not wired into NEXUS's text-document panel |
| `src.project_capabilities` | Existing deterministic requirement extraction and normalization | Development-tool reuse, no NEXUS UI integration or tool authority |
| `src/companion_core/{__main__,surface,codex}.py` | Trusted-host read-only Codex execution and shared review contracts | Specialized alternative host, not the daily SIWC entry or Native Reader |
| `src/local_runner_bridge/`, `scripts/` | Governed Bridge/Dispatcher/Runner, notifications, Panel/Observability/Sanctuary/Unified Shell | Specialized route, independent state/approval; never a required NEXUS launch step |

Native Reader reads history only and reports live state `UNKNOWN`. Floating
Companion is a page dialog, not an OS overlay. HGW/HAG are separate retained
products/contracts; neither is installed as NEXUS runtime. Detailed callers,
versions and reuse limits are in the engineering index.

## NEXUS Local Candidate Entry

On Windows, from this repository root with the existing Companion dependencies
installed in `.venv`:

```powershell
.\Open-Companion.cmd
```

Equivalent foreground entry:

```powershell
.venv\Scripts\python.exe -B -m src.companion_core.daily --workspace .
```

`--help` describes isolated data/review directories and preview-port options.
The launcher opens loopback UI; stopping the host ends availability. Closing a
browser tab does not confirm task cancellation. SIWC uses its own local account
store and explicit sources, without inheriting ChatGPT history/tools/memory.
Review [requirements-companion.txt](requirements-companion.txt) before any
separately chosen dependency installation. The two `Open-LC-*-Test.cmd` launchers
run synthetic fixtures; they are not the authenticated daily product.

## Project Capability Library

A thin local CLI and direct exports call **the original**
`api.app.services.task_extractors` functions. No second extraction algorithm,
plugin loader, provider connection or background service is introduced.
From the repository root, Python standard library is sufficient:

```powershell
.venv\Scripts\python.exe -B -m src.project_capabilities list
"The workbench must preserve source files." | .venv\Scripts\python.exe -B -m src.project_capabilities extract-requirements
```

For reproducible UTF-8 input independent of shell encoding:

```powershell
.venv\Scripts\python.exe -B -c "import json; from src.project_capabilities import extract_requirements_v1; print(json.dumps(extract_requirements_v1('The workbench must preserve source files.')))"
```

Input is explicitly supplied text; output is JSON with items, excerpts and match
reasons. CLI input is limited to 1 MiB. This is English heading/modal matching,
not semantic reasoning. Python exports are the existing callable objects.
The CLI has no file-path, shell, credential or network action. Developer access
does not authorize arbitrary AI access to resources or add this feature to NEXUS.
Contracts, source/version and actual verification are in the index.

## Document Showcase Setup and Demo

The showcase needs the declared API/Web dependencies; this consolidation does
not install them. In an environment where they are already available:

```powershell
.venv\Scripts\python.exe -m uvicorn api.app.main:app --reload
```

In another terminal, run `npm run dev` from `web/`. API is normally at
`http://127.0.0.1:8000`, Web at `http://127.0.0.1:5173`.
See [api/requirements.txt](api/requirements.txt) and `web/package.json` for setup
requirements, and the [document demo](docs/PROJECT_DEMO_FLOW_OVERVIEW_198.md).
Scan -> select -> summary -> preview -> check destination -> export -> audit.
Obsidian-ready means Markdown output, not plugin/API integration or two-way sync.
Source documents are not automatically modified. No OCR, semantic search,
background document sync, autonomous publication or external model in this
showcase is claimed. NEXUS SIWC chat is a separate model-backed candidate.

## Verification and Safety

New capability checks:

```powershell
.venv\Scripts\python.exe -B -m pytest tests/test_project_capabilities.py -q -p no:cacheprovider
```

Known HTTP `WinError 10013` and atomic-hardlink `WinError 5` restrictions remain;
static checks and pure capability tests do not establish full real daily use.
Execution, technical acceptance and publication permission remain separate.
Node 01 ends at READY_FOR_REVIEW; Node 02 and publishing require subsequent
explicit authority. Historical roadmaps, examples and completion records do
not activate work. The [engineering index](docs/ENGINEERING_RECORDS_INDEX.md)
keeps source-level evidence and verification limits.
