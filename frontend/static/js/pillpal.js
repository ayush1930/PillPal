function toggleSidebar(force) {
  const sidebar = document.querySelector('#sidebar');
  if (!sidebar) return;
  const open = force === undefined ? !sidebar.classList.contains('open') : force;
  sidebar.classList.toggle('open', open);
  document.body.classList.toggle('sidebar-open', open);
}

document.addEventListener('click', event => {
  if (event.target.closest('[data-sidebar-toggle]')) {
    toggleSidebar();
    return;
  }
  if (event.target.closest('[data-dialog-close]')) {
    event.target.closest('dialog')?.close();
    return;
  }
  const tab = event.target.closest('[data-profile-tab]');
  if (tab) {
    document.querySelectorAll('[data-profile-tab]').forEach(item => item.classList.toggle('active', item === tab));
    document.querySelectorAll('[data-profile-panel]').forEach(panel => {
      panel.hidden = panel.dataset.profilePanel !== tab.dataset.profileTab;
    });
  }
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') toggleSidebar(false);
});

document.addEventListener('submit', event => {
  const form = event.target;
  if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) event.preventDefault();
});

document.addEventListener('change', event => {
  const input = event.target;
  const form = input.closest('[data-auto-submit]');
  if (form && (input.tagName === 'SELECT' || ['checkbox', 'radio'].includes(input.type))) form.requestSubmit();
  if (input.matches('[data-delivery-type]')) {
    const address = input.form.querySelector('[data-address-field]');
    if (address) address.hidden = input.value === 'pickup';
    const summary = input.closest('[data-cart-subtotal]');
    if (summary) {
      const subtotal = Number(summary.dataset.cartSubtotal);
      const fee = input.value === 'delivery' && subtotal < 1200 ? 199.60 : 0;
      summary.querySelector('[data-delivery-charge]').textContent = `$${fee.toFixed(2)}`;
      summary.querySelector('[data-cart-total]').textContent = `$${(subtotal + fee).toFixed(2)}`;
    }
  }
  if (input.type === 'file') {
    const label = input.closest('[data-upload-zone]')?.querySelector('.selected-file');
    if (label) label.textContent = input.files[0]?.name || '';
  }
});

['dragenter', 'dragover'].forEach(type => document.addEventListener(type, event => {
  const zone = event.target.closest('[data-upload-zone]');
  if (zone) {
    event.preventDefault();
    zone.classList.add('drag-over');
  }
}));
document.addEventListener('dragleave', event => {
  event.target.closest('[data-upload-zone]')?.classList.remove('drag-over');
});
document.addEventListener('drop', event => {
  const zone = event.target.closest('[data-upload-zone]');
  if (!zone) return;
  event.preventDefault();
  zone.classList.remove('drag-over');
  const input = zone.querySelector('input[type="file"]');
  if (input && event.dataTransfer.files.length) {
    input.files = event.dataTransfer.files;
    input.dispatchEvent(new Event('change', {
      bubbles: true
    }));
  }
});

const errorBackButton = document.querySelector('[data-error-back]');
if (errorBackButton && window.history.length > 1) {
  errorBackButton.hidden = false;
  errorBackButton.addEventListener('click', () => window.history.back());
}
