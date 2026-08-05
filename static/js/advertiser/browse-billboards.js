function toggleAdvancedFilters() {
    const panel = document.getElementById('advanced-filters-panel');
    const btn = document.getElementById('toggle-advanced-btn');
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        btn.classList.add('bg-white/10', 'text-white', 'border-white/20');
    } else {
        panel.classList.add('hidden');
        btn.classList.remove('bg-white/10', 'text-white', 'border-white/20');
    }
}