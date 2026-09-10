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

// Delete confirmation dialog — opened by the trash button on pending/rejected
// media cards (see media_grid.html). Submits the matching hidden delete form
// once the person confirms, instead of a native window.confirm().
var AdVerseDeleteConfirm = (function () {
    var modal, message, submitBtn, pendingFormId;

    document.addEventListener('DOMContentLoaded', function () {
        modal = document.getElementById('delete-confirm-modal');
        message = document.getElementById('delete-confirm-message');
        submitBtn = document.getElementById('delete-confirm-submit');
        if (!modal || !submitBtn) return;

        submitBtn.addEventListener('click', function () {
            var form = pendingFormId && document.getElementById(pendingFormId);
            modal.close();
            if (form) form.submit();
        });
    });

    function open(formId, title) {
        pendingFormId = formId;
        if (message) {
            message.textContent = '"' + title + '" will be permanently deleted. This cannot be undone.';
        }
        if (modal) modal.showModal();
    }

    return { open: open };
}());