export default function PageHeader({ title, subtitle, actions, className = '' }) {
  return (
    <header className={`flex flex-wrap items-center justify-between gap-4 ${className}`}>
      <div className="min-w-0">
        <h1 className="text-display font-bold tracking-tight text-slate-950">{title}</h1>
        {subtitle ? <p className="mt-1 text-body-sm text-slate-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
