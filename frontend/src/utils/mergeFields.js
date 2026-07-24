import { extractPlaceholders } from './helpers';

/** Every {{Key}} -> Recipient field a template can merge in, matching the
 * mandatory prospect-info header set. Kept in sync with
 * backend/app/utils/helpers.py's KNOWN_MERGE_FIELDS — mirrored here since
 * preview rendering happens client-side. */
export const KNOWN_MERGE_FIELDS = [
  { key: 'Name', label: 'Name', field: 'name' },
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

const KNOWN_KEYS = new Set(KNOWN_MERGE_FIELDS.map((f) => f.key));

const SAMPLE_MERGE_VALUES = {
  Name: 'John Doe',
  Email: 'john@acme.com',
  Company: 'Acme Corp',
  Designation: 'CEO',
  DesignationLevel: 'Executive',
  Industry: 'Technology',
  Department: 'Sales',
  Country: 'United States',
  State: 'California',
  City: 'San Francisco',
  CompanySize: '201-500',
  YearsOfExperience: '10+',
  Skills: 'Leadership',
  Source: 'Website',
  Status: 'Active',
};

/** Sample context for the template editor's live preview, before any real
 * prospect is selected — user-entered placeholder values (from the
 * placeholder-type template UI) take priority over the generic samples. */
export function buildSamplePreviewContext(placeholderValues = {}) {
  const context = {};
  KNOWN_MERGE_FIELDS.forEach(({ key }) => {
    context[key] = placeholderValues[key] || SAMPLE_MERGE_VALUES[key];
  });
  return context;
}

/** Build the {{Key}}: value preview/render context from a real recipient
 * record (falls back to '—' for a missing value, matching how the rest of
 * the UI displays blanks). */
export function buildRecipientContext(recipient) {
  const context = {};
  KNOWN_MERGE_FIELDS.forEach(({ key, field }) => {
    context[key] = recipient[field] || '—';
  });
  return context;
}

/** Every {{Field}} used across the given template text blocks that isn't a
 * known header or an already-approved custom field name. */
export function getUnknownPlaceholders(textBlocks, approvedCustomFieldNames = []) {
  const approved = new Set(approvedCustomFieldNames);
  const used = new Set();
  textBlocks.filter(Boolean).forEach((text) => {
    extractPlaceholders(text).forEach((key) => used.add(key));
  });
  return [...used].filter((key) => !KNOWN_KEYS.has(key) && !approved.has(key));
}
