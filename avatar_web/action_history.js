const dialog = document.getElementById('action-history-dialog');
const list = document.getElementById('action-history-entries');
const status = document.getElementById('action-history-status');

async function loadHistory() {
  const response = await fetch('/api/action-history', { cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Action log request failed (${response.status}).`);
  list.replaceChildren();
  if (!data.entries.length) {
    const empty = document.createElement('p');
    empty.className = 'detail';
    empty.textContent = 'No approved computer actions have been recorded yet.';
    list.append(empty);
    return;
  }
  for (const entry of [...data.entries].reverse()) {
    const row = document.createElement('div');
    row.className = 'action-history-entry';
    const command = document.createElement('span');
    command.className = 'action-history-command';
    command.textContent = entry.command;
    const state = document.createElement('span');
    state.className = 'action-history-status';
    const when = entry.dispatched_at ? new Date(entry.dispatched_at).toLocaleString() : 'Time unavailable';
    state.textContent = `${when} · ${entry.status}${entry.undo_available ? ' · undo available' : ''}`;
    row.append(command, state);
    list.append(row);
  }
}

document.getElementById('open-action-history').addEventListener('click', async () => {
  dialog.showModal();
  status.classList.remove('warning');
  status.textContent = 'Loading approved actions…';
  try {
    await loadHistory();
    status.textContent = '';
  } catch (error) {
    status.textContent = error.message;
    status.classList.add('warning');
  }
});

document.getElementById('close-action-history').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => {
  if (event.target === dialog) dialog.close();
});
