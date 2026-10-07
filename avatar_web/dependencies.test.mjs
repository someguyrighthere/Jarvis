import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./dependencies.js', import.meta.url), 'utf8');

function hud() {
  const elements = new Map();
  function element() {
    return { hidden: true, classList: { toggle() {}, add() {} },
      children: [], addEventListener() {}, setAttribute() {}, append(...items) { this.children.push(...items); } };
  }
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, element());
        return elements.get(id);
      },
      createElement: element,
    },
    fetch: async () => ({ ok: true, json: async () => ({ busy: false, components: [] }) }),
    setTimeout() {},
  });
  vm.runInContext(source, context);
  return { context, elements };
}

test('dependency button is visible only when a component is missing', () => {
  const { context, elements } = hud();
  for (const states of [['unchecked'], ['installed', 'bundled'], ['installed', 'missing'], ['unavailable'], ['installed']]) {
    context.data = { busy: false, components: states.map((state, id) => ({ id, state })) };
    vm.runInContext('show(data)', context);
    assert.equal(elements.get('open-dependencies').hidden, !states.includes('missing'));
  }
});

test('check failures remain visible outside the dependency dialog', () => {
  const { context, elements } = hud();
  vm.runInContext("show({busy:false, components:[{id:'test',state:'unavailable'}]})", context);
  assert.equal(elements.get('dependency-message').textContent, 'Some dependency checks failed.');
  vm.runInContext("failure(new Error('Connection failed'))", context);
  assert.equal(elements.get('dependency-message').textContent, 'Connection failed');
});

test('skipped setup choices appear under optional installs', () => {
  const { context, elements } = hud();
  context.data = { busy: false, components: [
    { id: 'chrome', state: 'missing', optional: true },
    { id: 'packages', state: 'bundled', optional: false },
  ] };
  vm.runInContext('show(data)', context);
  assert.equal(elements.get('optional-dependencies').children.length, 1);
  assert.equal(elements.get('core-dependencies').children.length, 1);
});
