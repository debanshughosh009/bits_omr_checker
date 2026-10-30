// Sheet designer: refresh the preview image as the numbers change.
(function () {
  const form = document.getElementById("design-form");
  const img = document.getElementById("design-preview");
  const error = document.getElementById("design-error");
  let timer = null;
  let seq = 0;

  async function refresh() {
    const params = new URLSearchParams();
    for (const name of ["title", "questions", "options", "sets", "id_digits"]) {
      params.set(name, form.elements[name].value);
    }
    const mine = ++seq;
    const res = await fetch(`${form.dataset.previewUrl}?${params}`);
    if (mine !== seq) return;     // a newer request is on its way
    if (res.ok) {
      const blob = await res.blob();
      if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
      img.src = URL.createObjectURL(blob);
      img.classList.remove("stale");
      error.classList.add("hidden");
    } else {
      const body = await res.json().catch(() => ({ error: "Preview failed" }));
      error.textContent = body.error;
      error.classList.remove("hidden");
      img.classList.add("stale");
    }
  }

  form.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(refresh, 350);
  });
  refresh();
})();
