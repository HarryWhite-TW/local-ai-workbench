# LC-Bridge-01 local test

在 Windows 雙擊 repository 根目錄的 `Open-LC-Bridge-01-Test.cmd`。
需要已安裝的 Python 3.10+ 與 Chrome；無需安裝前端依賴。
瀏覽器會開啟可信的 `http://127.0.0.1:<port>` Surface。

此入口使用真實 Surface、Core、ReviewStore，只有執行器是 synthetic。
沒有 OAuth、真實 AI、專案讀取或外部操作。請勿輸入私人資料。
工作約 18 秒後取得合成結果；Stop 約 3 秒後由執行器確認取消。
成果與審查保存於 `%LOCALAPPDATA%\LocalAIWorkbench\LCBridge01-Test\reviews`，
工作區為同目錄的 `synthetic-workspace`，與成果目錄分離。
重新啟動可讀取已保存成果；未保存的執行進度不會恢復。

新增工作 → 一瞥 → 展開 → 觀察 → 成果 → 接受／拒絕／調整 → 返回。
調整只保存 CREATED 子工作與關聯，不會執行另一項工作。
停止等待確認時不表示已取消；斷線時重要操作暫停。
數字鍵 1／2／3 切換檢視，Esc 收合，Tab 與 Enter 操作控制。
右上角可切換三種主題、Reduced Motion 與表面光線品質。
在啟動視窗按 Enter 可關閉測試服務。使用前可先開啟原本
`C:\Users\harry\Desktop\LC-Interaction-01\index.html` 比較設計原型。

正式 CodexRuntime 與既有認證入口未修改。本輪沒有驗證真實 AI 或
Windows 精確讀取範圍（M2-C5 尚未解決）。產品品質仍待人類審查。
