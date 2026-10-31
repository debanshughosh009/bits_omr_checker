// Exam page: drag-and-drop upload with progress, job polling, results table filters.
(function () {
  const form = document.getElementById("upload-form");
  const input = document.getElementById("scan-input");
  const drop = document.getElementById("dropzone");
  const btn = document.getElementById("upload-btn");
  const fileList = document.getElementById("file-list");
  const box = document.getElementById("job-box");
  const bar = document.getElementById("job-bar");
  const msg = document.getElementById("job-msg");
  const unread = document.getElementById("job-unread");
  const logWrap = document.getElementById("job-log-wrap");
  const log = document.getElementById("job-log");
  let files = [];

  function setFiles(list) {
    files = [...list];
    btn.disabled = files.length === 0;
    const mb = files.reduce((n, f) => n + f.size, 0) / 1e6;
    fileList.textContent = files.length
      ? `${files.length} file(s) selected, ${mb.toFixed(1)} MB` : "";
  }

  input.addEventListener("change", () => setFiles(input.files));
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => setFiles(e.dataTransfer.files));

  function showJob(text, pct, state) {
    box.classList.remove("hidden", "failed", "done");
    if (state) box.classList.add(state);
    msg.textContent = text;
    bar.style.width = pct + "%";
    bar.classList.toggle("indeterminate", pct === null);
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!files.length) return;
    const fd = new FormData();
    files.forEach((f) => fd.append("scans", f, f.name));
    btn.disabled = true;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.dataset.url);
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) showJob(`Uploading... ${Math.round(100 * ev.loaded / ev.total)}%`, 100 * ev.loaded / ev.total);
    };
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (_) { body = { ok: false, error: `Upload failed (${xhr.status})` }; }
      if (!body.ok) { showJob(body.error, 100, "failed"); btn.disabled = false; return; }
      poll(body.job.id);
    };
    xhr.onerror = () => { showJob("Upload failed: network error", 100, "failed"); btn.disabled = false; };
    xhr.send(fd);
  });

  async function poll(jobId) {
    const res = await fetch(`/jobs/${jobId}`);
    if (!res.ok) { showJob("Lost track of the job. Reload the page.", 100, "failed"); return; }
    const job = await res.json();
    if (job.status === "queued" || job.status === "running") {
      showJob(job.message, null);
      setTimeout(() => poll(jobId), 1500);
      return;
    }
    showJob(job.message, 100, job.status === "done" ? "done" : "failed");
    unread.innerHTML = (job.unread || []).map((f) => `<li>Could not read: ${f}</li>`).join("");
    if (job.log) { log.textContent = job.log; logWrap.classList.remove("hidden"); }
    if (job.status === "done" && !(job.unread || []).length) {
      msg.textContent += " Refreshing...";
      setTimeout(() => location.reload(), 1200);
    } else {
      const a = document.createElement("a");
      a.href = location.pathname + "#results"; a.textContent = " Show results";
      a.onclick = () => location.reload();
      msg.appendChild(a);
    }
  }

  if (form.dataset.activeJob) poll(form.dataset.activeJob);

  // Results table filters
  const table = document.getElementById("results-table");
  if (table) {
    const search = document.getElementById("table-search");
    const flagged = document.getElementById("only-flagged");
    const perQ = document.getElementById("show-questions");
    const filter = () => {
      const term = search.value.trim().toLowerCase();
      for (const row of table.tBodies[0].rows) {
        const hide = (flagged.checked && !row.classList.contains("flagged")) ||
          (term && !row.textContent.toLowerCase().includes(term));
        row.classList.toggle("hidden", hide);
      }
    };
    search.addEventListener("input", filter);
    flagged.addEventListener("change", filter);
    if (perQ) perQ.addEventListener("change", () => table.classList.toggle("show-q", perQ.checked));
  }
})();
