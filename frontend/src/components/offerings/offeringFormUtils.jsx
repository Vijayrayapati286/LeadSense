/** Shared helpers for offering forms. */

import { useState } from 'react';
import { getDefaultAiTone } from '../../utils/workspaceDefaults';
import { normalizeList, reconcileAiDraft } from './offeringDraftUtils';

export const EMPTY_OFFERING = {
  name: '',
  short_description: '',
  description: '',
  detailed_description: '',
  product_type: '',
  website_url: '',
  pricing_range: '',
  target_customer: '',
  target_industries: [],
  target_company_size: [],
  company_size_min: '',
  company_size_max: '',
  company_size_label: '',
  revenue_min: '',
  revenue_max: '',
  target_geographies: [],
  business_models: [],
  target_departments: [],
  target_job_titles: [],
  target_seniority: [],
  decision_maker_types: [],
  buying_roles: [],
  pain_points: [],
  business_problems: [],
  current_challenges: [],
  use_cases: [],
  desired_outcomes: [],
  benefits: [],
  selling_points: [],
  must_have_rules: [],
  nice_to_have_rules: [],
  exclusion_rules: [],
  positive_keywords: [],
  negative_keywords: [],
  vouchers: [],
  email_template: null,
};

export function listToText(value) {
  if (!value) return '';
  if (Array.isArray(value)) return value.join('\n');
  return String(value);
}

export function textToList(value) {
  return normalizeList(value);
}

function asList(value) {
  return normalizeList(value);
}

export function applyGeneratedIcp(form, generated) {
  return reconcileAiDraft(form, generated).form;
}

export function formToPayload(form) {
  const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
  return {
    name: form.name?.trim(),
    short_description: form.short_description?.trim() || null,
    description: (form.detailed_description || form.description)?.trim() || null,
    detailed_description: (form.detailed_description || form.description)?.trim() || null,
    product_type: form.product_type?.trim() || null,
    website_url: form.website_url?.trim() || null,
    target_customer: form.target_customer?.trim() || null,
    target_industries: Array.isArray(form.target_industries)
      ? normalizeList(form.target_industries)
      : textToList(form.target_industries),
    target_company_size: asList(form.target_company_size),
    company_size_min: num(form.company_size_min),
    company_size_max: num(form.company_size_max),
    company_size_label: form.company_size_label?.trim() || null,
    revenue_min: num(form.revenue_min),
    revenue_max: num(form.revenue_max),
    target_geographies: asList(form.target_geographies),
    business_models: asList(form.business_models),
    target_departments: asList(form.target_departments),
    target_job_titles: asList(form.target_job_titles),
    target_seniority: asList(form.target_seniority),
    decision_maker_types: asList(form.decision_maker_types),
    buying_roles: asList(form.buying_roles),
    pain_points: asList(form.pain_points),
    business_problems: asList(form.business_problems),
    current_challenges: asList(form.current_challenges),
    use_cases: asList(form.use_cases),
    desired_outcomes: asList(form.desired_outcomes),
    benefits: asList(form.benefits),
    selling_points: asList(form.selling_points),
    must_have_rules: asList(form.must_have_rules),
    nice_to_have_rules: asList(form.nice_to_have_rules),
    exclusion_rules: asList(form.exclusion_rules),
    positive_keywords: asList(form.positive_keywords),
    negative_keywords: asList(form.negative_keywords),
    pricing_range: form.pricing_range?.trim() || null,
    vouchers: Array.isArray(form.vouchers) ? form.vouchers : [],
    email_template: form.email_template || null,
    status: form.status || 'active',
  };
}

export function offeringEmailTemplateName(offeringName, existingName) {
  const stored = (existingName || '').trim();
  if (stored && stored !== 'Introduction Outreach') return stored;
  const base = (offeringName || '').trim();
  return base ? `${base} — Outreach` : 'Introduction Outreach';
}

export function formToEmailContext(form) {
  const asArr = (value) => (Array.isArray(value) ? value : textToList(value));
  return {
    name: form.name?.trim() || 'Untitled offering',
    short_description: form.short_description?.trim() || null,
    description: form.description?.trim() || null,
    product_type: form.product_type?.trim() || null,
    target_industries: asArr(form.target_industries),
    target_job_titles: asArr(form.target_job_titles),
    target_geographies: asArr(form.target_geographies),
    company_size_label: form.company_size_label?.trim() || null,
    pain_points: asArr(form.pain_points),
    use_cases: asArr(form.use_cases),
    benefits: asArr(form.benefits),
    desired_outcomes: asArr(form.desired_outcomes),
    decision_maker_types: asArr(form.decision_maker_types),
    buying_roles: asArr(form.buying_roles),
    tone: getDefaultAiTone(),
    count: 3,
  };
}

export function ListField({ label, value, onChange, hint, generated, onRegenerate, regenerating, error }) {
  const [draft, setDraft] = useState('');
  const items = normalizeList(value);

  function addDraft() {
    const additions = normalizeList(draft);
    if (!additions.length) return;
    onChange(normalizeList([...items, ...additions]));
    setDraft('');
  }

  return (
    <div className="block space-y-1.5">
      <FieldLabel label={label} generated={generated} onRegenerate={onRegenerate} regenerating={regenerating} />
      {hint ? <span className="block text-xs text-gray-400">{hint}</span> : null}
      <div className={`control min-h-[46px] h-auto p-2 ${error ? 'border-red-400' : ''}`}>
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <span key={item.toLocaleLowerCase()} className="inline-flex items-center gap-1 rounded-full bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-800">
              {item}
              <button type="button" aria-label={`Remove ${item}`} onClick={() => onChange(items.filter((entry) => entry !== item))} className="text-primary-500 hover:text-primary-900">×</button>
            </span>
          ))}
          <input
            className="min-w-[150px] flex-1 border-0 bg-transparent px-1 py-1 text-sm outline-none"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={addDraft}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ',') {
                event.preventDefault();
                addDraft();
              }
            }}
            placeholder={items.length ? 'Add another…' : 'Type and press Enter'}
          />
        </div>
      </div>
      {error ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}

function FieldLabel({ label, required, generated, onRegenerate, regenerating }) {
  return (
    <span className="flex min-h-6 items-center justify-between gap-2 text-sm font-medium text-gray-700">
      <span>{label}{required ? ' *' : ''}</span>
      <span className="flex items-center gap-2">
        {generated ? <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700">✨ AI generated</span> : null}
        {onRegenerate ? <button type="button" disabled={regenerating} onClick={onRegenerate} className="text-[11px] font-semibold text-primary-600 hover:text-primary-800 disabled:opacity-50">{regenerating ? 'Generating…' : 'Regenerate'}</button> : null}
      </span>
    </span>
  );
}

export function TextField({ label, value, onChange, required, generated, onRegenerate, regenerating, error, type = 'text', placeholder }) {
  return (
    <label className="block space-y-1">
      <FieldLabel label={label} required={required} generated={generated} onRegenerate={onRegenerate} regenerating={regenerating} />
      <input
        type={type}
        className={`control ${error ? 'border-red-400 focus:border-red-500' : ''}`}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {error ? <span className="block text-xs text-red-600">{error}</span> : null}
    </label>
  );
}

export function AreaField({ label, value, onChange, rows = 4, generated, onRegenerate, regenerating, error, placeholder }) {
  return (
    <label className="block space-y-1">
      <FieldLabel label={label} generated={generated} onRegenerate={onRegenerate} regenerating={regenerating} />
      <textarea
        rows={rows}
        className={`control resize-y ${error ? 'border-red-400 focus:border-red-500' : ''}`}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {error ? <span className="block text-xs text-red-600">{error}</span> : null}
    </label>
  );
}
