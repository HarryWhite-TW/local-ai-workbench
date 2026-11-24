# NEXUS 模型能力資料

2026-11-24 HL-04 工程觀察。這是一份已核准來源的摘要。

1. HL-04 的 `codex_catalog.py` 以既有 ChatGPT 訂閱啟動正式 Codex App Server，先以 `account/read` 檢查訂閱認證類型，再用 `model/list`（`includeHidden=false`）取得 picker 項目。請核對目前執行器與帳戶後再視作當前目錄。
2. `official-models.json` 是當時 App Server 的目錄快照。舊 picker 未列出後來在 Codex 訂閱 Responses 通道成功的 GPT-6.2 Sol。目錄顯示、帳戶資格、指定通道與某個設定真正成功，須分別保存。
3. `model-preflight.json` 記錄 Sol Low 與 Medium 的 HTTP 200 和回傳模型比對。HL-04 的完整旅程也確認 Terra Medium，並在同一聊天跨模型使用。試用能力限實測組合。今日是否可用、還有哪些模型、額度及帳戶資格須另行查證。
4. App Server 官方 RPC 文件列出 `model/list` 及分頁。此診斷只能閱讀現存證據及程式，沒有授權新增模型推論或探測外部端點。
