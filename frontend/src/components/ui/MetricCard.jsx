import { Link } from 'react-router-dom';
import { METRIC_TONES } from '../../design-tokens';

export default function MetricCard({
  label,
  value,
  note,
  icon: Icon,
  tone = 'blue',
  index = 0,
  to,
  onClick,
  active = false,
  className = '',
}) {
  const interactive = Boolean(to || onClick);
  const toneClass = METRIC_TONES[tone] || METRIC_TONES.blue;

  const body = (
    <div className="flex min-h-[64px] items-center justify-between gap-4">
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
        <p className="mt-1 text-2xl font-bold tracking-tight text-slate-950">{value ?? 0}</p>
        {note ? <p className="mt-0.5 truncate text-xs font-medium text-slate-500">{note}</p> : null}
      </div>
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${toneClass}`}>
        {Icon ? <Icon size={19} /> : null}
      </div>
    </div>
  );

  const classes = `stagger-item min-w-0 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-card transition duration-200 ${
    interactive ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-card-hover focus:outline-none focus:ring-4 focus:ring-primary-100 active:scale-[.99]' : 'hover:-translate-y-0.5 hover:shadow-card-hover'
  } ${active ? 'border-primary-300 ring-2 ring-primary-100' : ''} ${className}`;

  if (to) {
    return (
      <Link to={to} className={classes} style={{ '--item-index': index }} aria-current={active ? 'true' : undefined}>
        {body}
      </Link>
    );
  }

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={`${classes} text-left`} style={{ '--item-index': index }} aria-pressed={active}>
        {body}
      </button>
    );
  }

  return (
    <div className={classes} style={{ '--item-index': index }}>
      {body}
    </div>
  );
}
