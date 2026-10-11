const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../../src/companion_core/static/surface.js"), "utf8");
function setup() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {disabled: true, hidden: false, value: "",
      textContent: "", setAttribute() {}, replaceChildren() {}});
    return elements.get(id);
  };
  const state = {workspace: "repo", active: {task_id: "exact-task", intent: "Inspect", state: "RUNNING"},
    busy: true, progress: [], notice: "", tasks: []};
  const posts = [];
  let resolveStop, rejectStop;
  const context = vm.createContext({
    document: {getElementById: element, createElement: () => ({}), body: {classList: {toggle() {}}}},
    Option: function(text, value) { return {text, value}; }, setTimeout() {},
    fetch: async (url, options) => {
      if (url === "/api/state") return {ok: true, json: async () => structuredClone(state)};
      posts.push({url, body: JSON.parse(options.body)});
      return new Promise((resolve, reject) => { resolveStop = resolve; rejectStop = reject; });
    }
  });
  vm.runInContext(source, context);
  return {context, state, posts, element,
    refresh: () => vm.runInContext("refresh()", context),
    resolve: () => resolveStop({ok: true, json: async () => ({state: "CANCEL_REQUESTED"})}),
    reject: () => rejectStop(new Error("private provider detail"))};
}
test("Stop binds exact task, disables immediately, never resubmits, and preserves terminal states", async () => {
  const ui = setup();
  await ui.refresh();
  assert.equal(ui.element("stop").disabled, false);
  assert.equal(ui.element("stop").hidden, false);
  const first = ui.element("stop").onclick();
  await ui.element("stop").onclick();
  assert.equal(ui.posts.length, 1);
  assert.deepEqual(ui.posts[0], {url: "/api/cancel", body: {task_id: "exact-task"}});
  assert.equal(ui.element("stop").disabled, true);
  ui.state.active.state = "CANCEL_REQUESTED";
  ui.resolve(); await first;
  assert.equal(ui.element("stop").disabled, true);
  assert.match(ui.element("active").textContent, /尚未確認取消/);
  for (const status of ["CANCELLED", "FAILED", "RESULT_PENDING_REVIEW"]) {
    ui.state.active.state = status; await ui.refresh();
    assert.equal(ui.element("stop").hidden, true);
    assert.equal(ui.element("stop").disabled, true);
  }
  assert.match(ui.element("active").textContent, /等待審查/);
});
test("disconnect and failed Stop do not retry or claim cancellation", async () => {
  const ui = setup(); await ui.refresh();
  vm.runInContext("disconnected()", ui.context);
  assert.equal(ui.posts.length, 0);
  assert.equal(ui.element("stop").disabled, true);
  assert.match(ui.element("connection").textContent, /不代表取消/);
  await ui.refresh();
  const click = ui.element("stop").onclick();
  ui.reject(); await click;
  await ui.refresh(); await ui.element("stop").onclick();
  assert.equal(ui.posts.length, 1);
  assert.equal(ui.element("stop").disabled, true);
  assert.match(ui.element("stop-status").textContent, /不會自動重試/);
  assert.doesNotMatch(ui.element("stop-status").textContent, /private/);
});
test("no active or CREATED task exposes Stop", async () => {
  const ui = setup();
  ui.state.active = null; await ui.refresh();
  assert.equal(ui.element("stop").hidden, true);
  ui.state.active = {task_id: "not-started", state: "CREATED", intent: "Inspect"};
  await ui.refresh();
  assert.equal(ui.element("stop").hidden, true);
  await ui.element("stop").onclick();
  assert.equal(ui.posts.length, 0);
});
