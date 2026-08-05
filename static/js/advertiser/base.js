(function () {
  const sidebar = document.getElementById('sidebar');
  const mainContent = document.getElementById('main-content');
  const chevron = document.getElementById('collapse-chevron');
  const brand = document.getElementById('sidebar-brand');
  let isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
  function applyCollapse() {
    const isMobile = window.innerWidth < 768;
    if (isMobile) return; // sidebar is hidden on mobile, nothing to collapse
    const labels = sidebar.querySelectorAll('.nav-label');
    if (isCollapsed) {
      sidebar.style.width = '4rem';
      sidebar.classList.add('collapsed');
      mainContent.style.marginLeft = '4rem';
      brand.classList.add('hidden');
      labels.forEach(el => el.classList.add('hidden'));
      if (chevron) chevron.style.transform = 'rotate(180deg)';
    } else {
      sidebar.style.width = '14rem';
      sidebar.classList.remove('collapsed');
      mainContent.style.marginLeft = '14rem';
      brand.classList.remove('hidden');
      labels.forEach(el => el.classList.remove('hidden'));
      if (chevron) chevron.style.transform = '';
    }
  }
  function toggleCollapse() {
    isCollapsed = !isCollapsed;
    localStorage.setItem('sidebarCollapsed', isCollapsed);
    applyCollapse();
  }
  function toggleUserMenu() {
    document.getElementById('user-menu').classList.toggle('hidden');
  }
  document.addEventListener('click', (e) => {
    const container = document.getElementById('user-menu-container');
    if (container && !container.contains(e.target)) {
      document.getElementById('user-menu').classList.add('hidden');
    }
  });
  function toggleMoreSheet() {
    document.getElementById('more-sheet').classList.toggle('hidden');
    document.getElementById('more-sheet-backdrop').classList.toggle('hidden');
  }
  window.addEventListener('resize', applyCollapse);
  window.toggleCollapse = toggleCollapse;
  window.toggleUserMenu = toggleUserMenu;
  window.toggleMoreSheet = toggleMoreSheet;
  applyCollapse();
})();