import { FiChevronDown, FiX } from 'react-icons/fi';

const EMPTY = {
  company: '',
  industry: '',
  company_size: '',
  designation: '',
  location: '',
  icp_status: '',
  date_from: '',
  date_to: '',
};

const FILTER_LABELS = {
  company: 'Company',
  industry: 'Industry',
  company_size: 'Company size',
  designation: 'Designation',
  location: 'Location',
  icp_status: 'Status',
  date_from: 'Verified from',
  date_to: 'Verified to',
};

const PRIMARY_FILTER_KEYS = ['company'];
const ADVANCED_FILTER_FIELDS = [
  ['industry', 'Industry'],
  ['company_size', 'Company Size'],
  ['designation', 'Designation'],
  ['location', 'Location'],
  ['icp_status', 'ICP Status'],
];

export default function IcpFiltersPanel({
  open,
  filters,
  onChange,
  onApply,
  onClear,
  variant = 'full',
  excludeFields = [],
}) {
  if (!open) return null;

  function set(key, value) {
    onChange({ ...filters, [key]: value });
  }

  const hidden = new Set([...excludeFields, ...(variant === 'advanced' ? PRIMARY_FILTER_KEYS : [])]);
  const showPrimary = variant === 'full' && !hidden.has('company');

  return (
    <div className="surface-card space-y-4 p-3 sm:p-4 animate-rise-in">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-900">
            {variant === 'advanced' ? 'More filters' : 'Refine your audience'}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {variant === 'advanced'
              ? 'Industry, persona, status, and verified date.'
              : 'Filter by company, persona, status, or verified date.'}
          </p>
        </div>
        <button type="button" onClick={onClear} className="text-xs text-gray-500 hover:text-gray-700 shrink-0">
          Clear all
        </button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {showPrimary
          ? [
              <label key="company" className="block sm:col-span-2 lg:col-span-1">
                <span className="text-xs font-medium text-gray-500">Company</span>
                <input
                  className="control mt-1"
                  value={filters.company || ''}
                  onChange={(e) => set('company', e.target.value)}
                  placeholder="e.g. BankPlus"
                />
              </label>,
            ]
          : null}
        {ADVANCED_FILTER_FIELDS.filter(([key]) => !hidden.has(key)).map(([key, label]) => (
          <label key={key} className="block">
            <span className="text-xs font-medium text-gray-500">{label}</span>
            <input
              className="control mt-1"
              value={filters[key] || ''}
              onChange={(e) => set(key, e.target.value)}
              placeholder={key === 'industry' ? 'e.g. banking' : label}
            />
          </label>
        ))}
        {!hidden.has('date_from') && !hidden.has('date_to') ? (
          <label className="block sm:col-span-2 lg:col-span-3">
            <span className="text-xs font-medium text-gray-500">Verified date range</span>
            <div className="mt-1 grid grid-cols-2 gap-2">
              <input
                type="date"
                className="control"
                value={filters.date_from || ''}
                onChange={(e) => set('date_from', e.target.value)}
                aria-label="Verified from"
              />
              <input
                type="date"
                className="control"
                value={filters.date_to || ''}
                onChange={(e) => set('date_to', e.target.value)}
                aria-label="Verified to"
              />
            </div>
          </label>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onApply}
          className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700"
        >
          Apply filters
        </button>
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
        >
          <FiX size={14} /> Clear
        </button>
      </div>
    </div>
  );
}

export { EMPTY as EMPTY_ICP_FILTERS, FILTER_LABELS };
