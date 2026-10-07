const controls = document.getElementById('assistant-controls');
const start = document.getElementById('start-assistant');
const stop = document.getElementById('stop-assistant');
const message = document.getElementById('assistant-message');
let pending = false;

function show(data) {
  controls.hidden = !data.supported;
  start.disabled = pending || data.running;
  stop.disabled = pending || !data.running;
  message.textContent = data.error || (data.running ? 'Assistant running' : 'Assistant stopped');
  message.classList.toggle('warning', Boolean(data.error));
}

async function request(action) {
  const response = await fetch(`/api/assistant${action ? `/${action}` : ''}`, {
    cache: 'no-store', ...(action ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Assistant request failed (${response.status}).`);
  return data;
}

async function action(name) {
  if (pending) return;
  pending = true;
  start.disabled = stop.disabled = true;
  try {
    const data = await request(name);
    pending = false;
    show(data);
  } catch (error) {
    pending = false;
    start.disabled = stop.disabled = false;
    message.textContent = error.message;
    message.classList.add('warning');
  }
}

start.addEventListener('click', () => action('start'));
stop.addEventListener('click', () => action('stop'));

async function poll() {
  try {
    const data = await request();
    if (!pending) show(data);
  } catch (error) {
    message.textContent = error.message;
    message.classList.add('warning');
  }
  setTimeout(poll, 1500);
}
poll();
