const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../../src/companion_core/static/chat.js'), 'utf8');
const keyHandler = script.slice(script.indexOf('  let composingQuestion=false;'), script.indexOf("  el('chat-sources').onchange="));

function composer({disabled = false, organizing = false} = {}) {
  const events = {};
  let sent = 0;
  let organizeSent = 0;
  const question = {addEventListener: (type, callback) => {events[type] = callback;}};
  const elements = {
    'chat-question': question, 'chat-send': {disabled}, 'organize-start': {disabled},
    'chat-form': {requestSubmit: () => {sent++;}},
  };
  const window = {NexusOrganize: {active: () => organizing, submit: () => {organizeSent++;}}};
  vm.runInNewContext(keyHandler, {el: id => elements[id], window});
  return {events, press(extra = {}) {
    const event = {key: 'Enter', defaultPrevented: false, preventDefault() {this.defaultPrevented = true;}, ...extra};
    question.onkeydown(event);
    return event.defaultPrevented;
  }, sent: () => sent, organizeSent: () => organizeSent};
}

test('Enter, Ctrl+Enter and Meta+Enter all use the existing form submit path', () => {
  const c = composer();
  for (const modifiers of [{}, {ctrlKey:true}, {metaKey:true}]) assert.equal(c.press(modifiers), true);
  assert.equal(c.sent(), 3);
});

test('newline, IME selection and a consumed event never submit', () => {
  const c = composer();
  assert.equal(c.press({shiftKey:true}), false);
  assert.equal(c.press({shiftKey:true, ctrlKey:true}), false);
  assert.equal(c.press({altKey:true}), false);
  assert.equal(c.press({isComposing:true}), false);
  assert.equal(c.press({keyCode:229}), false);
  c.events.compositionstart();
  assert.equal(c.press({ctrlKey:true}), false);
  c.events.compositionend();
  assert.equal(c.press({defaultPrevented:true}), true);
  assert.equal(c.sent(), 0);
  assert.equal(c.press(), true);
  assert.equal(c.sent(), 1);
});

test('held keys and disabled send do not resubmit', () => {
  const c = composer();
  assert.equal(c.press(), true);
  assert.equal(c.press({repeat:true}), true);
  assert.equal(c.sent(), 1);
  const disabled = composer({disabled:true});
  disabled.press();
  assert.equal(disabled.sent(), 0);
});

test('document organize keeps its existing explicit shortcut', () => {
  const c = composer({organizing:true});
  assert.equal(c.press(), false);
  assert.equal(c.press({ctrlKey:true}), true);
  assert.equal(c.sent(), 0);
  assert.equal(c.organizeSent(), 1);
});

test('paste and drop only attach explicit files without submitting the form', () => {
  const events = new Map();
  const attached = [];
  const elements = new Map();
  const ctx = {el(id) {
    if (!elements.has(id)) elements.set(id, {addEventListener(type, action) {events.set(id+':'+type, action);}});
    return elements.get(id);
  }, takeImageFiles: files => attached.push(Array.from(files)), canAttachImage: () => true};
  vm.runInNewContext(script.slice(script.indexOf("  el('chat-image-pick').onclick="), script.indexOf("  el('chat-question').oninput=")),ctx);
  const png = {type:'image/png'};
  let prevented = 0;
  const base = {preventDefault: () => {prevented++;}};
  events.get('chat-question:paste')({...base, clipboardData:{items:[{kind:'string',type:'text/plain'}]}});
  assert.equal(prevented, 0);
  events.get('chat-question:paste')({...base, clipboardData:{items:[{kind:'file',type:'image/png',getAsFile:()=>png}]}});
  events.get('chat-form:drop')({...base,dataTransfer:{files:[png]}});
  assert.equal(prevented, 2);
  assert.deepEqual(attached, [[png],[png]]);
});
