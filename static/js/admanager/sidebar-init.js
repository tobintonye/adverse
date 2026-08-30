// Must run synchronously in <head>, before first paint, to avoid a
// flash of the wrong sidebar width on page load.
if (localStorage.getItem('sidebarCollapsed') === 'true') {
  document.documentElement.classList.add('sidebar-is-collapsed');
}

// Same reasoning for theme: apply before first paint so there's no flash
// of the wrong light/dark mode.
(function () {
  var saved = localStorage.getItem('theme');
  var theme = saved === 'light' || saved === 'dark' ? saved : 'dark';
  document.documentElement.classList.add(theme);
})();