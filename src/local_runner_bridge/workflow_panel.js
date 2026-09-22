"use strict";

const CURSOR_KEY = "lawb.workflow_panel.cursor.v1";
const EVENTS_KEY = "lawb.workflow_panel.events.v1";
const MAX_RENDERED_EVENTS = 80;
const SNAPSHOT_POLL_MS = 2000;

const LIFECYCLE_LABELS = Object.freeze({
  IDLE: "未偵測到請求",
  CHECKING_FOR_WORK: "正在檢查工作",
  NO_REQUEST_DETECTED: "未偵測到請求",
  REQUEST_DETECTED: "已偵測請求／等待接手",
  DISPATCHING: "正在派送",
  RUNNING: "執行中",
  BLOCKED_OR_FAILED: "已阻擋／失敗",
  WAITING_FOR_CHATGPT_REVIEW: "等待 ChatGPT 審查",
  FINAL_ACCEPTED: "ChatGPT 最終審查已接受",
  REPAIR_REQUIRED: "ChatGPT 最終審查要求修復",
  FINAL_REVIEW_BLOCKED: "ChatGPT 最終審查未接受／已阻擋",
  COMPLETED_OR_LAST_COMPLETED: "已完成／最近完成",
  EXPIRED: "已過期",
  UNKNOWN: "狀態不明",
});

const READINESS_LABELS = Object.freeze({
  ready: "本機 Workflow 已就緒",
  degraded: "本機 Workflow 狀態降級",
  unavailable: "本機 Workflow 不可用",
});

const EXTERNAL_EXECUTION_LABELS = Object.freeze({
  unknown_until_execution: "外部模型執行可用性需在實際執行時確認",
});

const HEALTH_LABELS = Object.freeze({
  online: "Operator 連線正常",
  offline: "Operator 離線",
  stale: "Operator 心跳逾時",
  unknown: "Operator 狀態不明",
});

const SCAN_LABELS = Object.freeze({
  eligible_request_detected: "已偵測請求",
  expired_request_observed: "觀察到已過期請求",
  no_eligible_request: "未找到可接手的請求",
  scan_blocked: "Inbox 檢查遭阻擋",
});

const PICKUP_LABELS = Object.freeze({
  ready_for_pickup: "可接手",
  not_eligible: "沒有可接手的請求",
  expired: "已過期，未接手",
  blocked: "接手前已阻擋",
  picked_up: "已接手",
  completed: "已完成",
});

const EVENT_LABELS = Object.freeze({
  "execution.started": "執行已開始",
  "codex.thread.started": "Codex 工作階段已開始",
  "codex.turn.started": "Codex 回合已開始",
  "codex.turn.completed": "Codex 回合已完成（僅代表活動）",
  "codex.turn.failed": "Codex 回合失敗（僅代表活動）",
  "codex.error": "Codex 回報錯誤",
  "codex.command.started": "命令已開始",
  "codex.command.completed": "命令已完成",
  "codex.command.failed": "命令失敗",
  "codex.file.started": "檔案活動已開始",
  "codex.file.completed": "檔案活動已完成",
  "codex.file.failed": "檔案活動失敗",
  "codex.message.completed": "已觀察到 Codex 訊息",
  "codex.todo.started": "任務清單活動已開始",
  "codex.todo.completed": "任務清單活動已完成",
  "process.completed": "Codex 行程已結束（僅代表活動）",
  "observability.source_warning": "可觀測性警告",
});

const WARNING_LABELS = Object.freeze({
  malformed_utf8: "來源事件不是有效的 UTF-8",
  source_line_too_large: "來源事件超過大小限制",
  malformed_json: "來源事件不是有效的 JSON",
  source_event_not_object: "結構化來源事件不是物件",
  source_event_type_missing: "結構化來源事件缺少 type",
  unknown_source_event_type: "未知的結構化來源事件類型",
  item_missing: "結構化事件缺少 item",
  item_type_missing: "結構化事件 item 缺少 type",
  sensitive_item_omitted: "已省略敏感的結構化 item",
  unknown_item_type: "未知的結構化 item 類型",
  ingest_frame_malformed: "觀測 ingest frame 格式錯誤",
  runner_control_malformed: "Runner 觀測 control frame 格式錯誤",
  ingest_frame_unknown: "未知的觀測 ingest frame 類型",
  task_packet_id_request_id_mismatch: "Task Packet 與 request identity 不一致",
});

function validEvent(event) {
  return Boolean(
    event
      && typeof event === "object"
      && Number.isSafeInteger(event.sequence)
      && event.sequence > 0
      && typeof event.kind === "string"
      && event.kind.length > 0
      && typeof event.observed_at_utc === "string"
      && event.payload
      && typeof event.payload === "object"
      && !Array.isArray(event.payload),
  );
}

function mergeEventCache(events, event, lastSequence, maximum = MAX_RENDERED_EVENTS) {
  if (!validEvent(event) || event.sequence <= lastSequence) {
    return { accepted: false, events, lastSequence };
  }
  const merged = events
    .filter((item) => validEvent(item) && item.sequence < event.sequence)
    .concat([event])
    .sort((left, right) => left.sequence - right.sequence)
    .slice(-maximum);
  return { accepted: true, events: merged, lastSequence: event.sequence };
}

function streamUrlWithCursor(streamUrl, lastSequence, baseUrl = "http://127.0.0.1/") {
  const url = new URL(streamUrl, baseUrl);
  url.searchParams.set("after", String(lastSequence));
  url.searchParams.set("follow", "1");
  return `${url.pathname}?${url.searchParams.toString()}`;
}

function eventLabel(kind) {
  return EVENT_LABELS[kind] || "已觀察到結構化活動";
}

function lifecycleLabel(stage) {
  return LIFECYCLE_LABELS[stage] || "狀態不明";
}

function warningLabel(code) {
  return WARNING_LABELS[code] || "Workflow 警告或錯誤";
}

function relativeAge(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "時間不明";
  if (seconds < 5) return "剛剛";
  if (seconds < 60) return `${Math.floor(seconds)} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分鐘前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小時前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

function relativeTimeFrom(value, nowMilliseconds = Date.now()) {
  if (typeof value !== "string" || !Number.isFinite(nowMilliseconds)) return "時間不明";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "時間不明";
  const delta = (nowMilliseconds - timestamp) / 1000;
  if (Math.abs(delta) < 5) return "剛剛";
  if (delta >= 0) return relativeAge(delta);
  const seconds = Math.abs(delta);
  if (seconds < 60) return `${Math.floor(seconds)} 秒後`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分鐘後`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小時後`;
  return `${Math.floor(seconds / 86400)} 天後`;
}

function localTimestamp(value) {
  if (typeof value !== "string") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function timestampWithAge(value, ageSeconds) {
  const local = localTimestamp(value);
  return local === "—" ? local : `${local} · ${relativeAge(ageSeconds)}`;
}

function timestampWithRelative(value) {
  const local = localTimestamp(value);
  return local === "—" ? local : `${local} · ${relativeTimeFrom(value)}`;
}

function cadenceLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "狀態不明";
  if (seconds < 60) return `約每 ${seconds} 秒檢查一次工作`;
  const minutes = seconds / 60;
  return `約每 ${Number.isInteger(minutes) ? minutes : minutes.toFixed(1)} 分鐘檢查一次工作`;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    eventLabel,
    lifecycleLabel,
    mergeEventCache,
    streamUrlWithCursor,
    validEvent,
    warningLabel,
    relativeAge,
    relativeTimeFrom,
    cadenceLabel,
  };
} else {
  startPanel();
}

function startPanel() {
  const elements = {
    readiness: document.querySelector("#readiness"),
    workflowReadiness: document.querySelector("#workflow-readiness"),
    operatorHealth: document.querySelector("#operator-health"),
    panelHealth: document.querySelector("#panel-health"),
    nextAction: document.querySelector("#next-action"),
    stage: document.querySelector("#stage"),
    requestSummary: document.querySelector("#request-summary"),
    requestId: document.querySelector("#request-id"),
    issueNumber: document.querySelector("#issue-number"),
    requestAction: document.querySelector("#request-action"),
    detectedTime: document.querySelector("#detected-time"),
    expiryTime: document.querySelector("#expiry-time"),
    pickupDecision: document.querySelector("#pickup-decision"),
    evidenceTime: document.querySelector("#evidence-time"),
    operatorHealthDetail: document.querySelector("#operator-health-detail"),
    heartbeatTime: document.querySelector("#heartbeat-time"),
    heartbeatAge: document.querySelector("#heartbeat-age"),
    lastCheckTime: document.querySelector("#last-check-time"),
    pollCadence: document.querySelector("#poll-cadence"),
    scanResult: document.querySelector("#scan-result"),
    operatorCycle: document.querySelector("#operator-cycle"),
    diagnostics: document.querySelector("#diagnostics"),
    warning: document.querySelector("#warning-or-error"),
    changedFiles: document.querySelector("#changed-files"),
    testSummary: document.querySelector("#test-summary"),
    evidence: document.querySelector("#evidence-summary"),
    activity: document.querySelector("#activity"),
    eventCount: document.querySelector("#event-count"),
    connectionStatus: document.querySelector("#connection-status"),
    connectionDot: document.querySelector("#connection-dot"),
    refresh: document.querySelector("#refresh"),
  };

  let eventSource = null;
  let connectedStreamUrl = null;
  let snapshotRefreshQueued = false;
  let eventCache = readEventCache();
  let lastSequence = Math.max(readCursor(), ...eventCache.map((event) => event.sequence), 0);

  function shown(value, fallback = "無法取得") {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  function readCursor() {
    try {
      const value = Number(sessionStorage.getItem(CURSOR_KEY));
      return Number.isSafeInteger(value) && value >= 0 ? value : 0;
    } catch (_error) {
      return 0;
    }
  }

  function readEventCache() {
    try {
      const value = JSON.parse(sessionStorage.getItem(EVENTS_KEY) || "[]");
      if (!Array.isArray(value)) return [];
      const unique = new Map();
      value.filter(validEvent).forEach((event) => unique.set(event.sequence, event));
      return [...unique.values()]
        .sort((left, right) => left.sequence - right.sequence)
        .slice(-MAX_RENDERED_EVENTS);
    } catch (_error) {
      return [];
    }
  }

  function persistCursorAndEvents() {
    try {
      sessionStorage.setItem(CURSOR_KEY, String(lastSequence));
      sessionStorage.setItem(EVENTS_KEY, JSON.stringify(eventCache));
    } catch (_error) {
      setConnection("即時連線 · cursor 保存狀態降級", "degraded");
    }
  }

  function setConnection(status, tone) {
    elements.connectionStatus.textContent = status;
    elements.connectionDot.dataset.tone = tone;
  }

  function renderSnapshot(snapshot) {
    const system = snapshot.system;
    const task = snapshot.current_task;
    const lifecycle = task.lifecycle;
    const readiness = system.readiness || "unavailable";
    elements.readiness.textContent = READINESS_LABELS[readiness] || "本機 Workflow 不可用";
    elements.readiness.dataset.readiness = readiness;
    const localWorkflow = READINESS_LABELS[system.local_workflow || system.workflow]
      || "本機 Workflow 不可用";
    const externalExecution = EXTERNAL_EXECUTION_LABELS[system.external_model_execution]
      || "外部模型執行可用性不明";
    elements.workflowReadiness.textContent = `${localWorkflow}；${externalExecution}`;
    elements.operatorHealth.textContent = HEALTH_LABELS[system.operator] || "Operator 狀態不明";
    elements.panelHealth.textContent = system.panel === "online" ? "Panel 連線正常" : "Panel 不可用";
    elements.nextAction.textContent = shown(system.next_action, "目前狀態不明。");

    elements.stage.textContent = lifecycleLabel(lifecycle.stage);
    elements.stage.dataset.stage = lifecycle.stage;
    elements.stage.dataset.certainty = lifecycle.certainty;
    elements.requestSummary.textContent = shown(system.next_action, "目前的請求狀態不明。");
    elements.requestId.textContent = shown(task.request_id, "—");
    elements.issueNumber.textContent = task.issue_number ? `#${task.issue_number}` : "—";
    elements.requestAction.textContent = shown(task.action, "—");
    elements.detectedTime.textContent = timestampWithRelative(task.detected_at_utc);
    elements.expiryTime.textContent = timestampWithRelative(task.expires_at_utc);
    elements.pickupDecision.textContent = PICKUP_LABELS[task.pickup_decision] || "—";
    elements.evidenceTime.textContent = timestampWithRelative(task.updated_at_utc);

    const activity = snapshot.operator.activity;
    elements.operatorHealthDetail.textContent = HEALTH_LABELS[activity.health] || "Operator 狀態不明";
    elements.heartbeatTime.textContent = timestampWithAge(
      activity.heartbeat_at_utc,
      activity.heartbeat_age_seconds,
    );
    elements.heartbeatAge.textContent = relativeAge(activity.heartbeat_age_seconds);
    elements.lastCheckTime.textContent = timestampWithAge(
      activity.last_check_at_utc,
      activity.last_check_age_seconds,
    );
    elements.pollCadence.textContent = cadenceLabel(activity.poll_interval_seconds);
    elements.scanResult.textContent = SCAN_LABELS[activity.scan_result] || "狀態不明";
    elements.operatorCycle.textContent = Number.isSafeInteger(activity.cycle)
      ? `第 ${activity.cycle} 次檢查`
      : "—";

    renderReview(snapshot.review);
    if (snapshot.diagnostics.length) {
      elements.diagnostics.hidden = false;
      elements.diagnostics.textContent = "部分本機證據缺失或格式錯誤。狀態已安全降級。";
    } else {
      elements.diagnostics.hidden = true;
      elements.diagnostics.textContent = "";
    }
    connectEvents(snapshot.observability.stream_url);
  }

  function renderReview(review) {
    const warning = review.warning_or_error;
    elements.warning.textContent = warning.status === "available"
      ? `${warningLabel(warning.code)} · ${localTimestamp(warning.observed_at_utc)}`
      : "無法取得";
    elements.changedFiles.textContent = review.changed_files.status === "available"
      ? review.changed_files.items.join(", ")
      : "無法取得";
    elements.testSummary.textContent = review.test_summary.status === "available"
      ? shown(review.test_summary.summary, "狀態不明")
      : "無法取得";
    elements.evidence.textContent = review.evidence.status === "available"
      ? `${shown(review.evidence.summary, "有可用證據")} · ${review.evidence.pointer}`
      : "無法取得";
  }

  function safeDetail(value) {
    return typeof value === "string" && value.length <= 256 ? value : null;
  }

  function eventSummary(event) {
    const details = [];
    const commandName = safeDetail(event.payload.command_name);
    const reason = safeDetail(event.payload.reason);
    if (commandName) details.push(commandName);
    if (Number.isSafeInteger(event.payload.exit_code)) details.push(`exit ${event.payload.exit_code}`);
    if (Array.isArray(event.payload.paths)) {
      const paths = event.payload.paths.filter((path) => safeDetail(path)).slice(0, 16);
      if (paths.length) details.push(paths.join(", "));
    }
    if (reason) details.push(`${warningLabel(reason)} (${reason})`);
    const label = eventLabel(event.kind);
    return details.length ? `${label} · ${details.join(" · ")}` : label;
  }

  function renderTimeline() {
    elements.activity.replaceChildren();
    if (!eventCache.length) {
      const empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "等待有限範圍的觀測事件。";
      elements.activity.append(empty);
    } else {
      eventCache.slice().reverse().forEach((event) => {
        const item = document.createElement("li");
        const time = document.createElement("time");
        const content = document.createElement("div");
        const kind = document.createElement("strong");
        const identity = document.createElement("small");
        time.textContent = event.observed_at_utc;
        kind.textContent = eventSummary(event);
        identity.textContent = `活動事件 ${event.sequence}`;
        content.append(kind, identity);
        item.append(time, content);
        elements.activity.append(item);
      });
    }
    elements.eventCount.textContent = `${eventCache.length} 個事件 · cursor ${lastSequence}`;
  }

  function acceptEvent(event) {
    const merged = mergeEventCache(eventCache, event, lastSequence);
    if (!merged.accepted) return false;
    eventCache = merged.events;
    lastSequence = merged.lastSequence;
    persistCursorAndEvents();
    renderTimeline();
    return true;
  }

  function connectEvents(streamUrl) {
    if (eventSource && connectedStreamUrl === streamUrl) return;
    if (eventSource) eventSource.close();
    connectedStreamUrl = streamUrl;
    setConnection("連線中", "pending");
    eventSource = new EventSource(streamUrlWithCursor(streamUrl, lastSequence, window.location.href));
    eventSource.addEventListener("open", () => setConnection("即時連線 · 唯讀", "live"));
    eventSource.addEventListener("workflow-observation", (message) => {
      try {
        if (acceptEvent(JSON.parse(message.data))) queueSnapshotRefresh();
      } catch (_error) {
        setConnection("事件解析狀態降級", "degraded");
      }
    });
    eventSource.addEventListener("error", () => setConnection("重新連線中", "degraded"));
  }

  function queueSnapshotRefresh() {
    if (snapshotRefreshQueued) return;
    snapshotRefreshQueued = true;
    setTimeout(() => {
      snapshotRefreshQueued = false;
      refreshSnapshot(false);
    }, 0);
  }

  async function refreshSnapshot(manual = false) {
    if (manual) elements.refresh.disabled = true;
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      if (!response.ok) throw new Error(`snapshot ${response.status}`);
      renderSnapshot(await response.json());
    } catch (_error) {
      setConnection("狀態快照不可用", "degraded");
      elements.panelHealth.textContent = "Panel 不可用";
      elements.readiness.textContent = "本機 Workflow 不可用";
      elements.readiness.dataset.readiness = "unavailable";
    } finally {
      if (manual) elements.refresh.disabled = false;
    }
  }

  elements.refresh.addEventListener("click", () => refreshSnapshot(true));
  window.addEventListener("beforeunload", () => {
    if (eventSource) eventSource.close();
  });
  renderTimeline();
  refreshSnapshot(false);
  setInterval(() => refreshSnapshot(false), SNAPSHOT_POLL_MS);
}
