import { extractPlaceholders } from './helpers';

/** Every {{Key}} -> Recipient field a template can merge in, matching the
 * mandatory prospect-info header set. Kept in sync with
 * backend/app/utils/helpers.py's KNOWN_MERGE_FIELDS — mirrored here since
 * preview rendering happens client-side. */
export const KNOWN_MERGE_FIELDS = [
  { key: 'Name', label: 'Recipient name', field: 'name' },
  { key: 'Email', label: 'Email', field: 'email' },
  { key: 'Company', label: 'Company', field: 'company' },
  { key: 'Designation', label: 'Designation', field: 'designation' },
  { key: 'DesignationLevel', label: 'Designation Level', field: 'designation_level' },
  { key: 'Industry', label: 'Industry', field: 'industry' },
  { key: 'Department', label: 'Department', field: 'department' },
  { key: 'Country', label: 'Country', field: 'country' },
  { key: 'State', label: 'State', field: 'state' },
  { key: 'City', label: 'City', field: 'city' },
  { key: 'CompanySize', label: 'Company Size', field: 'company_size' },
  { key: 'YearsOfExperience', label: 'Years of Experience', field: 'years_of_experience' },
  { key: 'Skills', label: 'Skills', field: 'skills' },
  { key: 'Source', label: 'Source', field: 'source' },
  { key: 'Status', label: 'Status', field: 'status' },
];

/** Primary tags shown on Offering Email compose — keep the UI clean. */
export const OFFERING_EMAIL_MERGE_FIELDS = [
  { key: 'Name', label: 'Recipient (contact name, or from email)' },
  { key: 'Company', label: 'Company' },
  { key: 'FromName', label: 'Your name (after Regards)' },
];

const KNOWN_KEYS_LOWER = new Set([
  ...KNOWN_MERGE_FIELDS.map((f) => f.key.toLowerCase()),
  'fromname',
]);

/** Case-insensitive check mirroring backend/app/utils/helpers.py's
 * is_known_merge_field — {{name}} is the same merge field as {{Name}},
 * not an undefined custom field (see buildRecipientContext below). */
function isKnownMergeField(key) {
  return KNOWN_KEYS_LOWER.has(key.toLowerCase());
}

const SAMPLE_MERGE_VALUES = {
  Name: 'John Doe',
  Email: 'john@acme.com',
  Company: 'Acme Corp',
  Designation: 'VP Engineering',
  DesignationLevel: 'Executive',
  Industry: 'Technology',
  Department: 'Engineering',
  Country: 'United States',
  State: 'California',
  City: 'San Francisco',
  CompanySize: '201-500',
  YearsOfExperience: '10+',
  Skills: 'Leadership',
  Source: 'LinkedIn',
  Status: 'Active',
  FromName: 'Your Name',
};

/** Sample context for the template editor's live preview, before any real
 * prospect is selected — user-entered placeholder values (from the
 * placeholder-type template UI) take priority over the generic samples. */
export function buildSamplePreviewContext(placeholderValues = {}) {
  const context = {};
  KNOWN_MERGE_FIELDS.forEach(({ key }) => {
    context[key] = placeholderValues[key] || SAMPLE_MERGE_VALUES[key];
  });
  context.FromName = placeholderValues.FromName || SAMPLE_MERGE_VALUES.FromName;
  return context;
}

/** Build the {{Key}}: value preview/render context from a real recipient
 * record (falls back to '—' for a missing value, matching how the rest of
 * the UI displays blanks). */
export function buildRecipientContext(recipient) {
  const context = {};
  KNOWN_MERGE_FIELDS.forEach(({ key, field }) => {
    let value = recipient[field] || '';
    if (key === 'Name' && !String(value).trim()) {
      value = nameFromEmail(recipient.email) || '—';
    }
    if (!value) value = '—';
    context[key] = value;
    context[key.toLowerCase()] = value;
  });
  return context;
}

export function nameFromEmail(email) {
  const raw = String(email || '').trim();
  if (!raw.includes('@')) return '';
  const local = raw.split('@')[0].trim();
  if (!local) return '';
  const parts = local.split(/[._+\-]+/).filter((p) => p && /^[a-zA-Z]+$/.test(p));
  if (!parts.length) return local.charAt(0).toUpperCase() + local.slice(1);
  return parts.map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}

/** Every {{Field}} used across the given template text blocks that isn't a
 * known header (case-insensitive — see isKnownMergeField) or an
 * already-approved custom field name. */
export function getUnknownPlaceholders(textBlocks, approvedCustomFieldNames = []) {
  const approved = new Set(approvedCustomFieldNames);
  const used = new Set();
  textBlocks.filter(Boolean).forEach((text) => {
    extractPlaceholders(text).forEach((key) => used.add(key));
  });
  return [...used].filter((key) => !isKnownMergeField(key) && !approved.has(key));
}
