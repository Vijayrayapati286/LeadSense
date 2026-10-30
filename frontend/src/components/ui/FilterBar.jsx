import SurfaceCard from './SurfaceCard';

export function FilterField({ label, children, className = '' }) {
  return (
    <label className={`block min-w-0 ${className}`}>
      <span className="mb-1.5 block text-micro font-bold uppercase tracking-wider text-slate-500">{label}</span>
      {children}
    </label>
  );
}

export default function FilterBar({ children, actions, className = '' }) {
  return (
    <SurfaceCard variant="filter" className={className}>
      <div className="grid gap-3 overflow-x-auto sm:grid-cols-2 xl:grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.25fr)_minmax(10rem,1fr)_minmax(10rem,1fr)_auto] xl:items-end">
        {children}
        {actions ? <div className="flex h-9 shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
    </SurfaceCard>
  );
}
