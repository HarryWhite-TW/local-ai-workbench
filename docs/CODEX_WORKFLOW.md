# CODEX Workflow

## 使用情境
- Local 適合低風險、明確、可快速檢查的小修改。
- Branch 適合會留下正式 diff 的任務，例如 docs、tests、README 同步、小型 bug fix。
- Worktree 適合不確定是否採用、可能影響多檔案、需要隔離實驗、或想避免污染目前 working tree 的任務。
- 高風險架構、新功能、大型重構只能先做 plan，不得直接修改。
- 同一個 Local repo 不要同時讓多個 Codex thread 寫檔；若要並行，使用 Worktree。

## 主線保護
- `master` 必須保持可跑、可展示。
- 不要讓展示主線混入未驗收的實驗改動。

## 任務完成規則
- Codex 完成任務後不要自動 commit，除非我明確要求。
- 最終 merge、commit、push 由我決定。
- 任務完成後固定回報 `Summary`、`Modified files`、`Commands run`、`Test results`、`Risks / assumptions`、`Suggested next step`。
