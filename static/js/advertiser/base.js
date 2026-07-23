document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  const mainContent = document.getElementById('main-content');
  const chevron = document.getElementById('collapse-chevron');
  const brand = document.getElementById('sidebar-brand');

  let isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';

  function applyCollapse() {
    const isMobile = window.innerWidth < 768;
    const labels = sidebar.querySelectorAll('.nav-label');
    if (isCollapsed && !isMobile) {
      sidebar.style.width = '4rem';
      sidebar.classList.add('collapsed');
      mainContent.style.marginLeft = '4rem';
      brand.classList.add('hidden');
      labels.forEach(el => el.classList.add('hidden'));
      if (chevron) chevron.style.transform = 'rotate(180deg)';
    } else {
      sidebar.style.width = '14rem';
      sidebar.classList.remove('collapsed');
      if (!isMobile) mainContent.style.marginLeft = '14rem';
      brand.classList.remove('hidden');
      labels.forEach(el => el.classList.remove('hidden'));
      if (chevron) chevron.style.transform = '';
    }
  }

  window.toggleCollapse = function () {
    isCollapsed = !isCollapsed;
    localStorage.setItem('sidebarCollapsed', isCollapsed);
    applyCollapse();
  };

  window.openMobileSidebar = function () {
    sidebar.classList.add('mobile-open');
    backdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  };

  window.closeMobileSidebar = function () {
    sidebar.classList.remove('mobile-open');
    backdrop.classList.add('hidden');
    document.body.style.overflow = '';
  };

  window.toggleUserMenu = function () {
    document.getElementById('user-menu').classList.toggle('hidden');
  };

  // --- Theme toggle ---
  // NOTE: previously flipped DaisyUI's 'dark' <-> 'acid' themes. DaisyUI is
  // removed and there's no light palette defined in the brand Tailwind
  // config, so this button currently has no visible effect. Left in place
  // (not deleted) since it was working functionality — flag if you want a
  // real light theme built, or want the button removed instead.
  function updateThemeIcons(theme) {
    const sunIcon = document.getElementById('theme-icon-dark');
    const moonIcon = document.getElementById('theme-icon-light');
    if (!sunIcon || !moonIcon) return;
    if (theme === 'dark') {
      sunIcon.classList.remove('hidden');
      moonIcon.classList.add('hidden');
    } else {
      sunIcon.classList.add('hidden');
      moonIcon.classList.remove('hidden');
    }
  }

  window.toggleTheme = function () {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcons(next);
  };

  (function () {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    updateThemeIcons(theme);
  })();

  document.addEventListener('click', (e) => {
    const container = document.getElementById('user-menu-container');
    if (container && !container.contains(e.target)) {
      document.getElementById('user-menu').classList.add('hidden');
    }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth >= 768) {
      sidebar.classList.remove('mobile-open');
      backdrop.classList.add('hidden');
      document.body.style.overflow = '';
    }
    applyCollapse();
  });

  applyCollapse();
});
