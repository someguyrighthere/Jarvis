const check = document.getElementById('check-updates');
const message = document.getElementById('update-message');
function showStatus(data) {
  check.hidden = data.state !== 'available';
  message.classList.toggle('warning', Boolean(data.error));
  message.textContent = data.error || ({
    unchecked: `SARA ${data.current_version}`,
    checking: 'Checking the latest GitHub release...',
    available: `SARA update ${data.version} is available on GitHub Releases.`,
    current: `SARA ${data.current_version}`,
  }[data.state] || 'Update status unavailable.');
}

function showError(error) {
  message.textContent = error.message;
  message.classList.add('warning');
  check.hidden = true;
}

async function request(url, options) {
  const response = await fetch(url, { cache: 'no-store', ...options });
  if (!response.ok) {
    const body = await response.text();
    let detail = `Update request failed (${response.status}).`;
    try { detail = JSON.parse(body).error || detail; } catch { /* Older servers may return HTML errors. */ }
    throw new Error(detail);
  }
  return response.json();
}

check.addEventListener('click', () => {
  if (!check.hidden) window.open('https://github.com/someguyrighthere/Jarvis/releases/latest', '_blank', 'noopener,noreferrer');
});

async function pollUpdates() {
  try {
    const data = await request('/api/updates');
    showStatus(data);
  } catch (error) {
    showError(error);
  }
  setTimeout(pollUpdates, 1500);
}
pollUpdates();
