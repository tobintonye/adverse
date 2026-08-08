document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.password-toggle-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const wrapper = btn.closest('.password-field');
      const input = wrapper.querySelector('input');
      const eyeOpen = wrapper.querySelector('.eye-open');
      const eyeClosed = wrapper.querySelector('.eye-closed');
      const isPassword = input.type === 'password';

      input.type = isPassword ? 'text' : 'password';
      eyeOpen.classList.toggle('hidden', isPassword);
      eyeClosed.classList.toggle('hidden', !isPassword);
    });
  });
});