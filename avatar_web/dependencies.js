const dialog = document.getElementById('dependency-dialog');
const status = document.getElementById('dependency-status');
const refresh = document.getElementById('refresh-dependencies');
const open = document.getElementById('open-dependencies');
const summary = document.getElementById('dependency-message');
let busy = false;
let pending = false;
const rows = new Map();

async function request(path, post = false) {
  const response = await fetch(path, { cache: 'no-store', ...(post ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
  } : {}) });
  if (!response.ok) {
    let detail = `Dependency request failed (${response.status}).`;
    const body = await response.text();
    try { detail = JSON.parse(body).error || detail; } catch { /* Report non-JSON server failures below. */ }
    throw new Error(detail);
  }
  return response.json();
}

function show(data) {
  busy = data.busy;
  open.hidden = !data.components.some(component => component.state === 'missing');
  const unavailable = data.components.some(component => component.state === 'unavailable');
  summary.textContent = data.error || (unavailable ? 'Some dependency checks failed.'
    : busy && !data.active ? 'Checking dependencies...' : '');
  summary.classList.toggle('warning', Boolean(data.error) || unavailable);
  status.textContent = data.error || data.message;
  status.classList.toggle('warning', Boolean(data.error));
  refresh.disabled = busy || pending;
  for (const component of data.components) {
    let row = rows.get(component.id);
    if (!row) {
      const container = document.createElement('section');
      container.className = 'dependency-row';
      const body = document.createElement('div');
      const heading = document.createElement('h3');
      heading.textContent = component.name;
      const description = document.createElement('p');
      description.className = 'detail';
      description.textContent = component.description;
      const detail = document.createElement('p');
      const button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('aria-label', `Install ${component.name}`);
      button.addEventListener('click', () => {
        if (busy || pending) return;
        if (confirm(`Install ${component.name}?\n\n${component.description}\n\nThis may download software/models, accept package licenses, modify this computer, and require Windows approval or a restart. SARA is not being updated. Continue?`)) {
          action(`/api/dependencies/install/${component.id}`);
        }
      });
      body.append(heading, description, detail);
      container.append(body, button);
      document.getElementById(component.optional ? 'optional-dependencies' : 'core-dependencies').append(container);
      row = { detail, button };
      rows.set(component.id, row);
    }
    row.detail.textContent = `${component.state.toUpperCase()} / ${component.detail}`;
    row.detail.classList.toggle('warning', ['missing', 'unavailable'].includes(component.state));
    const installed = ['installed', 'bundled'].includes(component.state);
    row.button.disabled = busy || pending || installed;
    row.button.textContent = data.active === component.id && busy ? 'INSTALLING...'
      : installed ? component.state.toUpperCase() : 'INSTALL';
  }
}

function failure(error) {
  status.textContent = error.message;
  status.classList.add('warning');
  summary.textContent = error.message;
  summary.classList.add('warning');
}

async function action(path) {
  if (pending || busy) return;
  pending = true;
  refresh.disabled = true;
  for (const row of rows.values()) row.button.disabled = true;
  try {
    const data = await request(path, true);
    pending = false;
    show(data);
  } catch (error) {
    pending = false;
    await poll(false);
    failure(error);
  }
}

async function poll(schedule = true) {
  try {
    const data = await request('/api/dependencies');
    if (!pending) show(data);
  } catch (error) {
    failure(error);
  }
  if (schedule) setTimeout(poll, 1500);
}

open.addEventListener('click', () => {
  dialog.showModal();
  poll(false);
});
document.getElementById('close-dependencies').addEventListener('click', () => dialog.close());
refresh.addEventListener('click', () => action('/api/dependencies/refresh'));
poll();
