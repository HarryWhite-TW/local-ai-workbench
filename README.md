# Local Document-to-Knowledge Workbench

## NEXUS HL-09E Trace Workspace 已接受基準（2026-11-27）

**HL-09E 已獲 TECHNICAL ACCEPTED + PRODUCT ACCEPTED。** 接受範圍涵蓋 Presence、Focus、Trace、實際材質整合、日常輸入、工作事件呈現及既有可信唯讀工程旅程。原生工作已完成，診斷收據仍為 `RESULT_PENDING_REVIEW`，報告個別結論仍須獨立審查。使用者接受現有可用成果並結束 HL-09 UI 投資。下一階段核心 AI 能力主線尚待 ChatGPT 裁決。 [正式裁決與驗收限制](docs/hl09e-decision.json)

### Windows 獨立恢復

在新目錄將 `nexus-hl09e-accepted` 複製為 `candidate`，讓 `.venv`、`runtime` 及各自的本機資料與 `candidate` 相鄰。沿用下方的一般安裝或離線還原方式，使用 Python **3.14.6 x64** 及原有鎖定檔。

```powershell
git clone --single-branch --branch nexus-hl09e-accepted https://github.com/HarryWhite-TW/local-ai-workbench.git candidate
Set-Location candidate
.\Restore-HL05-Runtime.cmd
.\Open-HL09E-Companion.cmd
```

離線還原須事先放置已保全的 `runtime/site-packages.zip` 與 `runtime/runtime-lock.json`。啟動器使用父目錄的 `.venv`，預設開啟 <http://127.0.0.1:47731/#chat>。工作資料在同層 `engineering-project`，新目錄會自行建立工作區及讀入正式知識種子。原工作區的私人資料與登入留在原處。

材質使用隨程式發行的 Paper Shaders 0.0.82 Liquid Metal 子集，執行時由本機提供。第三方程式適用 Apache-2.0，原始 LICENSE 與 NOTICE 隨附，自有整合的來源與建置方式另有記載。 [Paper Shaders 來源與授權](src/companion_core/third_party/paper-shaders/README.md)

## NEXUS Windows 已接受基準（2026-11-26）

此節保留 HL-09C Trustworthy Engineering Workspace 的歷史發行說明。其接受範圍包含 HL-09B 自然協作改善。

| GitHub 分支 | 用途 | Windows 啟動器 |
| --- | --- | --- |
| `nexus-hl05-accepted` | HL-05 技術與產品接受的穩定檢查點 | `Open-HL05-Project-Companion.cmd` |
| `nexus-hl06-checkpoint` | HL-06 受控唯讀工程協作已接受基準 | `Open-HL06-Engineering-Companion.cmd` |
| `nexus-hl07-accepted` | HL-07 模型能力目錄已接受基準 | `Open-HL07-Catalog-Companion.cmd` |
| `nexus-hl09a-accepted` | HL-09A 日常輸入與圖片理解已接受基準 | `Open-HL09A-Companion.cmd` |
| `nexus-hl09c-accepted` | HL-09C 可信工程工作區已接受基準 | `Open-HL09C-Companion.cmd` |

### 正式狀態

HL-01 A 為技術與產品接受的限定研究參考，獨立程式與合成驗證在 [research/hl01](research/hl01/README.md)。HL-02 完成整合可行性審查。HL-03 的自然工作助手取得技術與核心產品接受。HL-04 的文件交付、長對話導航及限定模型切換取得技術與產品接受。HL-05 的真實專案知識、受控更新與規劃交付已獲 **TECHNICAL ACCEPTED + PRODUCT ACCEPTED**，限實際交付範圍。

**HL-06 已獲 TECHNICAL ACCEPTED + PRODUCT ACCEPTED。** 接受範圍涵蓋自然工程委託、限定唯讀 Codex 診斷、真人批准、受控執行、結果自動回傳、工作收據保存、當輪詳文分享、模型證據分析、自然追問、重啟保存及跨對話自主查找。純收據回答只取用當輪問題與獲准的收據。純專案與混合來源回答仍須符合相應的引用要求。複雜前文依賴與模型選擇證據模式仍有一般性限制。

診斷收據仍為 `RESULT_PENDING_REVIEW`，報告中的技術建議仍須另行裁決。較早的 `PARTIAL_WITH_EVIDENCE` 保留為歷史狀態。首次原生終態 `UNKNOWN`、後續分析的 `UsageLimitExceeded`、詳文確認逾期及新設備的引用檢查失敗均保留為原觀測。最後在新設備完成真模型分析、真人分享與跨對話查找。

**HL-07 已獲 TECHNICAL ACCEPTED + PRODUCT ACCEPTED。** 接受範圍涵蓋官方模型目錄、按模型列出推理強度、實測標記、目錄回退、跨模型對話與重啟保存。GPT-6.2 Sol 與 Astra 各有 Low、Medium、High、XHigh、Max 的 Provider 實測。Sol Low、Medium、High 和 Astra Max 也有 NEXUS 產品實測，其餘六組維持 Provider 實測標記。現有 SDK 未支援 Ultra，驗收期間沒有送出 Ultra 請求。

核對過的桌面 App 內建 Codex CLI `0.171.0-alpha.13.2` 僅受信任執行唯讀目錄查詢。App 更新後須重新核對執行檔。原生工程委派仍使用 HL-06 的 `0.162.1` 與既有雜湊、MXC、真人批准、工作區及收據門檻。目錄失效時保留可信回退，獨立 Provider 實測的選項可能暫時無法選取。歷史實測仍受當前帳戶資格與額度限制。Astra Max 的產品驗收涵蓋一般聊天與跨模型接續，完整原生委派旅程尚未獨立驗證。

**HL-08 已收束，狀態為 CLOSED — PARTIAL_WITH_EVIDENCE。** 保留隔離技術及實際工程失敗證據。HL-09A 從 HL-07 基準接續，沿用 HL-06 已接受的唯讀工程委派權限。

**HL-09A 已獲 TECHNICAL ACCEPTED + PRODUCT ACCEPTED。** 接受範圍包含 Enter 傳送、Shift+Enter 換行、Ctrl/Cmd+Enter、中文 IME 防誤送及滑鼠傳送。Windows 真人已驗證圖片選取、剪貼簿貼圖與拖放，附件可預覽、移除或送出並保存在本機對話。

GPT-6.2 Sol Medium 已完成圖片理解、同對話文字追問及重啟讀回。每則最多一張 PNG、JPEG 或 WebP，上限 4096 × 4096 與 4 MiB。後續文字回合保留對話文字，再次分析原圖需要明確重新附加。其他模型與推理強度的圖片能力尚未實測，圖片生成尚未實作。接受依據包含 121 項 Python 與 16 項 Node 測試。兩支舊 Playwright 腳本因缺少模組未執行。

**HL-09B Natural Collaboration Behavior** 曾為 `PARTIAL_WITH_EVIDENCE`。自然討論已有正向真模型證據，較早的提案承諾曾超出固定快照能力。自然協作及工具能力對齊改善已併入 HL-09C，HL-09B 無需獨立發布。

**HL-09C 已獲 TECHNICAL ACCEPTED + PRODUCT ACCEPTED。** 接受範圍包含自然討論、適時工程提案、主機核定交付契約、舊提案失效、來源預覽、真人批准、對話內工單、可收合工作監控及結果回傳。原生唯讀診斷已 `COMPLETED`，MXC 投影經核對，程序已退出，成果已保存並回到原對話。ChatGPT 已唯讀核對診斷核心結論。完整快照行號未逐一重驗，原收據仍為 `RESULT_PENDING_REVIEW`。

123 項 Python、18 項 Node 測試通過。中途執行階段由持久事件證明，瀏覽器直接核對批准前、完成後及重載。服務重啟未驗證，失敗、取消及 `UNKNOWN` 由自動化回歸驗證。工程能力限既有固定快照唯讀診斷，無即時 Git、Shell、測試或程式修改能力。

HL-09C 已正式收束。下一個建議成果為 HL-09D Visual Collaboration，技術方向尚待 ChatGPT 裁決。完整物流式進度時間軸及整體視覺打磨留待 HL-09E。Windows-first 方向維持，本機與異地 Windows 為主要開發路徑，手機可使用 ChatGPT、Codex Cloud 按需補充，GitHub 保存跨設備工程基準。M1 與 SIWC 維持停止，SIWC 工具能力仍未實測。

[HL-09C 正式裁決](docs/hl09c-decision.json) · [HL-09A 正式裁決](docs/hl09a-decision.json) · [HL-07 正式裁決](docs/hl07-decision.json) · [HL-06 正式裁決](docs/hl06-decision.json)

### 另一台 Windows 電腦

需要 Git、Windows x64、Python **3.14.6 x64**。每個版本各用自己的父目錄，讓 `candidate`、`.venv` 與本機資料相鄰。HL-09C 可獨立恢復，使用該工作區自己的 Python 虛擬環境。

```powershell
$branch = 'nexus-hl09c-accepted'
$destination = Join-Path (Get-Location).Path $branch
New-Item -ItemType Directory -Path $destination -ErrorAction Stop
git clone --single-branch --branch $branch https://github.com/HarryWhite-TW/local-ai-workbench.git (Join-Path $destination 'candidate')
if ($LASTEXITCODE -ne 0) { throw 'Git clone failed.' }
Set-Location (Join-Path $destination 'candidate')
git rev-parse HEAD
```

選擇一個環境恢復方式。

- **一般安裝。** 從預設官方套件來源建立並安裝鎖定版本。若 Python 不在 Windows Launcher 清單，可以本機 Python 3.14.6 x64 的完整執行檔路徑取代 `py -3.14`。

  ```powershell
  py -3.14 -c 'import sys,struct; assert sys.version_info[:3] == (3,14,6) and struct.calcsize("P") == 8'
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.14.6 x64 required.' }
  py -3.14 -m venv ..\.venv
  if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
  & ..\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements-companion-lock.txt -r requirements-companion.txt
  if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency install failed.' }
  & ..\.venv\Scripts\python.exe -m pip check
  ```

- **離線還原。** 安全攜帶本機保全的 `runtime/site-packages.zip` 與 `runtime/runtime-lock.json`，放在 `candidate` 旁的 `runtime`。安裝相容 Python 後在 `candidate` 執行 `.\Restore-HL05-Runtime.cmd`。若 Python 不在預設使用者安裝位置，先設定 `NEXUS_PYTHON_314` 為該 Python 執行檔完整路徑。腳本會比對套件包 SHA-256，建立同層新的 `.venv` 並執行套件檢查。

試用前在新電腦使用自己的正常官方 Codex 登入。Windows 原生委派驗證的版本為 `codex-cli 0.162.1`，使用現有 Node.js/npm 的標準 Windows npm 路徑。需要重建時可執行 `npm install -g @openai/codex@0.162.1`、`codex --version`，再以 `codex login` 完成官方登入。HL-06 執行委派另要求相符的原生執行檔雜湊、可用的 MXC 及 Plus，並預覽本機 Codex 自動載入的非敏感全域 `AGENTS.md`。它須是正常檔案、UTF-8 且不超過 8 KiB，既有全域覆寫檔會使本次診斷停在前置檢查。可在新電腦使用自己的非敏感協作規則。新安裝的登入、MXC 和真人委派能力要在該電腦上另行確認。

HL-09C 沿用 HL-09A 的兩份需求檔，鎖定 39 個指定套件，內含 `openai==3.49.0` 與 `pydantic-ai-slim==2.71.0`。完成任一恢復方式後，在 HL-09C 的 `candidate` 內執行 `Open-HL09C-Companion.cmd`，開啟 <http://127.0.0.1:47711/#chat>。啟動器使用該候選父目錄的 `.venv`，資料位於同層 `engineering-project`。新版桌面目錄須符合程式核對的官方套件路徑及雜湊，無法使用時會回退至已核對的舊版目錄或歷史實測。

HL-09A 的入口為 <http://127.0.0.1:47691/#chat>，由其各自 checkout 的 `Open-HL09A-Companion.cmd` 啟動。

HL-07 的入口為 <http://127.0.0.1:47671/#chat>，由其各自 checkout 的 `Open-HL07-Catalog-Companion.cmd` 啟動。

HL-05 的入口為 <http://127.0.0.1:47651/#chat>，資料位於該候選父目錄的 `real-project`。HL-06 的入口為 <http://127.0.0.1:47661/#chat>，資料位於其父目錄的 `engineering-project`。各版本首次啟動會建立新的工作區、SQLite 與知識種子，保存的文件位於各自的 `state/outputs`。私人對話、既有 SQLite、機器綁定憑證與活動批准保留在原工作區。

跨設備程式與核心環境恢復已完成。實體第二台 Windows 已確認聊天介面正常，並實際完成真人批准的原生唯讀診斷。工作收據可在原有帳戶與工作區內持久保存及重新查找。舊工作區的收據無直接匯入功能。

### 歷史發行說明

以下為先前 Windows MVP 與固定範例試點發行說明，適用於其各自的歷史分支與資料。

## NEXUS MVP 與固定工程範例試點（Windows，2026-11-05）

本分支保存已在本機驗證的 NEXUS MVP：一般聊天、原生 Codex 唯讀診斷、帶診斷來源的追問、UTF-8 TXT／Markdown 文件整理及 ZIP 副本輸出。來源分享與副本建立仍需要預覽及明確確認。Liquid Ceramic 對話空間保留閱讀寬度、字級、側欄及情境閱讀操作。

工程試點是另一條明確批准的固定非敏感範例路線，並非任意 Repository 寫入能力。舊 READ_ONLY 批准與 ReviewStore 審查決定不會變成寫入授權，模型完成也不是獨立技術 ACCEPTED。

### 在另一台 Windows 電腦準備

需要 Windows、Git、Python **3.10 或更新版本**、Node.js/npm、網際網路，以及操作者自己的 ChatGPT／Codex 使用資格。以下命令在 Windows PowerShell 執行：

```powershell
git clone --branch nexus-mvp-engineering-20261105 --single-branch https://github.com/HarryWhite-TW/local-ai-workbench.git
cd local-ai-workbench
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-companion.txt
npm install -g @openai/codex@0.162.1
codex --version
codex login
```

`codex --version` 必須顯示 `codex-cli 0.162.1`；不要改用更新的 alpha 版本。Codex 使用官方登入，NEXUS 一般聊天則透過介面中的帳戶登入開啟官方 SIWC 流程，由帳戶持有人本人驗證。兩者是不同登入；不要複製其他電腦的登入檔、資料庫或 DPAPI 密文，不需要新增 API Key。

一般使用雙擊 **Open-Companion.cmd**。啟動器預設使用本 Repository 的 `.venv` 及標準 npm Windows 原生 Codex 執行檔；非標準安裝可明確指定環境變數 `NEXUS_PYTHON`、`NEXUS_CODEX`（後者須為原生 `codex.exe`）。啟動器不會自動安裝依賴、更新 Codex 或分享來源。

預設頁面為 <http://127.0.0.1:56144/>。若該連接埠已使用，請先關閉前一個 NEXUS 主機，或設定 `NEXUS_PORT`／依 `python -m src.companion_core.daily --help` 使用另一個本機連接埠。主機是前景程序，關閉其命令視窗會停止服務；不是背景排程服務。

### 固定隔離工程範例

先關閉一般 NEXUS 主機，再雙擊 **Open-Engineering-Pilot.cmd**。首次會把 `examples/engineering-pilot/before/` 的三份非敏感檔案複製到 `%LOCALAPPDATA%\NEXUS\Daily\fixture`，不覆寫既有範例。此範例位於 Repository 和登入資料目錄之外。

先在 NEXUS 完成自己的 SIWC 登入並保存一段一般對話，再於該對話輸入：

> 修正 calculator.py 的 average([]) 除零問題，使空集合回傳 0，保留其他平均值行為與原有測試，實際執行 unittest。

選「預覽工程範例」，核對來源、目錄及修改／測試影響，勾選確認後按「批准修改隔離範例並執行測試」。這是本機工作提案，尚未執行的預覽不假裝模型回答。批准後才由官方 Codex App Server 修改範例，執行測試，將進度、實際差異及結果保存回同一對話。只預期修改 `calculator.py`；固定測試與規則若變更，成果不會被確認。額外權限要求一律拒絕。

每次工作會先實測範例內可寫、父目錄測試寫入遭拒，通過後才送模型。App Server 必須以範例本身為 cwd；前端不能指定其他寫入根。禁止直接指定原始 Repository 或私人資料目錄作為試點。`examples/engineering-pilot/after/` 是本機已完成的非敏感修正參考，不會被自動套用。

Windows `unelevated` 寫入探針只證明測試到的寫入邊界，**不代表完整的私人檔案讀取隔離或防火牆級網路隔離**。請只使用非敏感範例。官方說明：<https://learn.chatgpt.com/docs/windows/windows-sandbox>。主機中斷的工作標為 UNKNOWN，不會自動重跑；已完成工作重新整理只讀回結果。不要把工作摘要當成獨立技術驗收。

### 本機資料、驗證範圍與限制

- 新電腦自行建立 `%LOCALAPPDATA%\NEXUS\Daily\state`（Windows DPAPI 帳戶檔、聊天與工作結果）、`reviews`（唯讀審查紀錄）、`fixture`（僅試點）。兩個啟動入口共用這份狀態，一次只能開一個主機。
- 本分支只包含安全來源、測試與非敏感範例；不包含原電腦的私人歷史、帳戶、收據資料、Python 環境或 Codex 執行檔。原電腦的 A 保全不是可跨機複製的登入包。
- 既有本機證據包含真實 Codex 修改、3 項範例測試通過、原對話結果讀回及門禁/UI 檢查。發布時的可攜性檢查不等於第二台電腦已完成端到端驗證；新電腦的官方登入、沙盒能力、網路資格與完整操作仍待當地確認。
- 可讀驗證：`python -m unittest tests.companion_core.test_engineering_pilot -v`；`node --test tests/companion_core/test_native_work_ui.cjs tests/companion_core/test_organize_ui.cjs`。這些門禁/UI 測試不會呼叫真實模型。`examples/engineering-pilot/after` 的 `python -B -m unittest -v` 可確認修正參考；before 範例的空集合測試預期失敗。

以下保留原有 workbench 來源與歷史功能說明；本分支新增的 NEXUS 啟動與資料位置以上述章節為準。


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

The candidate published in [PR #362](https://github.com/HarryWhite-TW/local-ai-workbench/pull/362)
contains the retained NEXUS sources and Node 01 consolidation. The PR records
its merge state; real daily-use acceptance remains outstanding. The pre-publication source was HEAD
`6c1eac3e8be6f2b6efc5ba58e5289db5972a1f71` plus retained working-tree sources.
That pre-publication HEAD alone omits the daily/chat/resources/native-reader work. GitHub master was
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
Node 01 local consolidation is technically ACCEPTED. [PR #362](https://github.com/HarryWhite-TW/local-ai-workbench/pull/362)
publishes the candidate; its merge state is tracked by the PR. Node 02 requires
separate explicit authority. Historical roadmaps, examples and completion records do
not activate work. The [engineering index](docs/ENGINEERING_RECORDS_INDEX.md)
keeps source-level evidence and verification limits.
