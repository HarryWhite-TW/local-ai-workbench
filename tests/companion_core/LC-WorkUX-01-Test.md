# LC-WorkUX-01 local test

雙擊 repository 根目錄 Open-LC-WorkUX-01-Test.cmd；需要 Python 3.10+ 與 Chrome，
不需安裝前端依賴。開啟的是真實 localhost Surface／Core／ReviewStore；
只有執行器為 synthetic，沒有 OAuth、真實 AI 或私人專案讀取。

建立非敏感工作，約 18 秒後取得合成結果；Stop 約 3 秒後確認取消。
成果與審查保存在 %LOCALAPPDATA%\LocalAIWorkbench\LCWorkUX01-Test\reviews。
重啟可讀保存的成果，不恢復未保存執行或事件。啟動視窗按 Enter 關閉服務。

可以親自比較以下操作：

- 觀察 → 摘要／詳細事件：區分階段回報、Core 確認與未提供的工具細節。
- 成果 → 展開閱讀：閱讀器綁定原 Task／Result，即使背景選取其他工作也不更換。
- 拖動閱讀器標題、拖動右下角、或對應控制取得焦點後按方向鍵調整，Shift 加速。
- 專注閱讀／恢復視窗；Esc 或關閉按鈕返回原介面。
- 返回工作與審查：選取原成果所屬工作，重新讀回後由人類作出審查決定。
- 三種材質、Reduced Motion、窄視窗與 Chrome 縮放均可使用。

成果以純文字安全呈現。閱讀器不接受結果、不停止工作、不自動執行 Revision。
目前沒有工具命令、工具輸出、逐項操作完成回執或模型私人推理。
Windows 精確讀取範圍 M2-C5 尚未解決，真實 AI／OAuth 不在本輪驗證範圍。
