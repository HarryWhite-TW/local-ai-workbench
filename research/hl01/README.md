# HL-01 自然工作接續實驗

在本機 Windows 的 PowerShell 開啟本資料夾，直接執行下列兩行中的一行。兩個入口共用三筆可見的合成工程資料。輸入自己的自然問句即可開始。

```powershell
.\.venv\Scripts\python.exe -X utf8 lab.py A --chat daily
.\.venv\Scripts\python.exe -X utf8 lab.py B --chat daily
```

例如可以先問「我們以前做過哪些工作？」，再問「第二筆呢？」。輸入 `/exit` 關閉。重開同一行指令會讀回該版本、該名稱的對話。換一個 `--chat` 名稱即可從空白開始。兩個版本的同名對話各自獨立。這是單一本機示範身分，請只使用合成資料。模型會收到當次問題、可見歷史，以及本輪查到的授權資料。

想查詳細收據時，以自然語言說明想知道的內容。主機顯示工作及收據編號時，輸入大寫 `YES` 可允許模型在本輪讀取一次。Enter、其他文字或無互動輸入均拒絕。下個回合要使用同一份詳文，仍需重新批准。已分享的詳文與回答留在本機稽核存檔；後續模型只會看到分享事件的摘要。

## 實作與恢復

- `subscription.py` 建立 Pydantic 的 Codex 訂閱 provider，請求模型為 `gpt-6.1-terra`、effort 為 `medium`。專用 HTTP client 僅放行訂閱推論端點，關閉 SDK 重試與外部內容追蹤。現有登入無法送出請求時，當輪停止。
- `work_index.py` 將資料限制在主機綁定的帳戶與工作區。每個摘要的 SHA-256 對應排序鍵、UTF-8、保留非 ASCII 文字的整列 JSON，編碼規則見 `metadata()`。受限資料另有不同帳戶與工作區各一筆，供隔離驗證。
- `lab.py` 的 A 使用 Core 的 `Conversation` 與官方序列化器，Windows 檔案鎖防止同對話並行覆寫，以原子替換保存狀態。B 共用此機制，並以 `StepPersistence` 寫入該對話專用的 SQLite，以 `ConversationSearch(scope="conversation")` 搜尋已完成、可再次使用的公開回合。實驗短對話保留完整公開歷史。
- `state/demo/studio/<版本>/<對話 UUID>/` 內的 `conversation.json` 是下輪起點，`<run UUID>.jsonl` 是本機收據，`latest` 指向最近執行。B 另存 `steps.sqlite`。狀態依賴本機 Windows 使用者的檔案權限，適用單人操作。
- 程序中斷後，可執行下列指令檢查上一輪。如果 B 已留下完整公開答覆、相符的步驟快照與收據，而且沒有結果未知的工具操作，主機可直接恢復。較早的中斷、含已分享詳文的未提交回合或缺少必要紀錄時，保留上一次已保存的對話。A 可接續已提交的回合。

```powershell
.\.venv\Scripts\python.exe -X utf8 lab.py B --chat daily --recover
```

## 本機驗證

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest -v
.\.venv\Scripts\python.exe -m pip check
```

`smoke.py` 是最小的真模型查找驗證。`compare.py` 會以新批次重跑成對自然語句、程序重啟與可控中斷，並使用 Codex 訂閱額度；一般體驗只需執行 `lab.py`。每一題由新的 Windows 程序執行，模型自行選工具。比較中的詳文授權以關閉標準輸入觸發拒絕；真人可在 CLI 主機提示中自行作決定。受控中斷位於完整模型回覆後、正式對話寫入前。所有自然問句以及執行順序可在 `compare.py` 檢查。

在另一個已具備 Python 3.11+ 與相容 Windows wheels 的環境重建時，使用專案內虛擬環境及官方 PyPI，直接依賴固定在 `requirements.txt`。本次驗證使用 Python 3.14.6。首次模型執行需要已可用的 Codex CLI ChatGPT 登入。可將 `PYDANTIC_AI_NO_BANNER` 設為 `1` 隱藏套件提示。
