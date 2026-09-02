export default function PageHeader({ eyebrow, title, subtitle, actions, className = '' }) {
  return (
    <header className={`flex flex-wrap items-center justify-between gap-4 ${className}`}>
      <div className="min-w-0">
        {eyebrow ? <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-primary-600">{eyebrow}</p> : null}
        <h1 className="mt-0.5 text-2xl font-bold tracking-tight text-slate-950">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-2xl text-sm text-slate-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
