const dialog = document.getElementById('memory-dialog');
const entries = document.getElementById('memory-entries');
const status = document.getElementById('memory-status');
const form = document.getElementById('memory-add');

async function request(method = 'GET', payload) {
  const response = await fetch('/api/memory', {
    cache: 'no-store',
    ...(method === 'POST' ? {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Memory request failed (${response.status}).`);
  return data.entries;
}

function showError(error) {
  status.textContent = error.message;
  status.classList.add('warning');
}

function render(items) {
  entries.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'detail';
    empty.textContent = 'No saved memory yet.';
    entries.append(empty);
    return;
  }

  for (const entry of items) {
    const row = document.createElement('div');
    row.className = 'memory-entry';
    const category = document.createElement('span');
    category.className = 'memory-category';
    category.textContent = entry.key;
    const value = document.createElement('input');
    value.value = entry.value;
    value.maxLength = 1000;
    value.setAttribute('aria-label', `Saved memory in ${entry.key}`);
    const save = document.createElement('button');
    save.type = 'button';
    save.textContent = 'SAVE';
    save.addEventListener('click', async () => {
      try {
        status.classList.remove('warning');
        render(await request('POST', {
          action: 'update', key: entry.key, index: entry.index, value: value.value,
        }));
        status.textContent = 'Memory updated on this computer.';
      } catch (error) {
        showError(error);
      }
    });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'DELETE';
    remove.setAttribute('aria-label', `Delete saved memory in ${entry.key}`);
    remove.addEventListener('click', async () => {
      try {
        status.classList.remove('warning');
        render(await request('POST', {
          action: 'delete', key: entry.key, index: entry.index,
        }));
        status.textContent = 'Memory deleted from this computer.';
      } catch (error) {
        showError(error);
      }
    });
    row.append(category, value, save, remove);
    entries.append(row);
  }
}

document.getElementById('open-memory').addEventListener('click', async () => {
  dialog.showModal();
  status.classList.remove('warning');
  status.textContent = 'Loading saved memory…';
  try {
    render(await request());
    status.textContent = '';
  } catch (error) {
    showError(error);
  }
});

document.getElementById('close-memory').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => {
  if (event.target === dialog) dialog.close();
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  try {
    status.classList.remove('warning');
    render(await request('POST', {
      action: 'add',
      key: document.getElementById('memory-key').value,
      value: document.getElementById('memory-value').value,
    }));
    form.reset();
    status.textContent = 'Memory saved on this computer.';
  } catch (error) {
    showError(error);
  }
});
