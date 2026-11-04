// Talks to app/server.py. Exams live in its SQLite database; this file only fetches.
import { createContext, useContext, useEffect, useState, useCallback } from "react";

export async function api(path, opts = {}) {
  const res = await fetch(`/api/${path}`, {
    ...opts,
    body: opts.body && !(opts.body instanceof Blob) ? JSON.stringify(opts.body) : opts.body,
  });
  const data = await res.json().catch(() => ({ error: `${res.status} ${res.statusText}` }));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

// The exam list, shared by the sidebar, the dashboard and the exam page
export const ExamsContext = createContext(null);
export const useExams = () => useContext(ExamsContext);

export function useExamList() {
  const [exams, setExams] = useState(null);
  const [error, setError] = useState(null);
  const reload = useCallback(() => api("exams").then(setExams, setError), []);
  useEffect(() => { reload(); }, [reload]);
  return { exams, error, reload };
}

// Hash routes: #/, #/designer, #/exams/3
export function useRoute() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const on = () => setHash(location.hash);
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  const parts = hash.replace(/^#\/?/, "").split("/");
  return { page: parts[0] || "dashboard", id: parts[1] };
}

export const go = (path) => { location.hash = path; };

export function download(name, text, type = "application/json") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
