export default function StatBlock({ label, value, className = '' }) {
  return (
    <div className={`rounded-xl bg-slate-50 py-3 text-center ${className}`}>
      <div className="text-lg font-bold text-slate-950">{value}</div>
      <div className="mt-0.5 text-micro font-semibold uppercase tracking-wider text-slate-400">{label}</div>
    </div>
  );
}
