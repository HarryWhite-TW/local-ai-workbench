const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../../src/companion_core/static/surface.js"), "utf8");
function setup() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {disabled: true, hidden: false, value: "", dataset: {}, children: [],
      textContent: "", classList: {add() {}, remove() {}}, style: {setProperty() {}},
      setAttribute() {}, replaceChildren(...nodes) {this.children = nodes;}, append(...nodes) {this.children.push(...nodes);},
      querySelector: selector => element(id + selector), addEventListener() {}, focus() {}, scrollTo() {},
      getBoundingClientRect: () => ({left:0,top:0,width:800,height:500})});
    return elements.get(id);
  };
  const state = {workspace: "repo", active: {task_id: "exact-task", intent: "Inspect", state: "RUNNING"},
    busy: true, progress: [], notice: "", tasks: [], authority:"READ_ONLY", runtime:"synthetic-no-ai"};
  const posts = [];
  let resolveStop, rejectStop;
  const context = vm.createContext({
    document: {getElementById: element, createElement: () => element("generated-"+Math.random()),
      createTextNode: text => ({textContent:text}), querySelector: selector => element(selector),
      querySelectorAll: () => [], addEventListener() {}, body: {dataset: {}}},
    window: {addEventListener() {}, dispatchEvent() {}, CompanionReading: {result(parent,value) {parent.textContent=value;}}},
    CustomEvent: class {constructor(type,options) {this.type=type;this.detail=options.detail;}},
    matchMedia: () => ({matches:true,addEventListener() {}}),
    localStorage: {getItem() {return null;},setItem() {}}, AbortController, clearTimeout() {},
    getComputedStyle: () => ({zoom:"1",borderTopLeftRadius:"26px"}),
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
    resolve: () => resolveStop({ok: true, json: async () => ({task_id:"exact-task",state: "CANCEL_REQUESTED"})}),
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
  assert.match(ui.element("footer-status").textContent, /尚未確認取消/);
  for (const status of ["CANCELLED", "FAILED", "RESULT_PENDING_REVIEW"]) {
    ui.state.active.state = status; await ui.refresh();
    assert.equal(ui.element("stop").hidden, true);
    assert.equal(ui.element("stop").disabled, true);
  }
  assert.match(ui.element("footer-status").textContent, /等待審查/);
});
test("disconnect and failed Stop do not retry or claim cancellation", async () => {
  const ui = setup(); await ui.refresh();
  vm.runInContext("disconnected()", ui.context);
  assert.equal(ui.posts.length, 0);
  assert.equal(ui.element("stop").disabled, true);
  assert.match(ui.element("connection-banner").textContent, /不代表停止/);
  await ui.refresh();
  const click = ui.element("stop").onclick();
  ui.reject(); await click;
  await ui.refresh(); await ui.element("stop").onclick();
  assert.equal(ui.posts.length, 1);
  assert.equal(ui.element("stop").disabled, true);
  assert.match(ui.element("footer-status").textContent, /不會自動重試/);
  assert.doesNotMatch(ui.element("footer-status").textContent, /private/);
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
