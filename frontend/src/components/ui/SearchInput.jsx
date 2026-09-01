import { FiSearch } from 'react-icons/fi';

export default function SearchInput({ value = '', onChange, placeholder = 'Search...', className = '' }) {
  return (
    <div className={`relative min-w-0 ${className}`}>
      <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="control pl-10"
      />
    </div>
  );
}
