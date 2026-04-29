// Replay form handler
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('replay-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const logs = document.getElementById('replay-logs').value.trim();
    if (!logs) {
      alert('Please paste logs first');
      return;
    }

    const resultEl = document.getElementById('replay-result');
    const button = form.querySelector('button');
    const originalButtonText = button.textContent;

    // Show loading state
    resultEl.innerHTML = '<div class="loading">🔄 Processing logs...</div>';
    button.disabled = true;
    button.textContent = 'Processing...';

    try {
      const res = await fetch('/replay/logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs }),
      });

      const data = await res.json();

      if (!res.ok || data.status === 'error') {
        showReplayError(resultEl, data);
      } else if (data.status === 'no_events_parsed') {
        showReplayWarning(resultEl, `No valid SignalThrottle logs found in ${data.line_count} lines. Check timestamp format.`);
      } else if (data.status === 'processed') {
        showReplaySuccess(resultEl, data);
        // Reload page after 2s to show updated blocks
        setTimeout(() => location.reload(), 2000);
      } else {
        showReplayWarning(resultEl, `Unexpected status: ${data.status}`);
      }
    } catch (err) {
      showReplayError(resultEl, { error: 'network_error', message: err.message });
    } finally {
      button.disabled = false;
      button.textContent = originalButtonText;
    }
  });

  function showReplaySuccess(el, data) {
    el.innerHTML = `
      <div class="result result-success">
        <h3>✅ Replay Successful</h3>
        <div class="result-stats">
          <p><strong>Parsed:</strong> ${data.events_parsed} events</p>
          <p><strong>Stored:</strong> ${data.events_stored} new</p>
          <p><strong>Duplicates:</strong> ${data.duplicates_skipped} skipped</p>
          <p><strong>Blocks Detected:</strong> ${data.canonical_blocks_detected}</p>
          <p><strong>Created:</strong> ${data.blocks_created} | <strong>Updated:</strong> ${data.blocks_updated}</p>
          <p><strong>Trade Plans:</strong> ${data.trade_plans_created} generated</p>
        </div>
        ${data.blocks && data.blocks.length > 0 ? `
          <details class="result-details">
            <summary>View Block Details</summary>
            <div class="blocks-list">
              ${data.blocks.map(b => `
                <div class="block-item">
                  <strong>${b.symbol}</strong> - Grade: <span class="grade grade-${b.pressure_grade}">${b.pressure_grade}</span>
                  <br>Duration: ${b.duration_minutes.toFixed(1)}min | Events: ${b.event_count} | Density: ${b.density_per_minute.toFixed(2)}/min
                  <br>Action: ${b.action === 'created' ? '🆕 Created' : '🔄 Updated'} ${b.trade_plan_created ? '| 📊 Trade Plan ✓' : ''}
                </div>
              `).join('')}
            </div>
          </details>
        ` : ''}
        <p style="margin-top: 1rem; font-size: 0.9em; color: #666;">Reloading dashboard...</p>
      </div>
    `;
  }

  function showReplayWarning(el, message) {
    el.innerHTML = `
      <div class="result result-warning">
        <h3>⚠️ Warning</h3>
        <p>${message}</p>
      </div>
    `;
  }

  function showReplayError(el, data) {
    const errorMsg = data.message || data.error || 'Unknown error';
    el.innerHTML = `
      <div class="result result-error">
        <h3>❌ Error</h3>
        <p><strong>Status:</strong> ${data.error || data.status || 'unknown'}</p>
        <p><strong>Details:</strong> ${errorMsg}</p>
        ${data.events_parsed ? `<p>Parsed ${data.events_parsed} events before failure</p>` : ''}
      </div>
    `;
  }
});

document.body.addEventListener('htmx:beforeRequest', (event) => {
  const sourceElement = event.target;
  if (!(sourceElement instanceof Element)) {
    return;
  }

  const gatedFragment = sourceElement.closest('[data-refresh-when-visible="true"]');
  if (gatedFragment && document.hidden) {
    event.preventDefault();
  }
});
