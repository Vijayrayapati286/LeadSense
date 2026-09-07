export default function SegmentedControl({ options, value, onChange, className = '' }) {
  return (
    <div
      className={`flex w-fit max-w-full gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50/80 p-1 ${className}`}
      role="tablist"
    >
      {options.map((option) => {
        const key = option.key ?? option.value;
        const isActive = value === key;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(key)}
            className={`filter-chip shrink-0 ${
              isActive
                ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200'
                : 'text-slate-500 hover:bg-white/70 hover:text-slate-700'
            }`}
          >
            {option.label}
            {option.count != null ? ` (${option.count})` : ''}
          </button>
        );
      })}
    </div>
  );
}
