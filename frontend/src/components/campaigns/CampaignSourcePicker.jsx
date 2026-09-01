import { useEffect, useRef, useState } from 'react';
import { FiChevronDown, FiGift, FiInfo, FiPlus, FiZap } from 'react-icons/fi';

export const CAMPAIGN_SOURCE_OPTIONS = [
  {
    id: 'create',
    label: 'Create new',
    description: 'Start a campaign from scratch',
    icon: FiPlus,
    iconBg: 'bg-blue-100',
    iconColor: 'text-blue-600',
  },
  {
    id: 'offering',
    label: 'Select from offering',
    description: 'Choose from existing offerings',
    icon: FiGift,
    iconBg: 'bg-emerald-100',
    iconColor: 'text-emerald-600',
  },
  {
    id: 'smart_ops',
    label: 'Select from Smart Ops',
    description: 'Use from Smart Operations',
    icon: FiZap,
    iconBg: 'bg-violet-100',
    iconColor: 'text-violet-600',
  },
];

function SourceOptionRow({ option, selected, onClick }) {
  const Icon = option.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
        selected ? 'bg-primary-50 ring-1 ring-primary-200' : 'hover:bg-slate-50'
      }`}
    >
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${option.iconBg}`}>
        <Icon size={16} className={option.iconColor} />
      </span>
      <span className="min-w-0 pt-0.5">
        <span className="block text-sm font-semibold text-slate-900">{option.label}</span>
        <span className="block text-xs text-slate-500 mt-0.5">{option.description}</span>
      </span>
    </button>
  );
}

export default function CampaignSourcePicker({
  value,
  onChange,
  offerings = [],
  mailers = [],
  selectedOfferingId,
  selectedSmartOpsId,
  onOfferingSelect,
  onSmartOpsSelect,
  loadingSource = false,
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const selected = CAMPAIGN_SOURCE_OPTIONS.find((o) => o.id === value) || CAMPAIGN_SOURCE_OPTIONS[0];
  const SelectedIcon = selected.icon;

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="space-y-2">
      <label className="flex items-center gap-1.5 text-sm font-semibold text-slate-800">
        Campaign Source
        <FiInfo size={14} className="text-slate-400" title="Choose how to start this campaign" />
      </label>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left shadow-sm transition-all hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
      >
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${selected.iconBg}`}>
          <SelectedIcon size={16} className={selected.iconColor} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-900">{selected.label}</span>
          <span className="block text-xs text-slate-500 truncate">{selected.description}</span>
        </span>
        <FiChevronDown size={16} className={`shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open ? (
        <div className="rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg space-y-0.5">
          {CAMPAIGN_SOURCE_OPTIONS.map((option) => (
            <SourceOptionRow
              key={option.id}
              option={option}
              selected={option.id === value}
              onClick={() => {
                onChange(option.id);
                setOpen(false);
              }}
            />
          ))}
        </div>
      ) : null}

      {value === 'offering' ? (
        <select
          className="campaign-field-select"
          value={selectedOfferingId}
          onChange={(e) => onOfferingSelect(e.target.value)}
          disabled={loadingSource}
        >
          <option value="">Choose offering...</option>
          {offerings.map((offering) => (
            <option key={offering.id} value={offering.id}>{offering.name}</option>
          ))}
        </select>
      ) : null}

      {value === 'smart_ops' ? (
        <select
          className="campaign-field-select"
          value={selectedSmartOpsId}
          onChange={(e) => onSmartOpsSelect(e.target.value)}
        >
          <option value="">Choose Smart Ops mailer...</option>
          {mailers.map((mailer) => (
            <option key={mailer.id} value={mailer.id}>{mailer.name}</option>
          ))}
        </select>
      ) : null}
    </div>
  );
}
