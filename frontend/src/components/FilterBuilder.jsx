import { useRef, useState, useEffect } from 'react';
import { FiPlus, FiX } from 'react-icons/fi';
import MultiSelectDropdown from './ui/MultiSelectDropdown';

// Every field the dynamic "Add Filter" dropdown can offer. `type` decides
// which input control renders for that filter row.
export const FIELD_DEFS = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'company', label: 'Company Name', type: 'text' },
  { key: 'designation', label: 'Job Designation/Title', type: 'distinct' },
  { key: 'department', label: 'Department', type: 'text' },
  { key: 'industry', label: 'Industry', type: 'distinct' },
  { key: 'email', label: 'Business Email', type: 'text' },
  { key: 'email_domain', label: 'Email Domain', type: 'text' },
  { key: 'country', label: 'Country', type: 'distinct' },
  { key: 'state', label: 'State', type: 'distinct' },
  { key: 'city', label: 'City', type: 'distinct' },
  { key: 'company_size', label: 'Company Size', type: 'text' },
  { key: 'years_of_experience', label: 'Years of Experience', type: 'text' },
  { key: 'skills', label: 'Skills', type: 'distinct' },
  { key: 'seniority_level', label: 'Seniority Level', type: 'distinct' },
  { key: 'lead_status', label: 'Lead Status', type: 'distinct' },
  { key: 'response_tag', label: 'Response', type: 'fixed_options' },
  { key: 'campaign_status', label: 'Campaign Status', type: 'campaign_status' },
  { key: 'source', label: 'Source', type: 'text' },
  { key: 'group_ids', label: 'Prospect Group', type: 'groups' },
  { key: 'tag_ids', label: 'Tags', type: 'tags' },
];

const CAMPAIGN_STATUSES = [
  'not_contacted', 'queued', 'sent', 'delivered', 'opened', 'clicked',
  'replied', 'bounced', 'invalid_email', 'suppressed',
];

export const RESPONSE_TAGS = ['Cold', 'Negative', 'Warm', 'Hot'];

function AddFilterMenu({ availableFields, onAdd }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    const onClickOutside = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const filtered = availableFields.filter((f) => f.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div ref={ref} className="relative inline-block">
      <button type="button" onClick={() => setOpen((o) => !o)} className="btn-secondary text-sm flex items-center gap-1.5">
        <FiPlus size={14} /> Add Filter
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-64 bg-white rounded-lg border border-gray-200 shadow-lg max-h-72 overflow-hidden flex flex-col">
          <input
            autoFocus
            className="px-3 py-2 border-b border-gray-100 text-sm outline-none"
            placeholder="Search fields..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-sm text-gray-400">No fields left to add</p>
            ) : (
              filtered.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => { onAdd(f.key); setOpen(false); setQuery(''); }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
                >
                  {f.label}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Dynamic CRM-style filter builder: click "Add Filter", pick a field, set
 * its value; each active filter renders as its own removable row. Only
 * fields the user has actually added are shown — nothing is pre-cluttered. */
export default function FilterBuilder({
  activeFieldKeys,
  values,
  onAddField,
  onRemoveField,
  onValueChange,
  distinctOptions,
  distinctLoading,
  groups,
  tags,
  campaigns,
}) {
  const availableFields = FIELD_DEFS.filter((f) => !activeFieldKeys.includes(f.key));
  const activeDefs = FIELD_DEFS.filter((f) => activeFieldKeys.includes(f.key));

  return (
    <div className="space-y-3">
      {activeDefs.length > 0 && (
        <div className="space-y-2">
          {activeDefs.map((f) => (
            <div key={f.key} className="flex items-start gap-2 rounded-xl border border-gray-200 p-3">
              <div className="flex-1">
                {f.type === 'text' && (
                  <>
                    <label className="label">{f.label}</label>
                    <input
                      autoFocus
                      className="input-field"
                      value={values[f.key] || ''}
                      onChange={(e) => onValueChange(f.key, e.target.value)}
                      placeholder={`Contains...`}
                    />
                  </>
                )}

                {f.type === 'distinct' && (
                  <MultiSelectDropdown
                    label={f.label}
                    options={distinctOptions[f.key] || []}
                    selected={values[f.key] || []}
                    onChange={(vals) => onValueChange(f.key, vals)}
                    loading={distinctLoading[f.key]}
                  />
                )}

                {f.type === 'groups' && (
                  <MultiSelectDropdown
                    label={f.label}
                    options={groups.map((g) => g.name)}
                    selected={(values[f.key] || []).map((id) => groups.find((g) => g.id === id)?.name).filter(Boolean)}
                    onChange={(names) => onValueChange(f.key, names.map((n) => groups.find((g) => g.name === n)?.id).filter(Boolean))}
                  />
                )}

                {f.type === 'tags' && (
                  <MultiSelectDropdown
                    label={f.label}
                    options={tags.map((t) => t.name)}
                    selected={(values[f.key] || []).map((id) => tags.find((t) => t.id === id)?.name).filter(Boolean)}
                    onChange={(names) => onValueChange(f.key, names.map((n) => tags.find((t) => t.name === n)?.id).filter(Boolean))}
                  />
                )}

                {f.type === 'fixed_options' && (
                  <MultiSelectDropdown
                    label={f.label}
                    options={RESPONSE_TAGS}
                    selected={values[f.key] || []}
                    onChange={(vals) => onValueChange(f.key, vals)}
                  />
                )}

                {f.type === 'campaign_status' && (
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="label">Campaign</label>
                      <select
                        className="input-field"
                        value={values.campaign_id || ''}
                        onChange={(e) => onValueChange('campaign_id', e.target.value)}
                      >
                        <option value="">Select campaign...</option>
                        {campaigns.map((c) => (
                          <option key={c.id} value={c.id}>{c.campaign_name}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="label">Status</label>
                      <select
                        className="input-field"
                        value={values.campaign_status || ''}
                        onChange={(e) => onValueChange('campaign_status', e.target.value)}
                        disabled={!values.campaign_id}
                      >
                        <option value="">Any status</option>
                        {CAMPAIGN_STATUSES.map((s) => (
                          <option key={s} value={s}>{s.replace('_', ' ')}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => onRemoveField(f.key)}
                className="mt-6 p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600 flex-shrink-0"
                title="Remove filter"
              >
                <FiX size={16} />
              </button>
            </div>
          ))}
        </div>
      )}

      <AddFilterMenu availableFields={availableFields} onAdd={onAddField} />
    </div>
  );
}
