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
