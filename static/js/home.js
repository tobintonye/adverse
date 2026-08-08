// Fallback shown in place of a missing media file — replace this by
// simply adding the real image/video file at the path shown in the label.
function makePlaceholder(label) {
  const box = document.createElement('div');
  box.className = 'media-placeholder';
  box.innerHTML = `<span>DROP FILE HERE<br>${label}</span>`;
  return box;
}

document.addEventListener('DOMContentLoaded', () => {
  // 3D device tilt + glow tracking
  const mesh = document.getElementById('deviceMesh');
  const shimmer = document.getElementById('deviceShimmer');
  let targetX = 0, targetY = 0, curX = 0, curY = 0, mouseActive = false, idleTimer;
  const startTime = Date.now();
  const lerp = 0.08;

  window.addEventListener('mousemove', (e) => {
    mouseActive = true;
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { mouseActive = false; }, 3000);

    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = (e.clientY / window.innerHeight) * 2 - 1;
    targetY = nx * 18;
    targetX = -ny * 14;

    if (mesh) {
      const rect = mesh.getBoundingClientRect();
      const gx = ((e.clientX - rect.left) / rect.width) * 100;
      const gy = ((e.clientY - rect.top) / rect.height) * 100;
      mesh.style.setProperty('--mx', gx + '%');
      mesh.style.setProperty('--my', gy + '%');
      if (shimmer) shimmer.style.backgroundPosition = gx + '% ' + gy + '%';
    }
  });

  function tick() {
    if (!mouseActive) {
      const t = (Date.now() - startTime) / 1000;
      targetY = Math.sin(t * 0.4) * 12;
      targetX = Math.cos(t * 0.25) * 4;
    }
    curX += (targetX - curX) * lerp;
    curY += (targetY - curY) * lerp;
    if (mesh) mesh.style.transform = `rotateX(${curX}deg) rotateY(${curY}deg)`;
    requestAnimationFrame(tick);
  }
  if (mesh && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    tick();
  }

  // Cycle device screen "slides" to simulate real playback
  const slides = document.querySelectorAll('.device-slide');
  const proofTimeEl = document.getElementById('proofTime');
  let slideIndex = 0;
  if (slides.length) {
    setInterval(() => {
      slides[slideIndex].classList.remove('active');
      slideIndex = (slideIndex + 1) % slides.length;
      if (slideIndex === 4 && proofTimeEl) {
        proofTimeEl.textContent = new Date().toLocaleTimeString('en-GB');
      }
      slides[slideIndex].classList.add('active');
    }, 3200);
  }
});
