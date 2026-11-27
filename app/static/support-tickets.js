/* Support Tickets UI: client-side pending attachment removal and confirmation. */
'use strict';
(() => {
  for (const form of document.querySelectorAll('form[data-support-compose]')) {
    const input = form.querySelector('[data-support-files]');
    const list = form.querySelector('[data-support-file-list]');
    if (!input || !list || typeof DataTransfer === 'undefined') continue;
    let files = [];
    const refresh = () => {
      list.replaceChildren();
      const transfer = new DataTransfer();
      files.forEach((file, index) => {
        transfer.items.add(file);
        const item = document.createElement('li');
        const name = document.createElement('span');
        name.textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`;
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = 'Rimuovi';
        button.setAttribute('aria-label', 'Rimuovi ' + file.name);
        button.addEventListener('click', () => { files.splice(index, 1); refresh(); });
        item.append(name, button);
        list.append(item);
      });
      input.files = transfer.files;
    };
    input.addEventListener('change', () => {
      const incoming = Array.from(input.files || []);
      if (files.length + incoming.length > 5) {
        alert('Massimo 5 allegati per messaggio.');
        refresh();
        return;
      }
      if (incoming.some(file => file.size > 10 * 1024 * 1024)) {
        alert('Ogni allegato deve essere al massimo di 10 MB.');
        refresh();
        return;
      }
      files.push(...incoming);
      refresh();
    });
  }
  for (const form of document.querySelectorAll('form[data-support-confirm]')) {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.supportConfirm)) event.preventDefault();
    });
  }
})();
