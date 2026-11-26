/* Progressive controls for the modern UI; authorization stays on the server. */
(() => {
  'use strict';
  // Shared progressive handlers replace inline HTML handlers in both modes.
  // They preserve the strict CSP and never change the selected interface.
  document.querySelectorAll('img[data-cir-hide-on-error]').forEach((image) => {
    image.addEventListener('error', () => image.remove());
    if (image.complete && !image.naturalWidth) image.remove();
  });
  document.querySelectorAll('[data-cir-auto-submit]').forEach((input) => {
    input.addEventListener('change', () => {
      if (!input.form) return;
      if (typeof input.form.requestSubmit === 'function') input.form.requestSubmit();
      else input.form.submit();
    });
  });
  document.querySelectorAll('[data-cir-notification-bulk]').forEach((form) => {
    const master = form.querySelector('[data-cir-notification-select-all]');
    const items = [...form.querySelectorAll('[data-cir-notification-select]')];
    if (!master || !items.length) return;
    master.addEventListener('change', () => {
      items.forEach((item) => { item.checked = master.checked; });
      master.indeterminate = false;
    });
    items.forEach((item) => item.addEventListener('change', () => {
      const checked = items.filter((entry) => entry.checked).length;
      master.checked = checked === items.length;
      master.indeterminate = checked > 0 && checked < items.length;
    }));
    form.addEventListener('submit', (event) => {
      if (!items.some((item) => item.checked)) {
        event.preventDefault();
        window.alert(form.dataset.cirEmptySelection || 'Selezionare almeno un template da cancellare.');
      }
    });
  });
  document.querySelectorAll('[data-cir-confirm]').forEach((element) => {
    element.addEventListener(element.tagName === 'FORM' ? 'submit' : 'click', (event) => {
      if (!event.defaultPrevented && !window.confirm(element.dataset.cirConfirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('[data-cir-progress]').forEach((element) => {
    const raw = Number(element.dataset.cirProgress);
    const percent = Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : 0;
    element.style.width = `${percent}%`;
  });
  if (!document.body.classList.contains('cir-modern')) return;
  const shell = document.getElementById('cir-page-shell');
  if (!shell) return;
  const sidebar = document.getElementById('cir-sidebar');
  const workspace = document.getElementById('cir-workspace');
  const opener = document.querySelector('[data-cir-drawer-open]');
  const backdrop = document.querySelector('.cir-drawer-backdrop');
  const mobile = window.matchMedia('(max-width: 760px)');
  let restoreFocus = null;
  let previousInert = false;
  const focusable = (node) => [...node.querySelectorAll('a[href],button:not([disabled]),summary,input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')]
    .filter((element) => element.getClientRects().length && !element.closest('[hidden]'));

  function closeDrawer(restore = true) {
    if (!sidebar || !sidebar.classList.contains('open')) return;
    sidebar.classList.remove('open');
    document.body.classList.remove('cir-drawer-open');
    if (opener) opener.setAttribute('aria-expanded', 'false');
    if (backdrop) backdrop.hidden = true;
    if (workspace) workspace.inert = previousInert;
    sidebar.removeAttribute('role');
    sidebar.removeAttribute('aria-modal');
    if (restore && restoreFocus && restoreFocus.isConnected) restoreFocus.focus();
  }
  function openDrawer() {
    if (!mobile.matches || !sidebar || sidebar.classList.contains('open')) return;
    restoreFocus = document.activeElement;
    previousInert = Boolean(workspace && workspace.inert);
    sidebar.classList.add('open');
    document.body.classList.add('cir-drawer-open');
    if (opener) opener.setAttribute('aria-expanded', 'true');
    if (backdrop) backdrop.hidden = false;
    if (workspace) workspace.inert = true;
    sidebar.setAttribute('role', 'dialog');
    sidebar.setAttribute('aria-modal', 'true');
    const close = sidebar.querySelector('[data-cir-drawer-close]');
    if (close) close.focus();
  }
  if (opener) opener.addEventListener('click', openDrawer);
  document.querySelectorAll('[data-cir-drawer-close]').forEach((button) => button.addEventListener('click', () => closeDrawer()));
  if (sidebar) sidebar.querySelectorAll('a[href]').forEach((link) => {
    const destination = new URL(link.href, location.href);
    if (destination.origin === location.origin && destination.pathname === location.pathname && destination.search === location.search) {
      link.setAttribute('aria-current', 'page');
      const group = link.closest('.cir-nav-group');
      if (group) group.open = true;
    }
    link.addEventListener('click', () => closeDrawer(false));
  });
  mobile.addEventListener('change', () => { if (!mobile.matches) closeDrawer(false); });

  document.querySelectorAll('[data-cir-filter-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const fields = document.getElementById(button.getAttribute('aria-controls'));
      if (!fields) return;
      fields.hidden = !fields.hidden;
      button.setAttribute('aria-expanded', String(!fields.hidden));
    });
  });

  const rowMenus = [...document.querySelectorAll('.cir-row-more')];
  function positionMenu(details) {
    if (!details.open) return;
    const anchor = details.querySelector('summary');
    const menu = details.querySelector('.cir-row-actions-menu');
    if (!anchor || !menu) return;
    const rect = anchor.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > innerHeight) { details.open = false; return; }
    const width = Math.min(220, innerWidth - 24);
    menu.style.width = `${width}px`;
    menu.style.left = `${Math.max(12, Math.min(rect.right - width, innerWidth - width - 12))}px`;
    const height = Math.min(menu.scrollHeight, innerHeight * .7);
    menu.style.top = `${Math.max(12, Math.min(rect.bottom + 8, innerHeight - height - 12))}px`;
  }
  rowMenus.forEach((details) => details.addEventListener('toggle', () => {
    if (details.open) {
      rowMenus.forEach((other) => { if (other !== details) other.open = false; });
      positionMenu(details);
    }
  }));
  window.addEventListener('resize', () => rowMenus.forEach(positionMenu));
  document.addEventListener('scroll', () => rowMenus.forEach(positionMenu), true);
  document.addEventListener('click', (event) => {
    rowMenus.forEach((details) => { if (!details.contains(event.target)) details.open = false; });
    document.querySelectorAll('.cir-account-menu[open]').forEach((details) => { if (!details.contains(event.target)) details.open = false; });
  });
  document.addEventListener('keydown', (event) => {
    if (sidebar && sidebar.classList.contains('open')) {
      if (event.key === 'Escape') { event.preventDefault(); closeDrawer(); }
      if (event.key === 'Tab') {
        const items = focusable(sidebar);
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    } else if (event.key === 'Escape') {
      rowMenus.forEach((details) => { if (details.open) { details.open = false; details.querySelector('summary').focus(); } });
      document.querySelectorAll('.cir-account-menu[open]').forEach((details) => { details.open = false; details.querySelector('summary').focus(); });
    }
  });
})();
