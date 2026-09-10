export const ARRAY_FIELDS = new Set([
  'target_industries',
  'target_company_size',
  'target_geographies',
  'business_models',
  'target_departments',
  'target_job_titles',
  'target_seniority',
  'decision_maker_types',
  'buying_roles',
  'pain_points',
  'business_problems',
  'current_challenges',
  'use_cases',
  'desired_outcomes',
  'benefits',
  'selling_points',
  'must_have_rules',
  'nice_to_have_rules',
  'exclusion_rules',
  'positive_keywords',
  'negative_keywords',
]);

export const AI_EDITABLE_FIELDS = [
  'name',
  'product_type',
  'short_description',
  'detailed_description',
  'target_customer',
  'target_industries',
  'target_company_size',
  'target_job_titles',
  'pain_points',
  'current_challenges',
  'use_cases',
  'benefits',
  'selling_points',
];

const LEGACY_PLACEHOLDER = {
  name: 'ai sales platform',
  product_type: 'saas',
  short_description: 'ai-powered platform for b2b sales teams',
};

export function normalizeList(value) {
  const values = Array.isArray(value)
    ? value
    : String(value || '').split(/[\n,]+/);
  const seen = new Set();
  return values
    .map((item) => String(item).trim())
    .filter((item) => {
      const key = item.toLocaleLowerCase();
      if (!item || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

export function normalizeValue(field, value) {
  if (ARRAY_FIELDS.has(field)) return normalizeList(value);
  return typeof value === 'string' ? value.trim() : value ?? '';
}

export function isBlank(value) {
  if (Array.isArray(value)) return value.length === 0;
  return value === null || value === undefined || String(value).trim() === '';
}

export function valuesEqual(field, left, right) {
  const a = normalizeValue(field, left);
  const b = normalizeValue(field, right);
  if (ARRAY_FIELDS.has(field)) {
    return JSON.stringify(a.map((item) => item.toLocaleLowerCase())) ===
      JSON.stringify(b.map((item) => item.toLocaleLowerCase()));
  }
  return String(a).toLocaleLowerCase() === String(b).toLocaleLowerCase();
}

export function draftToFormValues(draft) {
  const size = draft.company_size || {};
  const sizeLabel =
    (Array.isArray(draft.target_company_size) && draft.target_company_size[0]) ||
    size.label ||
    ([size.min, size.max].filter((value) => value != null).join('–') || '');
  return {
    name: draft.suggested_name || draft.name || '',
    product_type: draft.product_type || '',
    short_description: draft.short_description || '',
    detailed_description: draft.detailed_description || draft.description || '',
    target_customer: draft.target_customer || '',
    target_industries: draft.industries || draft.target_industries || [],
    target_company_size: sizeLabel ? [sizeLabel] : [],
    target_job_titles: draft.job_titles || draft.target_job_titles || [],
    pain_points: draft.pain_points || [],
    current_challenges: draft.current_challenges || draft.business_problems || [],
    use_cases: draft.use_cases || [],
    benefits: draft.benefits || [],
    selling_points: draft.selling_points || [],
    target_geographies: draft.geographies || [],
    business_models: draft.business_models || [],
    target_departments: draft.departments || [],
    target_seniority: draft.seniority || [],
    decision_maker_types: draft.decision_maker_types || [],
    buying_roles: draft.buying_roles || [],
    business_problems: draft.business_problems || [],
    desired_outcomes: draft.desired_outcomes || [],
    positive_keywords: draft.positive_keywords || [],
    negative_keywords: draft.negative_keywords || [],
    must_have_rules: draft.must_have_rules || [],
    nice_to_have_rules: draft.nice_to_have_rules || [],
    exclusion_rules: draft.exclusion_rules || [],
    pricing_range: draft.pricing_range || '',
  };
}

export function reconcileAiDraft(form, draft, requestedFields = null, currentProvenance = {}) {
  const generated = draftToFormValues(draft);
  const fields = requestedFields?.length ? requestedFields : Object.keys(generated);
  const nextForm = { ...form };
  const suggestions = {};
  const provenance = {};
  const fullRegenerate = !requestedFields?.length;

  fields.forEach((field) => {
    const suggested = normalizeValue(field, generated[field]);
    if (isBlank(suggested) || valuesEqual(field, form[field], suggested)) return;
    // Blank fields, or fields still carrying a prior AI draft on a full
    // "Generate draft", take the new suggestion immediately. User-edited
    // values stay protected and surface as reviewable suggestions instead.
    const priorSource = currentProvenance[field];
    const replacePriorAi = fullRegenerate && (priorSource === 'ai_generated' || priorSource === 'ai_accepted');
    if (isBlank(form[field]) || replacePriorAi) {
      nextForm[field] = suggested;
      provenance[field] = 'ai_generated';
    } else {
      suggestions[field] = {
        current: normalizeValue(field, form[field]),
        suggested,
      };
    }
  });

  return { form: nextForm, suggestions, provenance };
}

export function acceptAiSuggestion(form, suggestions, field) {
  const suggestion = suggestions[field];
  if (!suggestion) return { form, suggestions };
  const nextSuggestions = { ...suggestions };
  delete nextSuggestions[field];
  return {
    form: { ...form, [field]: suggestion.suggested },
    suggestions: nextSuggestions,
  };
}

export function keepCurrentSuggestion(suggestions, field) {
  const next = { ...suggestions };
  delete next[field];
  return next;
}

export function applyAllAiSuggestions(form, suggestions) {
  const next = { ...form };
  Object.entries(suggestions).forEach(([field, item]) => {
    next[field] = item.suggested;
  });
  return { form: next, suggestions: {} };
}

export function validateOffering(form) {
  const errors = {};
  if (!String(form.name || '').trim()) errors.name = 'Offering name is required';
  if (!String(form.product_type || '').trim()) {
    errors.product_type = 'Product or service type is required';
  }
  if (form.website_url && !/^https?:\/\/\S+$/i.test(String(form.website_url).trim())) {
    errors.website_url = 'Enter a complete URL beginning with http:// or https://';
  }
  const isLegacyPlaceholder = Object.entries(LEGACY_PLACEHOLDER).every(
    ([field, value]) => String(form[field] || '').trim().toLocaleLowerCase() === value,
  );
  if (isLegacyPlaceholder) {
    errors.name = 'Replace the generic placeholder draft before saving';
  }
  return errors;
}
