# HL-09D-R · Upstream Workspace Composition

2026-11-26 台灣時間。Windows Visual Lab，Node 24.19.0、npm 11.17.0。

## 入口

- [Visual Lab 總入口](http://127.0.0.1:47809/) 保留既有 Paper Shader 與 Three.js 展示。
- [上游離線基準](http://127.0.0.1:47809/workspace/) 和 [複合工作台](http://127.0.0.1:47809/workspace/?mode=composite) 使用相同的離線對話。點 Open workbench 可查看右側成果。複合工作台的正確參數是 `mode=composite`。
- 在 Visual Lab 根目錄執行 Start-Visual-Lab.cmd 可啟動同一入口。既有服務正在執行時直接開網址。

## 來源與調整

- [assistant-ui Artifacts](https://github.com/assistant-ui/assistant-ui/tree/fa77fb8fad216588b57be4cfe69be3fe7f0e470e/examples/with-artifacts) 為主要上游，MIT。官方 Thread、ApprovalCard 和所有被編譯的共用元件源檔位於 packages/ui。右側 ArtifactSurface、雙欄條件布局和 UI 樣式源自官方範例。React 19.3.1、assistant-ui/react 0.15.38、react-markdown 0.14.26、Base UI 1.9.0、Tailwind 4.3.5 等依賴詳見 package-lock.json 及 evidence/dependencies.tsv。僅在隔離實驗安裝，安裝使用 ignore-scripts。
- 基準是官方介面的離線適配，使用原始 Thread 和原始樣式。用 LocalRuntime 固定回覆取代 Next.js、API、模型和帳戶，並用頂端按鈕開啟同一份固定報告。官方原始範例另存於 upstream 供比較。
- 兩版的成果框均為空 sandbox。上游原有 allow-scripts、allow-forms 已移除。Source 欄位唯讀，靜態報告無版本歷史，因此上游版本欄顯示 0。工作台路由 CSP connect-src none。工程卡只產生本機記憶體狀態，沒有永久允許選項。
- 複合版新增工作側欄、工單進度、離線模型／強度選單，以及可關閉的局部材料識別。保留官方 ApprovalCard 的按鈕及收據狀態。模型／強度選單僅展示狀態。所有工程、對話和成果使用合成資料。
- [Paper Shaders](https://github.com/paper-design/shaders) 既有 0.0.82，Apache-2.0。使用官方 ShaderMount 與 Liquid Metal fragment shader，透過內建菱形參數省去外部圖片。配色沿用上游中性色系。隨附 Paper LICENSE 和 NOTICE。先前其他實驗圖像仍有個別再散布限制，這次複合畫面未使用這些圖像。
- [Lobe UI](https://ui.lobehub.com/sections/chat) 是 MIT 元件庫，具備 ChatList 和 ChatInputArea。assistant-ui 已帶完整的 Chat＋Artifact 佈局和同系列批准卡，故選用這一路。

## Windows 實際觀測

- 兩版使用 1440 × 1000 viewport、相同合成對話和固定成果實拍。複合版實際通過側欄開關、拒絕、一次批准、收據重設、輸入送出、模型／推理強度選擇、預覽與唯讀原始碼的切換，以及關閉後重新開啟。
- Liquid Metal 以速度 0 渲染標記，不啟動連續動畫。可見時一張 46 × 42 繪圖緩衝，合計 1932 像素。兩次實測初始化耗時已記錄在瀏覽器觀測，該值含 WebGL 建置呼叫時間，並非 GPU frame time。關閉 Material 後 DOM 畫布數量為 0，重新開啟回到 1。對照 core 的 dispose 呼叫會刪除 GPU program，並在支援時要求釋放 WebGL context。
- 已接上可見性與離開畫面的資源清理。未取得真實背景分頁觸發的證據，亦未量測可歸因到標記的 GPU／CPU 占用。
- 接受基準 HEAD 2b806a97694e02a88c2063db70ab3d0ee27427ab。原實驗清單的 43 個 SHA-256 均通過，兩個更新的導航／服務檔案以 index.previous.html 和 server.previous.mjs 保留原字節。未使用外部帳戶、模型或付費服務。NT$0。

## 正式整合取捨

可優先保留 Approval Card 的範圍、單次決策和收據呈現方式，也可保留標記的局部靜態 shader。直接搬入整套 assistant-ui 意味引入 React、編譯和樣式工具鏈，還需銜接既有訊息事件、來源分享和一次性批准。應先決定元件重用範圍，再核對鎖定依賴的授權聲明與打包成本。成果 iframe 的固定報告證明顯示佈局，無法作為 NEXUS 原型執行或版本保存的證據。視覺品質交由使用者檢視。

