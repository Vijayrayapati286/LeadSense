import { useEffect, useRef, useState } from 'react';
import { FiChevronDown, FiX } from 'react-icons/fi';

/** A checkbox-list dropdown for selecting multiple values (OR within the
 * field), with its options populated dynamically from real data rather than
 * a hardcoded list. Selected values render as removable chips below. */
export default function MultiSelectDropdown({ label, options, selected, onChange, loading }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleValue = (value) => {
    if (selected.includes(value)) onChange(selected.filter((v) => v !== value));
    else onChange([...selected, value]);
  };

  const removeValue = (value) => onChange(selected.filter((v) => v !== value));

  const filteredOptions = options.filter((o) => o.toLowerCase().includes(query.toLowerCase()));

  return (
    <div ref={containerRef} className="relative">
      <label className="label">{label}</label>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="input-field flex items-center justify-between text-left"
      >
        <span className="text-gray-500 truncate">
          {selected.length > 0 ? `${selected.length} selected` : `Any ${label.toLowerCase()}`}
        </span>
        <FiChevronDown size={16} className="text-gray-400 flex-shrink-0" />
      </button>

      {open && (
        <div className="absolute z-20 mt-1 w-full bg-white rounded-lg border border-gray-200 shadow-lg max-h-64 overflow-hidden flex flex-col">
          <input
            autoFocus
            className="px-3 py-2 border-b border-gray-100 text-sm outline-none"
            placeholder={`Search ${label.toLowerCase()}...`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="overflow-y-auto">
            {loading ? (
              <p className="px-3 py-2 text-sm text-gray-400">Loading...</p>
            ) : filteredOptions.length === 0 ? (
              <p className="px-3 py-2 text-sm text-gray-400">No values found</p>
            ) : (
              filteredOptions.map((opt) => (
                <label key={opt} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-gray-50 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected.includes(opt)}
                    onChange={() => toggleValue(opt)}
                    className="rounded border-gray-300"
                  />
                  {opt}
                </label>
              ))
            )}
          </div>
        </div>
      )}

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {selected.map((v) => (
            <span key={v} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 text-xs">
              {v}
              <button type="button" onClick={() => removeValue(v)} className="hover:text-primary-900">
                <FiX size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
