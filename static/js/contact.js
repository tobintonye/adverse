document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('.form-panel');
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      alert('Prototype only — no data is sent.');
    });
  }
});
