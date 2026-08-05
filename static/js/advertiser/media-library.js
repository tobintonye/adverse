document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('preview-modal');
    if (!modal) return;

    // Open the dialog once htmx has swapped fresh content into it.
    document.body.addEventListener('htmx:afterSwap', function (evt) {
        if (evt.detail.target && evt.detail.target.id === 'preview-modal-content') {
            modal.showModal();
            document.body.style.overflow = 'hidden';
        }
    });

    // Pause any playing video and restore scroll whenever the dialog closes
    // (via the X button, backdrop click, or Esc).
    modal.addEventListener('close', function () {
        document.body.style.overflow = '';
        var video = this.querySelector('video');
        if (video) video.pause();
    });
});