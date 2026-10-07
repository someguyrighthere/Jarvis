import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./assistant.js', import.meta.url), 'utf8');
function hud() {
  const elements = new Map();
  const context = vm.createContext({
    document: { getElementById(id) {
      if (!elements.has(id)) elements.set(id, { hidden: false, classList: { toggle() {}, add() {} },
        addEventListener() {} });
      return elements.get(id);
    } },
    fetch: async () => ({ ok: true, json: async () => ({ supported: false }) }),
    setTimeout() {},
  });
  vm.runInContext(source, context);
  return { context, elements };
}

test('standalone browser does not display desktop process controls', () => {
  const { context, elements } = hud();
  vm.runInContext('show({supported:false,running:false})', context);
  assert.equal(elements.get('assistant-controls').hidden, true);
});

test('desktop controls follow running state and display startup errors', () => {
  const { context, elements } = hud();
  vm.runInContext('show({supported:true,running:true})', context);
  assert.equal(elements.get('assistant-controls').hidden, false);
  assert.equal(elements.get('start-assistant').disabled, true);
  assert.equal(elements.get('stop-assistant').disabled, false);
  assert.equal(elements.get('assistant-message').textContent, 'Assistant running');
  vm.runInContext("show({supported:true,running:false,error:'Chrome required'})", context);
  assert.equal(elements.get('start-assistant').disabled, false);
  assert.equal(elements.get('stop-assistant').disabled, true);
  assert.equal(elements.get('assistant-message').textContent, 'Chrome required');
});
