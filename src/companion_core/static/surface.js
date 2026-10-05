"use strict";
const $ = id => document.getElementById(id);
const labels = {CREATED: "正在準備", RUNNING: "正在執行", COMPLETED: "執行已完成",
  RESULT_PENDING_REVIEW: "結果等待審查", ACCEPTED: "結果已接受", REJECTED: "結果已拒絕",
  REVISION_REQUESTED: "已要求調整，新工作尚未執行", FAILED: "執行失敗", CANCELLED: "已確認取消"};
let selected = "", target = null, selectionVersion = 0, deciding = false, starting = false, connected = false;
function reviewButtons() {
  const ready = connected && !deciding && target && target.task_id === selected && target.state === "RESULT_PENDING_REVIEW";
  for (const id of ["accept", "reject", "revise"]) $(id).disabled = !ready;
}
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST", cache: "no-store",
    headers: body === undefined ? {} : {"Content-Type": "application/json", "X-Companion-UI": "1"},
    body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) throw new Error("操作未確認，請重新讀取工作；不會自動重試。");
  return response.json();
}
function disconnected() {
  connected = false;
  $("connection").textContent = "連線或記錄目前不可確認；不代表取消或接受。請重新讀取。";
  $("selected-status").textContent = "目前狀態未確認";
  $("start").disabled = true;
  reviewButtons();
}
function mode(companion) {
  document.body.classList.toggle("companion", companion);
  $("companion-mode").setAttribute("aria-pressed", String(companion));
  $("mixed-mode").setAttribute("aria-pressed", String(!companion));
}
function renderTarget(value) {
  target = value;
  $("review-panel").hidden = false;
  $("review-intent").textContent = value.intent;
  $("result").textContent = value.result;
  $("review-state").textContent = labels[value.state] || "狀態未確認";
  $("selected-status").textContent = `${value.intent} · ${labels[value.state] || "狀態未確認"}`;
  $("revision").textContent = value.revision ? `已建立另一個唯讀工作：${value.revision.intent}。尚未執行，舊結果與調整關聯已保存。` : "";
  reviewButtons();
}
async function openTarget() {
  const id = selected, version = ++selectionVersion;
  target = null; reviewButtons();
  $("review-panel").hidden = true;
  if (!id) return;
  try {
    const value = await api("/api/target", {task_id: id});
    if (version === selectionVersion && id === selected) renderTarget(value);
  } catch { if (version === selectionVersion) disconnected(); }
}
async function refresh() {
  try {
    const state = await api("/api/state");
    connected = true;
    $("connection").textContent = "已連接本機端 · 唯讀工作與審查各自保持明確界線";
    $("workspace").textContent = state.workspace;
    $("start").disabled = state.busy || starting;
    $("active").textContent = state.active ? `${state.active.intent} · ${labels[state.active.state] || "狀態未確認"}` : "尚未啟動工作；已保存的結果可由下方選擇。";
    $("progress").replaceChildren(...state.progress.map(text => { const li = document.createElement("li"); li.textContent = text; return li; }));
    $("notice").textContent = state.notice;
    $("tasks").replaceChildren(new Option("請選擇工作，不會自動批准最新結果", ""),
      ...state.tasks.map((t, i) => new Option(`${i + 1}. ${t.intent.slice(0, 75)} · ${labels[t.state] || "狀態未確認"}`, t.task_id)));
    $("tasks").value = selected;
    const saved = state.tasks.find(t => t.task_id === selected);
    $("open-review").disabled = !saved;
    if (saved) {
      $("selected-status").textContent = `${saved.intent} · ${labels[saved.state] || "狀態未確認"}`;
      if (target && target.state !== saved.state) { target = null; $("review-panel").hidden = true; }
    }
    reviewButtons();
  } catch { disconnected(); }
}
$("companion-mode").onclick = () => mode(true);
$("mixed-mode").onclick = () => mode(false);
$("tasks").onchange = () => {
  selected = $("tasks").value; target = null; ++selectionVersion;
  $("review-panel").hidden = true; $("decision-message").textContent = "";
  $("selected-status").textContent = selected ? "已選擇工作；開啟結果後才能審查。" : "尚未選擇工作";
  $("open-review").disabled = !selected; reviewButtons();
};
$("open-review").onclick = () => { mode(false); openTarget(); };
$("run-form").onsubmit = async event => {
  event.preventDefault();
  if (starting || $("start").disabled) return;
  starting = true; $("start").disabled = true;
  try {
    const created = await api("/api/start", {intent: $("intent").value});
    selected = created.task_id; target = null; ++selectionVersion; $("review-panel").hidden = true;
    $("decision-message").textContent = "";
  } catch { disconnected(); }
  finally { starting = false; await refresh(); }
};
async function decide(action) {
  if (deciding || !connected || !target || target.task_id !== selected || target.state !== "RESULT_PENDING_REVIEW") return;
  const exact = target;
  const intent = action === "revise" ? $("revision-intent").value.trim() : null;
  if (action === "revise" && !intent) { $("decision-message").textContent = "請先明確輸入調整內容。"; return; }
  deciding = true; reviewButtons();
  try {
    const value = await api("/api/review", {task_id: exact.task_id, result_id: exact.result_id, action, revision_intent: intent});
    if (selected === exact.task_id) {
      renderTarget(value); $("decision-message").textContent = "明確決定已保存；沒有授予 Git 或外部操作權限。";
    }
  } catch {
    target = null; $("decision-message").textContent = "決定未確認成功，請重新開啟指定結果讀回；不會自動重試。";
  } finally { deciding = false; await refresh(); }
}
$("accept").onclick = () => decide("accept");
$("reject").onclick = () => decide("reject");
$("revise").onclick = () => decide("revise");
async function poll() { await refresh(); setTimeout(poll, 1000); }
poll();
