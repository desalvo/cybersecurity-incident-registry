/* Modern AlBot UI. The API receives the current question, never page data/history. */
(function () {
  'use strict';

  function init() {
    const widget = document.getElementById('cir-albot');
    const panel = document.getElementById('cir-albot-panel');
    const shell = document.getElementById('cir-page-shell');
    if (!widget || !panel || !shell) return;
    const strings = JSON.parse(document.getElementById('cir-albot-strings').textContent);
    const question = document.getElementById('cir-albot-question');
    const form = document.getElementById('cir-albot-form');
    const send = document.getElementById('cir-albot-send');
    const reset = document.getElementById('cir-albot-new-question');
    const closeButton = document.getElementById('cir-albot-close');
    const expand = document.getElementById('cir-albot-expand');
    const back = document.getElementById('cir-albot-back');
    const messages = document.getElementById('cir-albot-messages');
    const scroller = document.getElementById('cir-albot-scroll');
    const status = document.getElementById('cir-albot-status');
    const contextToggle = document.getElementById('cir-albot-context-toggle');
    const context = document.getElementById('cir-albot-context-details');
    const triggers = Array.from(document.querySelectorAll('[data-cir-albot-open]'));
    const wide = window.matchMedia('(min-width: 1800px)');
    const tenantId = widget.dataset.tenantId;
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const ask = new URL(widget.dataset.askUrl, location.href);
    if (ask.origin !== location.origin) return;
    let open = false;
    let expanded = false;
    let focused = false;
    let returnFocus = null;
    let previousInert = false;
    let previousAriaHidden = null;
    let savedScroll = null;
    let controller = null;
    let generation = 0;
    let busy = false;
    let invalid = false;

    function safeLink(target) {
      if (!target || /[\s\\\u0000-\u001f\u007f]/.test(target) || target.startsWith('//')) return null;
      if (/^[a-z][a-z0-9+.-]*:/i.test(target) && !/^https?:\/\//i.test(target)) return null;
      try {
        const url = new URL(target, location.href);
        if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
        return url;
      } catch (_) { return null; }
    }

    // All text is inserted through textContent/createTextNode. Model HTML is never trusted.
    function inline(text, depth) {
      const fragment = document.createDocumentFragment();
      if (depth > 4) { fragment.appendChild(document.createTextNode(text)); return fragment; }
      const token = /`([^`\n]+)`|\{button:([^|{}\n]{1,80})\|([^\s{}<>"']{1,300})\}|\{(color|size):([^{}\n]+)\}([\s\S]+?)\{\/\4\}|\*\*\*([^*\n]+)\*\*\*|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|\[([^\]\n]+)\]\(([^\s)]+)\)|(https?:\/\/[^\s<>]+)/g;
      let previous = 0;
      let match;
      while ((match = token.exec(text)) !== null) {
        if (match.index > previous) fragment.appendChild(document.createTextNode(text.slice(previous, match.index)));
        let node;
        if (match[1] !== undefined) {
          node = document.createElement('code'); node.textContent = match[1];
        } else if (match[2] !== undefined || match[10] !== undefined || match[12] !== undefined) {
          const label = match[2] || match[10] || match[12];
          const target = (match[3] || match[11] || match[12]).trim();
          const url = safeLink(target);
          if (url) {
            node = document.createElement('a'); node.href = url.href;
            if (match[2]) node.className = 'cir-albot-markdown-button';
            if (url.origin !== location.origin) { node.target = '_blank'; node.rel = 'noopener noreferrer'; }
            node.appendChild(inline(label, depth + 1));
          } else { node = document.createTextNode(label); }
        } else if (match[4] !== undefined) {
          node = document.createElement('span');
          const type = match[4];
          const value = match[5].trim().toLowerCase();
          const validColor = typeof window.isAllowedSafeMarkdownColor === 'function' && window.isAllowedSafeMarkdownColor(value);
          const validSize = typeof window.isAllowedSafeMarkdownSize === 'function' && window.isAllowedSafeMarkdownSize(value);
          if (type === 'color' && validColor) node.style.color = value;
          if (type === 'size' && validSize) node.style.fontSize = value;
          node.appendChild(inline(match[6], depth + 1));
        } else if (match[7] !== undefined) {
          node = document.createElement('strong');
          const emphasis = document.createElement('em'); emphasis.appendChild(inline(match[7], depth + 1)); node.appendChild(emphasis);
        } else {
          node = document.createElement(match[8] !== undefined ? 'strong' : 'em');
          node.appendChild(inline(match[8] || match[9], depth + 1));
        }
        fragment.appendChild(node);
        previous = token.lastIndex;
      }
      if (previous < text.length) fragment.appendChild(document.createTextNode(text.slice(previous)));
      return fragment;
    }

    function markdown(value) {
      const fragment = document.createDocumentFragment();
      const lines = String(value || '').replace(/\r\n?/g, '\n').split('\n');
      let paragraph = [];
      let list = null;
      let code = null;
      function flush() {
        if (paragraph.length) { const p = document.createElement('p'); p.appendChild(inline(paragraph.join(' '), 0)); fragment.appendChild(p); paragraph = []; }
      }
      lines.forEach(function (line) {
        if (/^\s*```/.test(line)) {
          flush(); list = null;
          if (code !== null) { const pre = document.createElement('pre'); const c = document.createElement('code'); c.textContent = code.join('\n'); pre.appendChild(c); fragment.appendChild(pre); code = null; }
          else code = [];
          return;
        }
        if (code !== null) { code.push(line); return; }
        const text = line.trim();
        if (!text) { flush(); list = null; return; }
        const heading = /^(#{1,6})\s+(.+)$/.exec(text);
        if (heading) { flush(); list = null; const h = document.createElement('h' + Math.min(6, heading[1].length + 2)); h.appendChild(inline(heading[2], 0)); fragment.appendChild(h); return; }
        const bullet = /^([-*]|\d+\.)\s+(.+)$/.exec(text);
        if (bullet) {
          flush(); const tag = /^\d/.test(bullet[1]) ? 'OL' : 'UL';
          if (!list || list.tagName !== tag) { list = document.createElement(tag.toLowerCase()); fragment.appendChild(list); }
          const li = document.createElement('li'); li.appendChild(inline(bullet[2], 0)); list.appendChild(li); return;
        }
        list = null; paragraph.push(text);
      });
      flush();
      if (code !== null) { const pre = document.createElement('pre'); pre.textContent = code.join('\n'); fragment.appendChild(pre); }
      return fragment;
    }

    function addMessage(text, type) {
      const article = document.createElement('article');
      article.className = 'cir-albot-message ' + type;
      const label = document.createElement('strong'); label.className = 'cir-albot-message-label'; label.textContent = type === 'user' ? strings.you : 'AlBot';
      article.appendChild(label);
      if (type === 'bot') article.appendChild(markdown(text));
      else { const p = document.createElement('p'); p.textContent = text; article.appendChild(p); }
      messages.appendChild(article);
      scroller.scrollTop = scroller.scrollHeight;
      return article;
    }

    function controls() {
      send.disabled = busy || invalid || !question.value.trim();
      question.disabled = invalid;
      reset.disabled = invalid;
      form.setAttribute('aria-busy', busy ? 'true' : 'false');
      widget.querySelectorAll('[data-cir-albot-question]').forEach(function (button) { button.disabled = invalid; });
    }

    function clearConversation() {
      generation += 1;
      if (controller) controller.abort();
      controller = null; busy = false; question.value = ''; status.textContent = '';
      messages.replaceChildren(); addMessage(strings.welcome, 'bot'); controls();
    }

    function restorePage() {
      if (!focused) return;
      focused = false;
      shell.inert = previousInert;
      if (previousAriaHidden === null) shell.removeAttribute('aria-hidden');
      else shell.setAttribute('aria-hidden', previousAriaHidden);
      document.body.classList.remove('cir-albot-focused');
      if (savedScroll) { window.scrollTo(savedScroll.x, savedScroll.y); savedScroll = null; }
    }

    function viewport() {
      if (!open) return;
      const view = window.visualViewport;
      panel.style.setProperty('--cir-albot-height', (view ? view.height : window.innerHeight) + 'px');
      panel.style.setProperty('--cir-albot-top', (focused && view ? view.offsetTop : 0) + 'px');
    }

    function layout() {
      const docked = open && wide.matches && !expanded;
      document.body.classList.toggle('cir-albot-docked', docked);
      if (open && !docked && !focused) {
        previousInert = shell.inert;
        previousAriaHidden = shell.getAttribute('aria-hidden');
        savedScroll = {x: window.scrollX, y: window.scrollY};
        // Move focus outside the workspace before making it unavailable.
        closeButton.focus({preventScroll: true});
        shell.inert = true; shell.setAttribute('aria-hidden', 'true');
        focused = true; document.body.classList.add('cir-albot-focused');
      } else if (!open || docked) restorePage();
      panel.setAttribute('role', focused ? 'dialog' : 'complementary');
      if (focused) panel.setAttribute('aria-modal', 'true'); else panel.removeAttribute('aria-modal');
      expand.setAttribute('aria-pressed', expanded ? 'true' : 'false');
      expand.setAttribute('aria-label', expanded ? strings.restore : strings.expand);
      expand.title = expanded ? strings.restore : strings.expand;
      // Expanding a narrow view would have no effect; keep this control for wide desktop.
      expand.hidden = !wide.matches;
      viewport();
    }

    function setOpen(value, opener) {
      if (value && !open) returnFocus = opener || document.activeElement;
      open = value; panel.hidden = !open;
      triggers.forEach(function (trigger) { trigger.setAttribute('aria-expanded', open ? 'true' : 'false'); });
      if (!open) expanded = false;
      layout();
      if (open) { if (!invalid) question.focus({preventScroll: true}); else closeButton.focus({preventScroll: true}); }
      else if (returnFocus && returnFocus.isConnected && !returnFocus.disabled) returnFocus.focus({preventScroll: true});
    }

    triggers.forEach(function (trigger) { trigger.addEventListener('click', function () { setOpen(!open, trigger); }); });
    closeButton.addEventListener('click', function () { setOpen(false); });
    back.addEventListener('click', function () { setOpen(false); });
    expand.addEventListener('click', function () { expanded = !expanded; layout(); closeButton.focus({preventScroll: true}); });
    contextToggle.addEventListener('click', function () { context.hidden = !context.hidden; contextToggle.setAttribute('aria-expanded', context.hidden ? 'false' : 'true'); });
    reset.addEventListener('click', function () { clearConversation(); if (!invalid) question.focus(); });
    question.addEventListener('input', controls);
    widget.querySelectorAll('[data-cir-albot-question]').forEach(function (button) {
      button.addEventListener('click', function () { if (invalid) return; question.value = button.dataset.cirAlbotQuestion; controls(); question.focus(); });
    });
    document.addEventListener('keydown', function (event) {
      if (!open) return;
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return; }
      if (event.key !== 'Tab' || !focused) return;
      const focusable = Array.from(panel.querySelectorAll('button:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')).filter(function (el) { return !el.closest('[hidden]') && el.getClientRects().length; });
      if (!focusable.length) { event.preventDefault(); return; }
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    }, true);

    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      const value = question.value.trim();
      if (!value || busy || invalid) return;
      addMessage(value, 'user'); question.value = ''; busy = true; controls(); status.textContent = strings.pending;
      controller = new AbortController();
      const requestController = controller;
      const requestGeneration = generation;
      let timedOut = false;
      const timer = window.setTimeout(function () { timedOut = true; requestController.abort(); }, 120000);
      try {
        const response = await fetch(ask.href, {
          method: 'POST', credentials: 'same-origin', redirect: 'error',
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrf, 'X-CIR-Tenant-ID': tenantId},
          body: JSON.stringify({question: value}), signal: requestController.signal
        });
        if (requestGeneration !== generation) return;
        if (response.status === 403 || response.status === 409 || response.status === 401) {
          invalid = true; clearConversation(); messages.replaceChildren(); addMessage(strings.invalid, 'error'); return;
        }
        if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error(strings.invalidResponse);
        const data = await response.json();
        if (requestGeneration !== generation) return;
        if (!response.ok || data.ok !== true || typeof data.answer !== 'string') {
          addMessage(typeof data.error === 'string' ? data.error : strings.invalidResponse, 'error');
        } else addMessage(data.answer, 'bot');
      } catch (error) {
        if (requestGeneration === generation && (error.name !== 'AbortError' || timedOut)) addMessage(timedOut ? strings.timeout : strings.error, 'error');
      } finally {
        window.clearTimeout(timer);
        if (requestGeneration === generation) { busy = false; controller = null; status.textContent = ''; controls(); }
      }
    });

    // A tenant switch or navigation must never retain an old tenant's transcript.
    document.addEventListener('submit', function (event) {
      if (event.target.matches('[data-tenant-switcher-form]')) { clearConversation(); setOpen(false); }
    }, true);
    window.addEventListener('pagehide', function () { clearConversation(); setOpen(false); });
    window.addEventListener('pageshow', function (event) { if (event.persisted) { clearConversation(); setOpen(false); } });
    window.addEventListener('resize', layout);
    if (wide.addEventListener) wide.addEventListener('change', layout);
    if (window.visualViewport) { window.visualViewport.addEventListener('resize', viewport); window.visualViewport.addEventListener('scroll', viewport); }
    controls();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());
