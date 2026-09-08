"use strict";

const CURSOR_KEY = "lawb.workflow_panel.cursor.v1";
const EVENTS_KEY = "lawb.workflow_panel.events.v1";
const MAX_RENDERED_EVENTS = 80;
const SNAPSHOT_POLL_MS = 2000;

const LIFECYCLE_LABELS = Object.freeze({
  IDLE: "No request detected",
  CHECKING_FOR_WORK: "Checking for work",
  NO_REQUEST_DETECTED: "No request detected",
  REQUEST_DETECTED: "Request detected / waiting for pickup",
  DISPATCHING: "Dispatching",
  RUNNING: "Running",
  BLOCKED_OR_FAILED: "Blocked / failed",
  WAITING_FOR_CHATGPT_REVIEW: "Waiting for ChatGPT review",
  COMPLETED_OR_LAST_COMPLETED: "Completed / last completed",
  EXPIRED: "Expired",
  UNKNOWN: "Unknown",
});

const READINESS_LABELS = Object.freeze({
  ready: "Workflow ready",
  degraded: "Workflow degraded",
  unavailable: "Workflow unavailable",
});

const HEALTH_LABELS = Object.freeze({
  online: "Operator online",
  offline: "Operator offline",
  stale: "Operator stale",
  unknown: "Operator status unknown",
});

const SCAN_LABELS = Object.freeze({
  eligible_request_detected: "Request detected",
  expired_request_observed: "Expired request observed",
  no_eligible_request: "No eligible request found",
  scan_blocked: "Inbox check blocked",
});

const PICKUP_LABELS = Object.freeze({
  ready_for_pickup: "Ready for pickup",
  not_eligible: "No eligible request",
  expired: "Expired; not picked up",
  blocked: "Blocked before pickup",
  picked_up: "Picked up",
  completed: "Completed",
});

const EVENT_LABELS = Object.freeze({
  "execution.started": "Execution started",
  "codex.thread.started": "Codex session started",
  "codex.turn.started": "Codex turn started",
  "codex.turn.completed": "Codex turn completed (activity only)",
  "codex.turn.failed": "Codex turn failed (activity only)",
  "codex.error": "Codex reported an error",
  "codex.command.started": "Command started",
  "codex.command.completed": "Command completed",
  "codex.command.failed": "Command failed",
  "codex.file.started": "File activity started",
  "codex.file.completed": "File activity completed",
  "codex.file.failed": "File activity failed",
  "codex.message.completed": "Codex message observed",
  "codex.todo.started": "Task-list activity started",
  "codex.todo.completed": "Task-list activity completed",
  "process.completed": "Codex process exited (activity only)",
  "observability.source_warning": "Observability warning",
});

const WARNING_LABELS = Object.freeze({
  malformed_utf8: "Malformed UTF-8 source event",
  source_line_too_large: "Source event exceeded the size bound",
  malformed_json: "Malformed JSON source event",
  source_event_not_object: "Structured source event was not an object",
  source_event_type_missing: "Structured source event type was missing",
  unknown_source_event_type: "Unknown structured source event type",
  item_missing: "Structured event item was missing",
  item_type_missing: "Structured event item type was missing",
  sensitive_item_omitted: "Sensitive structured item was omitted",
  unknown_item_type: "Unknown structured item type",
  ingest_frame_malformed: "Observation ingest frame was malformed",
  runner_control_malformed: "Runner observation control frame was malformed",
  ingest_frame_unknown: "Observation ingest frame type was unknown",
  task_packet_id_request_id_mismatch: "Task Packet and request identity did not match",
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
  return EVENT_LABELS[kind] || "Observed structured activity";
}

function lifecycleLabel(stage) {
  return LIFECYCLE_LABELS[stage] || "Unknown";
}

function warningLabel(code) {
  return WARNING_LABELS[code] || "Workflow warning or error";
}

function relativeAge(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "time unknown";
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${Math.floor(seconds)} seconds ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
  return `${Math.floor(seconds / 86400)} days ago`;
}

function relativeTimeFrom(value, nowMilliseconds = Date.now()) {
  if (typeof value !== "string" || !Number.isFinite(nowMilliseconds)) return "time unknown";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "time unknown";
  const delta = (nowMilliseconds - timestamp) / 1000;
  if (Math.abs(delta) < 5) return "just now";
  if (delta >= 0) return relativeAge(delta);
  const future = relativeAge(Math.abs(delta)).replace(/ ago$/, "");
  return `in ${future}`;
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
  if (!Number.isFinite(seconds) || seconds < 0) return "Unknown";
  if (seconds < 60) return `Checks for work about every ${seconds} seconds`;
  const minutes = seconds / 60;
  return `Checks for work about every ${Number.isInteger(minutes) ? minutes : minutes.toFixed(1)} minutes`;
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

  function shown(value, fallback = "Unavailable") {
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
      setConnection("Live · cursor persistence degraded", "degraded");
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
    elements.readiness.textContent = READINESS_LABELS[readiness] || "Workflow unavailable";
    elements.readiness.dataset.readiness = readiness;
    elements.workflowReadiness.textContent = READINESS_LABELS[system.workflow] || "Workflow unavailable";
    elements.operatorHealth.textContent = HEALTH_LABELS[system.operator] || "Operator status unknown";
    elements.panelHealth.textContent = system.panel === "online" ? "Panel online" : "Panel unavailable";
    elements.nextAction.textContent = shown(system.next_action, "Current status is unknown.");

    elements.stage.textContent = lifecycleLabel(lifecycle.stage);
    elements.stage.dataset.stage = lifecycle.stage;
    elements.stage.dataset.certainty = lifecycle.certainty;
    elements.requestSummary.textContent = shown(system.next_action, "Current request state is unknown.");
    elements.requestId.textContent = shown(task.request_id, "—");
    elements.issueNumber.textContent = task.issue_number ? `#${task.issue_number}` : "—";
    elements.requestAction.textContent = shown(task.action, "—");
    elements.detectedTime.textContent = timestampWithRelative(task.detected_at_utc);
    elements.expiryTime.textContent = timestampWithRelative(task.expires_at_utc);
    elements.pickupDecision.textContent = PICKUP_LABELS[task.pickup_decision] || "—";
    elements.evidenceTime.textContent = timestampWithRelative(task.updated_at_utc);

    const activity = snapshot.operator.activity;
    elements.operatorHealthDetail.textContent = HEALTH_LABELS[activity.health] || "Operator status unknown";
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
    elements.scanResult.textContent = SCAN_LABELS[activity.scan_result] || "Unknown";
    elements.operatorCycle.textContent = Number.isSafeInteger(activity.cycle)
      ? `Check ${activity.cycle}`
      : "—";

    renderReview(snapshot.review);
    if (snapshot.diagnostics.length) {
      elements.diagnostics.hidden = false;
      elements.diagnostics.textContent = "Some local evidence is missing or malformed. Status has been degraded safely.";
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
      : "Unavailable";
    elements.changedFiles.textContent = review.changed_files.status === "available"
      ? review.changed_files.items.join(", ")
      : "Unavailable";
    elements.testSummary.textContent = review.test_summary.status === "available"
      ? shown(review.test_summary.summary, "Unknown")
      : "Unavailable";
    elements.evidence.textContent = review.evidence.status === "available"
      ? `${shown(review.evidence.summary, "Evidence available")} · ${review.evidence.pointer}`
      : "Unavailable";
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
      empty.textContent = "Waiting for bounded observation events.";
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
        identity.textContent = `Activity event ${event.sequence}`;
        content.append(kind, identity);
        item.append(time, content);
        elements.activity.append(item);
      });
    }
    elements.eventCount.textContent = `${eventCache.length} events · cursor ${lastSequence}`;
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
    setConnection("Connecting", "pending");
    eventSource = new EventSource(streamUrlWithCursor(streamUrl, lastSequence, window.location.href));
    eventSource.addEventListener("open", () => setConnection("Live · read only", "live"));
    eventSource.addEventListener("workflow-observation", (message) => {
      try {
        if (acceptEvent(JSON.parse(message.data))) queueSnapshotRefresh();
      } catch (_error) {
        setConnection("Event parse degraded", "degraded");
      }
    });
    eventSource.addEventListener("error", () => setConnection("Reconnecting", "degraded"));
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
      setConnection("Snapshot unavailable", "degraded");
      elements.panelHealth.textContent = "Panel unavailable";
      elements.readiness.textContent = "Workflow unavailable";
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
