export const FIELDS = [
  { key: 'name', label: 'Name' },
  { key: 'designation', label: 'Designation' },
  { key: 'company', label: 'Company' },
  { key: 'location', label: 'Person Location' },
  { key: 'company_location', label: 'Company Location' },
];

export function itemHasConflict(item) {
  if (!item) return false;
  const status = (item.verification_status || '').toUpperCase();
  if (status === 'RESOLVED' || status === 'VERIFIED' || status === 'ALREADY_EXISTS') return false;
  if (Array.isArray(item.conflicts)) return item.conflicts.length > 0;
  if (['MISMATCH', 'REVIEW', 'NEEDS_REVIEW'].includes(status)) return true;
  return FIELDS.some((f) => item[`${f.key}_match`] === false);
}

export function isVerifiedItem(item) {
  const status = (item?.verification_status || '').toUpperCase();
  return status === 'VERIFIED' || status === 'RESOLVED';
}

export function itemDisplayName(item) {
  return (
    item?.extracted?.name ||
    item?.uploaded?.name ||
    item?.url ||
    `Row ${item?.source_row_number ?? '?'}`
  );
}

export function splitValueTokens(value) {
  if (value == null) return [];
  const text = String(value).trim();
  if (!text) return [];
  const parts = text
    .split(/\s*[|,/•·]\s*|,\s+/)
    .map((p) => p.trim())
    .filter(Boolean);
  return parts.length ? parts : [text];
}
