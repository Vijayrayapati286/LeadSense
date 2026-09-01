import { FiAlertTriangle, FiCheck, FiX } from 'react-icons/fi';

export const COMPARE_FIELDS = [
  { key: 'name', label: 'Name', major: true },
  { key: 'job_title', label: 'Job title', major: true },
  { key: 'company', label: 'Company', major: true },
  { key: 'headline', label: 'Headline', major: false },
  { key: 'location', label: 'Location', major: false },
  { key: 'summary', label: 'About / Summary', major: false },
  { key: 'followers', label: 'Followers', major: false },
  { key: 'connections', label: 'Connections', major: false },
];

export function normalizeValue(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim().replace(/\s+/g, ' ').toLowerCase();
}

export function tokenOverlap(a, b) {
  const left = new Set(normalizeValue(a).split(' ').filter(Boolean));
  const right = new Set(normalizeValue(b).split(' ').filter(Boolean));
  if (!left.size || !right.size) return 0;
  let hit = 0;
  left.forEach((t) => {
    if (right.has(t)) hit += 1;
  });
  return hit / Math.max(left.size, right.size);
}

export function classifyField(field, existing, extracted) {
  const oldVal = existing?.[field.key];
  const newVal = extracted?.[field.key];
  const oldN = normalizeValue(oldVal);
  const newN = normalizeValue(newVal);
  if (!oldN && !newN) return { status: 'empty', major: false };
  if (oldN === newN) return { status: 'unchanged', major: false };
  if (!oldN) return { status: 'added', major: false };
  if (!newN) return { status: 'removed', major: Boolean(field.major) };

  if (field.major) return { status: 'changed', major: true };

  const overlap = tokenOverlap(oldVal, newVal);
  if (overlap < 0.35 && oldN.length > 2) {
    return { status: 'changed', major: true };
  }
  return { status: 'changed', major: false };
}

export function buildDiff(existing, extracted, fields = COMPARE_FIELDS) {
  return fields.map((field) => ({
    ...field,
    existing: existing?.[field.key],
    extracted: extracted?.[field.key],
    ...classifyField(field, existing, extracted),
  }));
}

function display(value) {
  const text = value?.toString().trim();
  return text ? text : '—';
}

export default function GitDiffCompare({
  existing,
  extracted,
  onApprove,
  onReject,
  requireApproval = false,
}) {
  const rows = buildDiff(existing, extracted);
  const changed = rows.filter((r) => r.status !== 'unchanged' && r.status !== 'empty');
  const majors = changed.filter((r) => r.major);
  const needsApproval = requireApproval && majors.length > 0;

  return (
    <div className="space-y-4">
      {needsApproval ? (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
          <FiAlertTriangle className="mt-0.5 shrink-0 text-red-600" size={18} />
          <div>
            <p className="text-sm font-semibold text-red-800">Major changes need approval</p>
            <p className="text-sm text-red-700 mt-0.5">
              {majors.map((m) => m.label).join(', ')} changed vs the saved record. Red rows are
              treated like a breaking diff — approve before replacing existing data.
            </p>
          </div>
        </div>
      ) : changed.length > 0 ? (
        <p className="text-sm text-gray-500">
          {changed.length} field{changed.length === 1 ? '' : 's'} differ from the saved record.
        </p>
      ) : (
        <p className="text-sm text-green-700">Extracted data matches the saved record.</p>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 font-mono text-[13px]">
        <div className="grid grid-cols-2 bg-gray-50 border-b border-gray-200 text-xs font-sans uppercase tracking-wide text-gray-500">
          <div className="px-4 py-2 border-r border-gray-200">Existing</div>
          <div className="px-4 py-2">Extracted</div>
        </div>
        {rows.map((row) => {
          const isMajor = row.major && row.status !== 'unchanged' && row.status !== 'empty';
          const changedRow = row.status !== 'unchanged' && row.status !== 'empty';
          return (
            <div
              key={row.key}
              className={`grid grid-cols-2 border-b border-gray-100 last:border-b-0 ${
                isMajor ? 'bg-red-50/80' : changedRow ? 'bg-amber-50/40' : 'bg-white'
              }`}
            >
              <div className="px-4 py-2.5 border-r border-gray-100 min-w-0">
                <p className="font-sans text-[10px] uppercase tracking-wide text-gray-400 mb-1">
                  {row.label}
                  {isMajor ? (
                    <span className="ml-2 rounded bg-red-600 px-1.5 py-0.5 text-[9px] font-semibold text-white">
                      Major
                    </span>
                  ) : null}
                </p>
                <p
                  className={`whitespace-pre-wrap break-words ${
                    isMajor
                      ? 'text-red-800'
                      : row.status === 'unchanged'
                        ? 'text-gray-700'
                        : 'text-red-700'
                  }`}
                >
                  {changedRow && row.status !== 'added' ? (
                    <span className="select-none text-red-500 mr-1">−</span>
                  ) : null}
                  {display(row.existing)}
                </p>
              </div>
              <div className="px-4 py-2.5 min-w-0">
                <p className="font-sans text-[10px] uppercase tracking-wide text-gray-400 mb-1">
                  {row.label}
                </p>
                <p
                  className={`whitespace-pre-wrap break-words ${
                    isMajor
                      ? 'text-red-800 font-medium'
                      : row.status === 'unchanged'
                        ? 'text-gray-700'
                        : 'text-green-800'
                  }`}
                >
                  {changedRow && row.status !== 'removed' ? (
                    <span className="select-none text-green-600 mr-1">+</span>
                  ) : null}
                  {display(row.extracted)}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {needsApproval ? (
        <div className="flex flex-col sm:flex-row gap-2 justify-end">
          <button
            type="button"
            onClick={onReject}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <FiX size={16} />
            Keep existing
          </button>
          <button
            type="button"
            onClick={onApprove}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700"
          >
            <FiCheck size={16} />
            Approve major changes
          </button>
        </div>
      ) : onApprove ? (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onApprove}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-700"
          >
            <FiCheck size={16} />
            Save extracted record
          </button>
        </div>
      ) : null}
    </div>
  );
}
