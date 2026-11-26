/* Presentation navigation only; workflow activation remains the audited app.js path. */
(function () {
  'use strict';
  function initWorkflowConnectors() {
    // Position arrows based on rendered rows, not on an assumed number of columns.
    // ResizeObserver also covers incident panels whose available width changes.
    document.querySelectorAll('.workflow-steps-ordered').forEach(function (grid) {
      const cards = Array.from(grid.querySelectorAll('.workflow-step-card'));
      if (!cards.length) return;
      let pending = false;
      function layout() {
        pending = false;
        cards.forEach(function (card) {
          card.classList.remove('workflow-connector-right', 'workflow-connector-down', 'workflow-connector-wrap');
        });
        if (grid.getClientRects().length === 0) return;
        cards.slice(0, -1).forEach(function (card, index) {
          const next = cards[index + 1];
          const currentBounds = card.getBoundingClientRect();
          const nextBounds = next.getBoundingClientRect();
          if (Math.abs(currentBounds.top - nextBounds.top) <= 2) {
            card.classList.add('workflow-connector-right');
          } else if (Math.abs(currentBounds.left - nextBounds.left) <= 2) {
            card.classList.add('workflow-connector-down');
          } else {
            // The sequence wraps to the first card in the following row.
            card.classList.add('workflow-connector-wrap');
          }
        });
      }
      function requestLayout() {
        if (pending) return;
        pending = true;
        window.requestAnimationFrame(layout);
      }
      requestLayout();
      window.addEventListener('resize', requestLayout);
      const details = grid.closest('details');
      if (details) details.addEventListener('toggle', requestLayout);
      if (window.ResizeObserver) {
        const observer = new ResizeObserver(requestLayout);
        observer.observe(grid);
      }
    });
  }
  function init() {
    if (!document.body.classList.contains('cir-modern')) return;
    initWorkflowConnectors();
    const navigation = document.getElementById('cir-incident-navigation');
    if (!navigation) return;
    const links = Array.from(navigation.querySelectorAll('a[data-cir-section-link]'));
    function mark(id) {
      links.forEach(function (link) {
        if (link.getAttribute('href') === '#' + id) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    }
    document.querySelectorAll('a[data-cir-section-link]').forEach(function (link) {
      link.addEventListener('click', function (event) {
        const id = (link.getAttribute('href') || '').replace(/^#/, '');
        const target = document.getElementById(id);
        if (!target) return;
        event.preventDefault();
        if (target.tagName === 'DETAILS') target.open = true;
        const menu = link.closest('.cir-incident-more');
        if (menu) menu.open = false;
        history.replaceState(history.state, '', '#' + id);
        mark(id);
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        target.scrollIntoView({block: 'start', behavior: reducedMotion ? 'auto' : 'smooth'});
        const summary = target.querySelector('summary');
        if (summary) summary.focus({preventScroll: true});
      });
    });
    window.addEventListener('hashchange', function () { mark(location.hash.slice(1)); });
    if (location.hash) mark(location.hash.slice(1));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());
