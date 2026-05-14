# No-Agent Local Commit Rail SOP

## 文件目的

本文件是 no-agent local commit rail 的完成版 SOP，用來保存目前已驗證成功的流程、操作方式、失敗處理、安全邊界與下一階段限制。

本 SOP 的背景完成節點是 Issue #72：

- 成功流程：ReviewBundle -> DryRun -> CommitOnce -> auto local commit -> push completed
- Commit：`a4680667570261fdd2ad66ebd2e3dcc5d688ee06`
- Committed file：`docs/RUNNER_V2.md` only
- Issue #72 已完成並關閉

本文件只記錄已完成的 no-agent local commit rail。它不宣稱 push / close issue automation 已完成，也不把下一階段規劃寫成既有能力。

## 目前已完成能力

目前 runner rail 已能做到：

- 自動從 GitHub issue 找到有效的 `run-reviewbundle` approval。
- 自動產生 ReviewBundle（審核包）。
- 驗證 commit approval 的 `branch` / `HEAD` / `review` / `diff` / `files` / `expiry`。
- 執行 `ApprovalNextCommitDryRun`。
- 執行 `ApprovalNextCommitOnce`。
- 委派 runner v1 建立 local commit。
- 讓使用者不需要手動執行 `git add` / `git commit`。
- 保持 local commit rail 的安全邊界：no push / no close / no merge / no PR。

## 完整流程

文字流程如下：

```text
GitHub Issue approval
-> runner v2 掃描任務
-> runner v2 委派 runner v1 / Codex 產生 ReviewBundle
-> ChatGPT 審核 review / diff / files fingerprint
-> ChatGPT 貼 structured commit approval marker
-> runner v2 ApprovalNextCommitDryRun 驗證
-> runner v2 ApprovalNextCommitOnce 委派 runner v1
-> runner v1 建立 local commit
-> 使用者不需要手動 git add / git commit
```

重要觀念：

- ReviewBundle 階段負責產生可審核的 diff 與 fingerprint。
- Commit approval marker 必須綁定目前狀態，不能跨 branch、跨 HEAD、跨 diff 或跨 files 狀態重用。
- CommitOnce 只建立 local commit，不代表 push、close issue、label、PR 或 merge 已完成。

## 模式中文解釋

- ReviewBundle：審核包。runner / Codex 產生可供人類與 ChatGPT 審查的變更摘要、diff 狀態、fingerprint 與 final status。
- DryRun：試跑 / 不寫入驗證。只檢查目前狀態、approval marker 與安全條件，不 stage、不 commit、不 push。
- CommitOnce：只執行一次提交。驗證通過後只建立一個 local commit，不進入連續處理或背景模式。
- approval marker：批准標記。GitHub issue comment 內的 structured ASCII marker，用來表示某個狀態被批准進入下一步。
- fingerprint：指紋 / 雜湊驗證值。用 SHA-256 類型的值確認 diff、files 等狀態沒有被替換或漂移。
- dirty state：有未提交變更的狀態。`git status --short` 顯示有 modified / untracked / staged 等變更時，即為 dirty。
- scanner：掃描器。runner v2 用來掃描 bounded open issues、讀取 approval marker、找出符合條件任務的部分。
- rail：受控軌道 / 安全流程。每一步都有明確輸入、驗證、停止條件與禁止事項的 automation path。

## 正常操作流程

使用者負責：

- 在 repo root 執行被批准的 runner 指令。
- 不手動 stage / commit / push，除非另有明確批准。
- 檢查 runner 輸出與 final git status。
- 在需要進入下一階段前，要求 ChatGPT 審核目前狀態。

ChatGPT 負責：

- 審核 ReviewBundle 內容、diff、modified files、fingerprint 與安全邊界。
- 判斷是否可以貼出 structured commit approval marker。
- 確認 approval marker 綁定正確 issue、repo、branch、HEAD、review、diff、files、expiry。
- 在每個 issue 完成後，回報進度、完成度與下一個 issue 的目的。

Codex / runner 負責：

- runner v2 掃描 bounded open issues。
- runner v2 驗證 approval marker 是否 current 且符合本地狀態。
- runner v2 在 DryRun 中只回報計畫，不寫入。
- runner v2 在 CommitOnce 中委派 runner v1。
- runner v1 在 approval 通過後只 stage approved files 並建立 exactly one local commit。
- runner v1 回報 commit SHA、final git status 與下一步。

## 失敗處理流程

### Expired marker

如果 approval marker 已過期，runner 必須視為非 current approval。

處理方式：

- 不執行 CommitOnce。
- 重新審核目前 ReviewBundle / diff / files fingerprint。
- 由 ChatGPT 在確認仍有效後貼新的 marker。

### Dirty repo

如果 repo 是 dirty state，runner 必須停止。

處理方式：

- 不 stage。
- 不 commit。
- 不自動 reset。
- 回報 `git status --short`。
- 由使用者與 ChatGPT 判斷 dirty state 是否就是預期 ReviewBundle 變更，或是否混入非預期變更。

### Unreadable issue

如果某個 issue comment / JSON 無法讀取，scanner 應依既有 bounded scan 行為處理：

- top-level GitHub issue list/search failure 是硬失敗。
- 單一 issue read failure 可以被 skip 並回報。
- 不應因已知單一舊 issue 讀取失敗而讓整條 rail 無法使用。

### Fingerprint mismatch

如果 diff fingerprint 或 files fingerprint 不一致，代表目前狀態不是被審核批准的狀態。

處理方式：

- 不執行 CommitOnce。
- 不嘗試修補 marker。
- 重新產生 ReviewBundle 或重新審核目前 diff。
- 貼出新的 approval marker 前，必須確認 branch、HEAD、review、diff、files 全部一致。

### Unrelated old marker

如果 scanner 找到 unrelated old marker，例如舊 issue、舊 HEAD、舊 review id 或過期 marker：

- 不應把它當作有效 approval。
- 不應用舊 marker 執行 commit。
- 若它只是 stale / expired / mismatch，通常可視為 skipped marker。
- 若它是 current 但 action unsupported，watch / execution rail 應停止，不應忽略後繼續執行其他 approval。

### ReviewBundle / DryRun / CommitOnce 不一致

如果 ReviewBundle、DryRun、CommitOnce 三者看到的狀態不一致：

- 停止 CommitOnce。
- 不 stage。
- 不 commit。
- 回報不一致項目，例如 branch、HEAD、review id、diff fingerprint、files fingerprint、modified file list。
- 重新從 ReviewBundle 或 DryRun 開始，直到狀態機回到一致狀態。

## 狀態機觀念

這條流程不是單點命令，而是狀態機：

```text
Clean repo
-> ReviewBundle dirty state
-> approval marker state
-> DryRun validated state
-> CommitOnce executable state
-> committed clean state
```

各狀態含義：

- Clean repo：開始前 repo 乾淨，沒有未提交變更。
- ReviewBundle dirty state：runner / Codex 產生 reviewable local diff，repo 變 dirty。
- approval marker state：ChatGPT 審核 diff / files / fingerprint 後，在 GitHub issue 貼 structured marker。
- DryRun validated state：`ApprovalNextCommitDryRun` 驗證 marker 與本地狀態一致，但不寫入。
- CommitOnce executable state：相同狀態可交給 `ApprovalNextCommitOnce` 執行一次 local commit。
- committed clean state：runner v1 建立 local commit 後，repo 回到 clean 或只剩已明確回報的狀態。

狀態漂移時，例如 branch 改變、HEAD 改變、diff 改變、files 改變、marker 過期，必須停止並重新審核。

## 明確禁止自動化事項

目前仍禁止：

- 自動 push。
- 自動 close issue。
- 自動 label。
- 自動 PR / merge。
- 背景 daemon / scheduler。
- 一次連鎖多個 approval。
- 自動修改 approval marker 格式。
- 自動修改 scanner 邏輯。
- 使用 local commit rail 提交未在 ReviewBundle / approval marker 中明確批准的檔案。
- 若本次變更包含 docs 以外檔案，必須由該 issue 明確列入 ReviewBundle / approval marker，並經過更嚴格審核；#72 的 docs-only 是驗證情境，不是 local commit rail 的永久能力限制。

## 下一階段邊界

Push / close issue automation 是下一階段新里程碑，不屬於 local commit rail 收尾。

候選 issue：

- #74 Design push approval rail boundary
- #75 Implement / validate PushOnce DryRun
- #76 Implement / validate PushOnce
- #77 Design close issue approval rail
- #78 Implement / validate CloseIssueOnce

下一階段必須重新設計 approval boundary，不能把 local commit approval 直接延伸成 push 或 close approval。

## 每個 issue 完成後的進度匯報格式

每個 issue 完成後，使用以下固定格式回報：

```text
進度匯報
- 本 issue 完成了什麼
- 對無 Agent 自動化目標的影響
- 目前完成度估算
- 剩餘 issue 粗估
- 是否偏離主線
- 下一個 issue 的目的
```

填寫原則：

- 本 issue 完成了什麼：描述實際完成的驗證、文件或 automation rail 能力。
- 對無 Agent 自動化目標的影響：說明是否降低人工 relay、是否新增安全邊界、是否只是文件收斂。
- 目前完成度估算：用保守估計，不把未完成 push / close automation 算入已完成。
- 剩餘 issue 粗估：列出剩餘主要里程碑，不需要過度精準。
- 是否偏離主線：明確回答是 / 否；若有偏離，要說明原因。
- 下一個 issue 的目的：用一句話說明下一個 issue 要解決的邊界或驗證。

## 快速恢復上下文

未來 ChatGPT / Codex / 使用者接手時，先確認：

- 目前 repo 是否 clean。
- local commit rail 的基準驗證節點是否仍可追溯到 Issue #72 / commit `a4680667570261fdd2ad66ebd2e3dcc5d688ee06`。
- 若後續已有新的 SOP / runner validation issue，應同時確認最新完成節點與 #72 baseline 的關係。
- 目前 issue 是否只要求 docs / SOP 收斂，還是要求新增 runner 行為。
- 是否有人明確批准 stage / commit / push。
- 是否正在進入新的 push / close issue rail；如果是，必須開新 boundary，不可沿用 local commit approval。
