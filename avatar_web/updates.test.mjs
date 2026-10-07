import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./updates.js', import.meta.url), 'utf8');

function hud() {
  const check = { hidden: true, addEventListener: (_, callback) => { check.click = callback; } };
  const message = { classList: { toggle() {}, add() {} } };
  const opened = [];
  const context = vm.createContext({
    document: { getElementById: id => id === 'check-updates' ? check : message },
    window: { open: (...args) => opened.push(args) },
    fetch: async () => ({ ok: true, json: async () => ({ state: 'current', current_version: '1.0.5' }) }),
    setTimeout() {},
  });
  vm.runInContext(source, context);
  return { check, message, opened, context };
}

test('update button appears only for an available release', () => {
  const { check, context } = hud();
  for (const state of ['unchecked', 'checking', 'current', 'error', 'available']) {
    context.data = { state, current_version: '1.0.5', version: 'v1.0.6' };
    vm.runInContext('showStatus(data)', context);
    assert.equal(check.hidden, state !== 'available');
  }
});

test('available update opens official releases without installing', () => {
  const { check, opened, context } = hud();
  check.click();
  assert.equal(opened.length, 0);
  vm.runInContext("showStatus({state: 'available', version: 'v1.0.6'})", context);
  check.click();
  assert.deepEqual(opened, [['https://github.com/someguyrighthere/Jarvis/releases/latest', '_blank', 'noopener,noreferrer']]);
});

test('check failures hide update button and report the error', () => {
  const { check, message, context } = hud();
  vm.runInContext("showStatus({state: 'available', version: 'v1.0.6'}); showError(new Error('Network unavailable'))", context);
  assert.equal(check.hidden, true);
  assert.equal(message.textContent, 'Network unavailable');
});
