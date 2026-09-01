import { FiX } from 'react-icons/fi';

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

export default function IcpFiltersPanel({ open, filters, onChange, onApply, onClear }) {
  if (!open) return null;

  function set(key, value) {
    onChange({ ...filters, [key]: value });
  }

  return (
    <div className="surface-card space-y-5 p-4 sm:p-5 animate-rise-in">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900">Refine your audience</p>
          <p className="mt-0.5 text-xs text-slate-500">Filter by company, persona, status, or verified date.</p>
        </div>
        <button type="button" onClick={onClear} className="text-xs text-gray-500 hover:text-gray-700">
          Clear all
        </button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['company', 'Company'],
          ['industry', 'Industry'],
          ['company_size', 'Company Size'],
          ['designation', 'Designation'],
          ['location', 'Location'],
          ['icp_status', 'ICP Status'],
        ].map(([key, label]) => (
          <label key={key} className="block">
            <span className="text-xs font-medium text-gray-500">{label}</span>
            <input
              className="control mt-1"
              value={filters[key] || ''}
              onChange={(e) => set(key, e.target.value)}
              placeholder={
                key === 'company'
                  ? 'e.g. BankPlus'
                  : key === 'industry'
                    ? 'e.g. banking'
                    : label
              }
            />
          </label>
        ))}
        <label className="block sm:col-span-2">
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
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onApply}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          Apply Filters
        </button>
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          <FiX size={14} /> Clear Filters
        </button>
      </div>
    </div>
  );
}

export { EMPTY as EMPTY_ICP_FILTERS, FILTER_LABELS };
