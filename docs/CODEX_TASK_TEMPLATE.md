# CODEX Task Template

每次要交給 Codex 的任務，請盡量填完這份模板。空白可保留，但 `允許修改`、`禁止修改`、`完成標準` 最好明確。

## 任務類型
- 文件小修 / 規則整理 / Bug fix / 測試同步 / CLI 同步 / Docker 同步 / 重構 plan / 其他：

## 本次目標
- 

## 背景脈絡
- 

## 允許修改
- 

## 禁止修改
- 

## 驗收命令
```bash
# 若 repo 有 pytest 測試：
pytest -q

# 若 repo 有文件化 CLI：
<documented-cli-command>

# 若 repo 有 Docker 驗收流程：
docker build .
docker run --rm <image>
```

## 完成標準
- 

## 若卡住 20 分鐘，縮小到
- 

## 最後回報格式
1. Summary
2. Modified files
3. Commands run
4. Test results
5. Risks / assumptions
6. Suggested next step

## 需要我拍板的點
- 若沒有，請寫 `None`。
- 若有，請列成可決策清單，不要模糊帶過。
