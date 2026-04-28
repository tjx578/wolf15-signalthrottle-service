// Replay form handler
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('replay-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const logs = document.getElementById('replay-logs').value.trim();
    if (!logs) return;

    const resultEl = document.getElementById('replay-result');
    resultEl.textContent = 'Processing...';

    try {
      const res = await fetch('/replay/logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs }),
      });

      const data = await res.json();
      resultEl.textContent = JSON.stringify(data, null, 2);

      // Reload page after 1s to show updated blocks
      if (data.status === 'processed') {
        setTimeout(() => location.reload(), 1500);
      }
    } catch (err) {
      resultEl.textContent = 'Error: ' + err.message;
    }
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const refreshSeconds = Number.parseInt(document.body.dataset.autoRefreshSeconds || '', 10);
  if (!Number.isFinite(refreshSeconds) || refreshSeconds <= 0) {
    return;
  }

  setInterval(() => {
    if (document.hidden) {
      return;
    }
    if (document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement) {
      return;
    }
    window.location.reload();
  }, refreshSeconds * 1000);
});
