import { createContext, useContext, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronRight, BadgeCheck } from 'lucide-react';
import { Toaster } from '@/components/ui/sonner';
import { ExamsContext, useExamList, useRoute } from '@/lib/api';
import ImportDialog from '@/components/ImportDialog';
import Dashboard from '@/pages/Dashboard';
import Designer from '@/pages/Designer';
import Exam from '@/pages/Exam';

// Pages put their title and buttons into the sticky top bar through these
const HeaderSlots = createContext({});

export function PageHeader({ title, badge, actions }) {
  const { crumb, actions: right } = useContext(HeaderSlots);
  useEffect(() => {
    document.title = title ? `${title} · OMR Checker` : 'OMR Checker';
    return () => { document.title = 'OMR Checker'; };
  }, [title]);
  return (
    <>
      {crumb &&
        title &&
        createPortal(
          <>
            <ChevronRight className='size-4 shrink-0 text-muted-foreground' />
            <span className='truncate font-medium'>{title}</span>
            {badge}
          </>,
          crumb,
        )}
      {right && actions && createPortal(actions, right)}
    </>
  );
}

export default function App() {
  const list = useExamList();
  const route = useRoute();
  const [importing, setImporting] = useState(false);
  const [crumb, setCrumb] = useState(null);
  const [actions, setActions] = useState(null);
  const [version, setVersion] = useState(null);
  useEffect(() => {
    fetch('/api/version').then((r) => r.json()).then((v) => setVersion(v.version), () => {});
    // the packaged app's server stops a few minutes after the last open window stops checking in
    const ping = setInterval(() => fetch('/api/ping').catch(() => {}), 20000);
    return () => clearInterval(ping);
  }, []);

  return (
    <ExamsContext.Provider
      value={{ ...list, importSheet: () => setImporting(true) }}
    >
      <HeaderSlots.Provider value={{ crumb, actions }}>
        <div className='flex min-h-svh flex-col'>
          <header className='sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur md:px-6 print:hidden'>
            <nav className='flex min-w-0 flex-1 items-center gap-2 text-sm'>
              <a
                href='#/'
                className='flex shrink-0 items-center gap-2 font-semibold'
              >
                <span className='grid size-7 place-items-center rounded-md bg-primary text-primary-foreground'>
                  <BadgeCheck className='size-4' />
                </span>
                <span
                  className={
                    route.page === 'dashboard' ? '' : 'hidden sm:inline'
                  }
                >
                  OMR Checker
                </span>
              </a>
              <div ref={setCrumb} className='flex min-w-0 items-center gap-2' />
            </nav>
            <div
              ref={setActions}
              className='flex shrink-0 items-center gap-2'
            />
          </header>
          {list.error ? (
            <p className='m-auto max-w-md p-8 text-center text-sm text-muted-foreground'>
              Cannot reach the local server ({list.error.message}). Start it
              with “Start OMR” in the project folder.
            </p>
          ) : route.page === 'design' ? (
            <Designer key={route.id ?? 'new'} id={route.id} />
          ) : route.page === 'sheets' ? (
            <Exam key={route.id} id={route.id} />
          ) : (
            <Dashboard />
          )}
          <footer className='mt-auto border-t px-4 py-3 text-center text-xs text-muted-foreground print:hidden'>
            Developed by Debanshu Ghosh and Aravind Sathesh{version && ` · v${version}`}
          </footer>
        </div>
        <ImportDialog open={importing} onClose={() => setImporting(false)} />
        <Toaster position='bottom-right' />
      </HeaderSlots.Provider>
    </ExamsContext.Provider>
  );
}
