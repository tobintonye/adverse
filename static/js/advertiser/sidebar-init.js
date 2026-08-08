// Must run synchronously in <head>, before first paint, to avoid a
// flash of the wrong sidebar width on page load.
if (localStorage.getItem('sidebarCollapsed') === 'true') {
  document.documentElement.classList.add('sidebar-is-collapsed');
}