// Desktop window helpers (app/desktop.py exposes window.pywebview.api).
// Links that would open a new tab open in a second app window instead, and
// "Open folder" buttons show a layout's or exam's files in the file manager.
(function () {
  function ready() {
    const api = window.pywebview && window.pywebview.api;
    if (!api) return;
    document.querySelectorAll(".desktop-only").forEach((el) => el.classList.remove("hidden"));

    document.addEventListener("click", (e) => {
      const a = e.target.closest('a[target="_blank"]');
      if (!a || a.origin !== location.origin) return;
      e.preventDefault();
      api.open_window(a.href, a.textContent.trim() || document.title);
    });

    document.querySelectorAll("[data-open-folder]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [kind, id] = btn.dataset.openFolder.split(":");
        api.open_folder(kind, id);
      });
    });
  }

  if (window.pywebview && window.pywebview.api) ready();
  else window.addEventListener("pywebviewready", ready);
})();
