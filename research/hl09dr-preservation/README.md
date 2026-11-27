# HL-09D-R Upstream Visual Lab

雙擊 Start-Visual-Lab.cmd 後開啟 [本機展示](http://127.0.0.1:47809/)。本機只接受 127.0.0.1:47809，關閉啟動視窗即可停止自行啟動的服務。現有 Node v24.19.0、npm 11.17.0 可用。兩個直接依賴已安裝。要從鎖檔重新安裝，只在本目錄執行：

```powershell
npm ci --ignore-scripts --no-audit --no-fund --cache .npm-cache --registry=https://registry.npmjs.org
```

## 來源與授權

| 項目 | 固定版本、來源與本機行為 |
| --- | --- |
| Liquid Metal 與 Fluted Glass | [Paper 官方原始碼](https://github.com/paper-design/shaders) 的 npm `@paper-design/shaders@0.0.82`，Apache-2.0，無套件依賴。依同版 `shaders-react` 包對照參數映射，瀏覽器直接載入 core ESM 的 ShaderMount、fragment shaders 與 Liquid Metal 遮罩處理。React 封包只供唯讀檢查。保留包內 LICENSE、NOTICE 與 upstream/Paper-LICENSE、upstream/Paper-NOTICE。 |
| Three.js Clearcoat | [Three.js r187 Clearcoat](https://github.com/mrdoob/three.js/blob/r187/examples/webgl_materials_physical_clearcoat.html)，`three@0.187.0`，MIT，無套件依賴。保留官方 HTML、CSS、HDR 與貼圖。本機只改 import 路徑、加上播放暫停、可見性與診斷計數。物理場景、渲染、相機與 OrbitControls 使用原始程式。Stats 由該版 Three.js 隨附，保留原模組。 |
| assistant-ui | [官方批准卡](https://www.assistant-ui.com/elements/approval-card)、[官方成果展示](https://www.assistant-ui.com/examples/artifacts) 為唯讀參考。[上游程式碼為 MIT](https://github.com/assistant-ui/assistant-ui/blob/main/LICENSE)。未安裝該套件或執行本機 React 版本。獨立卡片可離開 assistant runtime，但仍需 React、圖示、共用樣式元件及樣式建置。 |

兩個套件均從 npm 官方登錄下載，package-lock.json 記錄 tarball URL 和 SHA-512 SRI。首次安裝停用生命週期腳本，使用 npm 原有快取。SVG 與花朵素材來自 Paper 展示頁列出的官方 URL；Clearcoat 貼圖取自 r187 的 examples/textures。本目錄是本機觀測用途。外部示範素材的個別再散布條款尚未逐項確認，整合或公開發布前應換用自有素材或完成素材授權核對。

## 實測範圍與差異

- **Liquid Metal** 使用 [官方預設](https://shaders.paper.design/liquid-metal) 與同一菱形遮罩。灰底、金屬帶、邊緣彩色偏移及流動都可辨認。官方頁與本機截圖的顯示尺寸和動畫相位不同；未做逐像素比對。
- **Fluted Glass** 使用 [官方預設](https://shaders.paper.design/fluted-glass) 的同一花朵圖、prism、lines、distortion 0.5。可辨認相同的垂直折射方向與花朵分布。用滑桿調至 1 後畫面變形增加，重設回 0.5。官方頁與本機顯示尺寸不同。
- **Clearcoat** 與 [官方展示](https://threejs.org/examples/webgl_materials_physical_clearcoat.html) 都以 1280 × 720 場景核對。四顆材質球、HDR 場景及反射相符，旋轉、點光時相和程序生成的 flakes 各自獨立，未做逐像素比對。[Iridescence](https://threejs.org/examples/webgl_loader_gltf_iridescence.html) 為官方參考，沒有另行加入本機。
- **Paper 並排** 是有限組合，兩張獨立 WebGL 畫布同時顯示。批准卡僅保留官方展示截圖，未組進渲染頁。
- **行為** 使用 1440 × 1050 本機桌面 viewport。Liquid Metal 暫停時鐘維持 13477 ms，繼續後前進；Clearcoat 暫停時到 500 幀後增量為 0，繼續後再增。Fluted Glass 預設靜態。Node 服務程序實際重啟，HTTP 200，三項 canvas 可讀回。IAB 隱藏面板和 Chrome 管理分頁未觀測到可信的 document.hidden，故背景止動未獨立通過。Chrome 該次觀測到頁面 RAF 一度 1 次/秒。Paper core 具原生 Page Visibility／IntersectionObserver，Clearcoat 實驗頁具 visibilitychange 停止邏輯。
- **資源** RTX 3060、WebGL 2.0、ANGLE/D3D11。Clearcoat 活躍樣本約 165 渲染幀/秒。Paper 的頁面 RAF 不是 shader 幀率。另保存 5 個約一秒間距的 Windows 顯卡樣本，以及 Chrome、Edge、Codex 可讀程序的 CPU 時間差。這些是全系統 GPU／可讀程序合計，非分頁專屬。GPU 使用率無畫布 90–99%、Metal 99–100%、Clearcoat 91–100%，基線已高，不能從差值推出任一效果的成本。三段 CPU 分別為單一邏輯核心等價 3.2%、2.0%、13.5%，屬短窗口觀測。未量測省電環境或低階 GPU。
- **隔離** 靜態 server 限定 loopback、GET 與公開素材路徑類別。常態渲染資源皆由本機供應。外部連結僅用於明確打開官方對照。實驗只使用公開展示素材，未連 NEXUS、模型或登入。費用 NT$0。

## 整合取捨

Paper 可以直接進入受信任的原生 JS 前端，採本地 ESM、少量 ShaderMount 配置及顯式 dispose。Fluted Glass 適合靜態素材預覽。Liquid Metal 適合尺寸有界、選擇性顯示的識別或交互用途，先衡量像素上限、低階 GPU、減少動態偏好以及無 WebGL 回退。Three.js 可保留於專門的 3D 檢視，對一般聊天背景會引入場景、相機、貼圖管理及長期 GPU 生命週期成本，暫不採用作常駐裝飾。assistant-ui 批准卡可提供狀態呈現與資訊階層參考，整套移植需要 React／樣式工具鏈及既有批准狀態映射。現有 NEXUS 授權與原型 CSP 可維持原狀，可信前端載入元件的決策應另作評估。
