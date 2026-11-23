/* Presentation navigation only; workflow activation remains the audited app.js path. */
(function () {
  'use strict';
  function init() {
    if (!document.body.classList.contains('cir-modern')) return;
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
