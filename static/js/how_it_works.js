function showTrack(which) {
  document.getElementById('advertisers').classList.toggle('active', which === 'advertisers');
  document.getElementById('owners').classList.toggle('active', which === 'owners');
  document.getElementById('tab-advertisers').classList.toggle('active', which === 'advertisers');
  document.getElementById('tab-owners').classList.toggle('active', which === 'owners');
  document.getElementById('cta-heading').textContent = which === 'advertisers'
    ? 'Ready to launch your first campaign?' : 'Ready to start earning from your screens?';
  document.getElementById('cta-btn').textContent = which === 'advertisers'
    ? 'Join as an advertiser' : 'Register your screens';
}

document.addEventListener('DOMContentLoaded', () => {
  // deep-link support: #advertisers / #screen-owners
  if (location.hash === '#screen-owners') {
    showTrack('owners');
  }
});
