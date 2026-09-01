/** Shared helpers for offering forms. */

export const EMPTY_OFFERING = {
  name: '',
  short_description: '',
  description: '',
  product_type: '',
  website_url: '',
  target_industries: [],
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
  must_have_rules: [],
  nice_to_have_rules: [],
  exclusion_rules: [],
  positive_keywords: [],
  negative_keywords: [],
};

export function listToText(value) {
  if (!value) return '';
  if (Array.isArray(value)) return value.join('\n');
  return String(value);
}

export function textToList(value) {
  if (!value || !String(value).trim()) return [];
  return String(value)
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function applyGeneratedIcp(form, generated) {
  const cs = generated.company_size || {};
  return {
    ...form,
    name: form.name || generated.suggested_name || '',
    short_description: form.short_description || generated.short_description || '',
    description: generated.description || form.description || '',
    product_type: form.product_type || generated.product_type || '',
    pricing_range: generated.pricing_range || form.pricing_range || '',
    target_industries: generated.industries || [],
    company_size_min: cs.min ?? '',
    company_size_max: cs.max ?? '',
    company_size_label: cs.label || '',
    target_geographies: generated.geographies || [],
    business_models: generated.business_models || [],
    target_departments: generated.departments || [],
    target_job_titles: generated.job_titles || [],
    target_seniority: generated.seniority || [],
    decision_maker_types: generated.decision_maker_types || [],
    buying_roles: generated.buying_roles || [],
    pain_points: generated.pain_points || [],
    business_problems: generated.business_problems || [],
    use_cases: generated.use_cases || [],
    desired_outcomes: generated.desired_outcomes || [],
    benefits: generated.benefits || [],
    positive_keywords: generated.positive_keywords || [],
    negative_keywords: generated.negative_keywords || [],
    must_have_rules: generated.must_have_rules || [],
    nice_to_have_rules: generated.nice_to_have_rules || [],
    exclusion_rules: generated.exclusion_rules || [],
  };
}

export function formToPayload(form) {
  const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
  return {
    name: form.name?.trim(),
    short_description: form.short_description?.trim() || null,
    description: form.description?.trim() || null,
    product_type: form.product_type?.trim() || null,
    website_url: form.website_url?.trim() || null,
    target_industries: Array.isArray(form.target_industries)
      ? form.target_industries
      : textToList(form.target_industries),
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
    must_have_rules: asList(form.must_have_rules),
    nice_to_have_rules: asList(form.nice_to_have_rules),
    exclusion_rules: asList(form.exclusion_rules),
    positive_keywords: asList(form.positive_keywords),
    negative_keywords: asList(form.negative_keywords),
    pricing_range: form.pricing_range?.trim() || null,
    status: form.status || 'active',
  };
}

function asList(value) {
  return Array.isArray(value) ? value : textToList(value);
}

export function ListField({ label, value, onChange, hint }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      {hint ? <span className="block text-xs text-gray-400">{hint}</span> : null}
      <textarea
        rows={3}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
        value={listToText(value)}
        onChange={(e) => onChange(textToList(e.target.value))}
        placeholder="One item per line"
      />
    </label>
  );
}

export function TextField({ label, value, onChange, required }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium text-gray-700">
        {label}
        {required ? ' *' : ''}
      </span>
      <input
        type="text"
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export function AreaField({ label, value, onChange, rows = 4 }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <textarea
        rows={rows}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
