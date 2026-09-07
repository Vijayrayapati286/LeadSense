import { Link } from 'react-router-dom';

export default function PanelHeader({ title, action, to, className = '' }) {
  return (
    <div className={`mb-5 flex items-center justify-between gap-3 ${className}`}>
      <h2 className="text-sm font-bold text-slate-900">{title}</h2>
      {action && to ? (
        <Link
          to={to}
          className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-micro text-slate-500 transition hover:bg-blue-50 hover:text-blue-600"
        >
          {action}
        </Link>
      ) : null}
    </div>
  );
}
