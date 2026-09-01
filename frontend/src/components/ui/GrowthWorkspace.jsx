import { Link, NavLink } from 'react-router-dom';
import { FiAlertCircle, FiArchive, FiClock, FiDatabase, FiPlus, FiUser } from 'react-icons/fi';

const EXTRACTOR_TABS = [
  { to: '/linkedin-extractor', label: 'Extract', icon: FiUser, accent: 'blue' },
  { to: '/linkedin-history', label: 'History', icon: FiClock, accent: 'violet' },
  { to: '/linkedin-needs-review', label: 'Needs review', icon: FiAlertCircle, accent: 'amber' },
  { to: '/linkedin-backups', label: 'Backups', icon: FiArchive, accent: 'emerald' },
];

/* Each tab keeps the accent its content uses elsewhere — amber for review work,
   emerald for backups — so colour becomes a wayfinding cue rather than decoration.
   Class strings stay literal so Tailwind can see them at build time. */
const TAB_ACCENT = {
  blue: {
    idle: 'text-slate-500 hover:bg-primary-50 hover:text-primary-700',
    active: 'bg-white text-primary-700 shadow-sm ring-1 ring-primary-200',
    idleIcon: 'text-primary-400',
    activeIcon: 'text-primary-600',
  },
  violet: {
    idle: 'text-slate-500 hover:bg-violet-50 hover:text-violet-700',
    active: 'bg-white text-violet-700 shadow-sm ring-1 ring-violet-200',
    idleIcon: 'text-violet-400',
    activeIcon: 'text-violet-600',
  },
  amber: {
    idle: 'text-slate-500 hover:bg-amber-50 hover:text-amber-700',
    active: 'bg-white text-amber-700 shadow-sm ring-1 ring-amber-200',
    idleIcon: 'text-amber-400',
    activeIcon: 'text-amber-600',
  },
  emerald: {
    idle: 'text-slate-500 hover:bg-emerald-50 hover:text-emerald-700',
    active: 'bg-white text-emerald-700 shadow-sm ring-1 ring-emerald-200',
    idleIcon: 'text-emerald-400',
    activeIcon: 'text-emerald-600',
  },
};

/** Status vocabulary shared by every extraction surface, so a job that reads
 * "Needs review" on a history card reads the same on its detail page. */
const STATUS_MAP = {
  job: {
    pending: ['Queued', 'neutral'],
    running: ['Extracting', 'info'],
    done: ['Completed', 'success'],
    failed: ['Failed', 'danger'],
    needs_review: ['Needs review', 'warning'],
  },
  verification: {
    VERIFIED: ['Verified', 'success'],
    RESOLVED: ['Resolved', 'info'],
    ALREADY_EXISTS: ['Already exists', 'info'],
    MISMATCH: ['Mismatch', 'warning'],
    REVIEW: ['Needs review', 'warning'],
    NOT_VERIFIED: ['Not verified', 'neutral'],
  },
  extraction: {
    SUCCESS: ['Extracted', 'success'],
    FINAL_FAILED: ['Failed', 'danger'],
    FAILED: ['Failed', 'danger'],
    PROCESSING: ['Processing', 'info'],
    RETRYING: ['Retrying', 'warning'],
    QUEUED: ['Queued', 'neutral'],
    PENDING: ['Pending', 'neutral'],
  },
};

export function statusMeta(status, kind = 'job') {
  const table = STATUS_MAP[kind] || STATUS_MAP.job;
  const key = kind === 'job' ? String(status || '').toLowerCase() : String(status || '').toUpperCase();
  const [label, tone] = table[key] || [status || 'Unknown', 'neutral'];
  return { label, tone };
}

export function StatusBadge({ status, kind = 'job', label, tone, className = '' }) {
  const meta = statusMeta(status, kind);
  return (
    <span className={`badge badge-${tone || meta.tone} ${className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {label || meta.label}
    </span>
  );
}

export function WorkspaceHeader({ eyebrow, title, description, actions, children }) {
  return (
    <header className="workspace-hero animate-rise-in">
      <div className="relative z-10 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          {eyebrow ? <p className="workspace-eyebrow">{eyebrow}</p> : null}
          <h1 className="workspace-title">{title}</h1>
          {description ? <p className="workspace-description">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}

export function ExtractorNav() {
  return (
    <nav className="workspace-tabs" aria-label="Profile extraction workspace">
      {EXTRACTOR_TABS.map(({ to, label, icon: Icon, accent }) => {
        const theme = TAB_ACCENT[accent] || TAB_ACCENT.blue;
        return (
          <NavLink
            key={to}
            to={to}
            end={to === '/linkedin-extractor'}
            className={({ isActive }) => `workspace-tab group ${isActive ? theme.active : theme.idle}`}
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={16}
                  className={`transition-transform duration-200 group-hover:scale-110 ${
                    isActive ? theme.activeIcon : theme.idleIcon
                  }`}
                />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}

/** Renders as a button/link when `onClick`/`to` is supplied so a metric can
 * double as the filter shortcut users instinctively click it for. */
export function MetricCard({ label, value, hint, tone = 'blue', icon: Icon, onClick, to, active = false }) {
  const interactive = Boolean(onClick || to);
  const body = (
    <>
      <div className={`metric-icon metric-icon-${tone} transition-transform duration-200 group-hover:scale-110`}>
        {Icon ? <Icon size={18} /> : <FiDatabase size={18} />}
      </div>
      <div className="min-w-0 text-left">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">{label}</p>
        <p className="mt-1 text-2xl font-bold tracking-tight text-slate-900">{value}</p>
        {hint ? <p className="mt-0.5 text-xs text-slate-500">{hint}</p> : null}
      </div>
    </>
  );

  const className = `metric-card group w-full ${
    interactive ? 'cursor-pointer active:scale-[.99] focus:outline-none focus:ring-4 focus:ring-primary-100' : ''
  } ${active ? 'border-primary-300 ring-2 ring-primary-100' : ''}`;

  if (to) {
    return (
      <Link to={to} className={className} aria-current={active ? 'true' : undefined}>
        {body}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className} aria-pressed={active}>
        {body}
      </button>
    );
  }
  return <div className={className}>{body}</div>;
}

export function EmptyState({ title, description, action, icon: Icon = FiPlus }) {
  return (
    <div className="empty-state">
      <span className="empty-state-icon"><Icon size={22} /></span>
      <h3 className="mt-4 font-semibold text-slate-900">{title}</h3>
      {description ? <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function SkeletonCards({ count = 4, className = 'h-[7.5rem]' }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className={`skeleton rounded-2xl ${className}`} />
      ))}
    </div>
  );
}

export function SkeletonRows({ rows = 6, columns = 5 }) {
  return (
    <div className="divide-y divide-slate-100" aria-hidden="true">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex items-center gap-4 px-4 py-4">
          {Array.from({ length: columns }, (_, c) => (
            <div key={c} className={`skeleton h-4 ${c === 1 ? 'flex-[2]' : 'flex-1'}`} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Screen-reader announcement for async regions that swap in skeletons. */
export function LoadingAnnouncement({ label }) {
  return <span className="sr-only" role="status" aria-live="polite">{label}</span>;
}
