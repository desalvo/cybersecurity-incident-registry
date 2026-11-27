// CIR RC100: local-only visualization. No remote charting services or fonts.
(() => {
  const checkbox = document.querySelector('#cir-export-encrypt');
  const label = document.querySelector('#cir-export-password-label');
  const password = document.querySelector('#cir-export-password');
  if (checkbox && label && password) {
    const update = () => {
      label.hidden = !checkbox.checked;
      password.required = checkbox.checked;
      if (!checkbox.checked) password.value = '';
    };
    checkbox.addEventListener('change', update);
    update();
  }
  // Presentation effects only: values and ordering are server-rendered, preventing
  // any client-side access beyond the authorized (super admin) response.
  const scene = document.querySelector('#cir-bubble-scene');
  if (scene) {
    const items = scene.querySelectorAll('.cir-bubble');
    items.forEach((bubble, i) => {
      const weight = Number.parseFloat(bubble.dataset.bubbleWeight) || 0;
      const diameter = Math.round(80 + 70 * Math.sqrt(Math.max(0, weight)));
      bubble.style.width = diameter + 'px';
      bubble.style.height = diameter + 'px';
      bubble.style.setProperty('--bubble-hue', String((i * 47 + 198) % 360));
    });
  }
})();
