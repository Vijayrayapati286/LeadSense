import { useEffect, useMemo, useState } from 'react';
import { FiCheck, FiEdit2, FiExternalLink, FiX } from 'react-icons/fi';
import { FIELDS, itemHasConflict } from './conflictUtils';

function display(value) {
  const text = value?.toString().trim();
  return text ? text : '—';
}

function buildConflicts(item) {
  if (Array.isArray(item?.conflicts)) return item.conflicts;
  return FIELDS.filter((f) => item?.[`${f.key}_match`] === false).map((f) => ({
    field: f.key,
    uploaded: item?.uploaded?.[f.key],
    extracted: item?.extracted?.[f.key],
    resolved: item?.resolved?.[f.key],
  }));
}

export default function InlineConflictReview({ item, onResolve, busy = false }) {
  const conflicts = buildConflicts(item);
  const conflictKeys = new Set(conflicts.map((c) => c.field));
  const hasConflicts = conflicts.length > 0;
  const canResolve = hasConflicts || itemHasConflict(item);
  const displayName =
    item?.extracted?.name || item?.uploaded?.name || `Row ${item?.source_row_number}`;

  const initial = useMemo(() => {
    const map = {};
    FIELDS.forEach((f) => {
      const extracted = item?.extracted?.[f.key] || '';
      const linkedInEmpty = !String(extracted).trim();
      const preferSheet = conflictKeys.has(f.key) && linkedInEmpty;
      map[f.key] = {
        resolution: preferSheet ? 'KEEP_EXISTING' : 'KEEP_EXTRACTED',
        edited_value: preferSheet ? item?.uploaded?.[f.key] || '' : extracted,
        editing: false,
      };
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.item_id, hasConflicts, conflicts.length]);

  const [decisions, setDecisions] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [openField, setOpenField] = useState(null);

  useEffect(() => {
    setDecisions(initial);
    setSaving(false);
    // Auto-open the first difference so the user can fix it immediately
    const firstDiff = FIELDS.find((f) => conflictKeys.has(f.key));
    setOpenField(firstDiff?.key ?? null);
  }, [initial]);

  const isBusy = busy || saving;

  const ready = (hasConflicts ? conflicts : FIELDS.map((f) => ({ field: f.key }))).every((c) => {
    const d = decisions[c.field];
    if (!d) return false;
    if (d.resolution === 'MANUAL_EDIT' && !String(d.edited_value || '').trim()) return false;
    return Boolean(d.resolution);
  });

  function setField(field, patch) {
    setDecisions((prev) => ({ ...prev, [field]: { ...prev[field], ...patch } }));
  }

  function chooseSource(field, resolution) {
    const source =
      resolution === 'KEEP_EXISTING' ? item?.uploaded?.[field] : item?.extracted?.[field];
    setField(field, {
      resolution,
      editing: false,
      edited_value: source || '',
    });
  }

  function startEdit(field) {
    const d = decisions[field] || {};
    const seed =
      d.edited_value ||
      (d.resolution === 'KEEP_EXISTING'
        ? item?.uploaded?.[field]
        : item?.extracted?.[field]) ||
      '';
    setField(field, {
      resolution: 'MANUAL_EDIT',
      editing: true,
      edited_value: seed,
    });
    setOpenField(field);
  }

  function chosenLabel(field) {
    const d = decisions[field];
    if (!d) return 'LinkedIn';
    if (d.resolution === 'MANUAL_EDIT' || d.editing) return 'Custom';
    if (d.resolution === 'KEEP_EXISTING') return 'Spreadsheet';
    return 'LinkedIn';
  }

  function chosenValue(field) {
    const d = decisions[field];
    if (!d) return item?.extracted?.[field];
    if (d.resolution === 'MANUAL_EDIT' || d.editing) return d.edited_value;
    if (d.resolution === 'KEEP_EXISTING') return item?.uploaded?.[field];
    return item?.extracted?.[field];
  }

  function buildPayload(overrideMap) {
    const fields = hasConflicts ? conflicts : FIELDS.map((f) => ({ field: f.key }));
    return fields.map((c) => {
      const d = overrideMap?.[c.field] || decisions[c.field];
      const row = { field: c.field, resolution: d.resolution };
      if (d.resolution === 'MANUAL_EDIT') row.edited_value = d.edited_value;
      return row;
    });
  }

  async function submit(payload) {
    setSaving(true);
    try {
      await onResolve(payload);
    } finally {
      setSaving(false);
    }
  }

  async function approve() {
    await submit(buildPayload());
  }

  const primaryLabel = hasConflicts ? 'Approve' : 'Verify';

  return (
    <div className="border-t border-gray-100 bg-white px-4 py-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{displayName}</p>
          <p className="text-xs text-gray-500">
            {hasConflicts
              ? `${conflicts.length} difference${conflicts.length === 1 ? '' : 's'} — tap a line to choose`
              : 'All fields match'}
          </p>
        </div>
        {item?.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary-600 hover:underline shrink-0"
          >
            Profile <FiExternalLink size={11} />
          </a>
        ) : null}
      </div>

      <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
        {FIELDS.map((f) => {
          const isDiff = conflictKeys.has(f.key);
          const isOpen = openField === f.key;
          const d = decisions[f.key] || {};
          const isEditing = Boolean(d.editing);
          const extractedRaw = item?.extracted?.[f.key];
          const uploadedRaw = item?.uploaded?.[f.key];
          const source =
            d.resolution === 'MANUAL_EDIT' || isEditing
              ? 'MANUAL_EDIT'
              : d.resolution === 'KEEP_EXISTING'
                ? 'KEEP_EXISTING'
                : 'KEEP_EXTRACTED';

          return (
            <div key={f.key} className={isDiff && isOpen ? 'bg-amber-50/40' : 'bg-white'}>
              {/* Compact line — always visible */}
              <button
                type="button"
                disabled={!isDiff || isBusy || !canResolve}
                onClick={() => setOpenField(isOpen ? null : f.key)}
                className={`w-full grid grid-cols-[7.5rem_1fr_auto] gap-2 items-center px-3 py-2.5 text-left ${
                  isDiff && canResolve ? 'hover:bg-gray-50 cursor-pointer' : 'cursor-default'
                } disabled:opacity-70`}
              >
                <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                  {f.label}
                </span>
                <span
                  className={`text-sm truncate ${
                    isDiff ? 'text-gray-900 font-medium' : 'text-gray-700'
                  }`}
                >
                  {display(chosenValue(f.key))}
                </span>
                <span className="shrink-0 text-[11px] font-medium">
                  {isDiff ? (
                    <span className="text-amber-700">{chosenLabel(f.key)} ▾</span>
                  ) : (
                    <span className="inline-flex items-center gap-0.5 text-emerald-600">
                      <FiCheck size={12} /> Match
                    </span>
                  )}
                </span>
              </button>

              {/* Only open the differing line — simple pick list */}
              {isDiff && isOpen ? (
                <div className="px-3 pb-3 space-y-1.5">
                  {isEditing ? (
                    <div className="space-y-1.5">
                      <textarea
                        rows={2}
                        autoFocus
                        disabled={isBusy}
                        className="w-full rounded-md border border-primary-300 bg-white px-2.5 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-200"
                        value={d.edited_value || ''}
                        onChange={(e) =>
                          setField(f.key, {
                            edited_value: e.target.value,
                            resolution: 'MANUAL_EDIT',
                            editing: true,
                          })
                        }
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => setField(f.key, { editing: false })}
                          className="text-xs font-medium text-primary-700 hover:underline"
                        >
                          Done
                        </button>
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() =>
                            chooseSource(
                              f.key,
                              String(extractedRaw || '').trim()
                                ? 'KEEP_EXTRACTED'
                                : 'KEEP_EXISTING',
                            )
                          }
                          className="inline-flex items-center gap-0.5 text-xs text-gray-500 hover:text-gray-700"
                        >
                          <FiX size={12} /> Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <button
                        type="button"
                        disabled={isBusy || !canResolve}
                        onClick={() => chooseSource(f.key, 'KEEP_EXTRACTED')}
                        className={`w-full flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition disabled:opacity-50 ${
                          source === 'KEEP_EXTRACTED'
                            ? 'bg-emerald-50 ring-1 ring-emerald-300'
                            : 'hover:bg-gray-50'
                        }`}
                      >
                        <span className="w-20 shrink-0 text-[11px] font-medium text-gray-400 pt-0.5">
                          LinkedIn
                        </span>
                        <span
                          className={`flex-1 break-words ${
                            source === 'KEEP_EXTRACTED'
                              ? 'font-medium text-emerald-900'
                              : 'text-gray-700'
                          }`}
                        >
                          {display(extractedRaw)}
                        </span>
                        {source === 'KEEP_EXTRACTED' ? (
                          <FiCheck className="shrink-0 text-emerald-600 mt-0.5" size={14} />
                        ) : null}
                      </button>

                      <button
                        type="button"
                        disabled={isBusy || !canResolve}
                        onClick={() => chooseSource(f.key, 'KEEP_EXISTING')}
                        className={`w-full flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition disabled:opacity-50 ${
                          source === 'KEEP_EXISTING'
                            ? 'bg-amber-50 ring-1 ring-amber-300'
                            : 'hover:bg-gray-50'
                        }`}
                      >
                        <span className="w-20 shrink-0 text-[11px] font-medium text-gray-400 pt-0.5">
                          Spreadsheet
                        </span>
                        <span
                          className={`flex-1 break-words ${
                            source === 'KEEP_EXISTING'
                              ? 'font-medium text-amber-900'
                              : 'text-gray-700'
                          }`}
                        >
                          {display(uploadedRaw)}
                        </span>
                        {source === 'KEEP_EXISTING' ? (
                          <FiCheck className="shrink-0 text-amber-700 mt-0.5" size={14} />
                        ) : null}
                      </button>

                      <button
                        type="button"
                        disabled={isBusy || !canResolve}
                        onClick={() => startEdit(f.key)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs text-gray-500 hover:text-primary-600"
                      >
                        <FiEdit2 size={12} /> Edit custom value
                      </button>
                    </>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {canResolve ? (
        <div className="flex items-center justify-end gap-2 pt-0.5">
          <button
            type="button"
            onClick={approve}
            disabled={isBusy || !ready}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 text-white text-sm font-medium px-4 py-2 hover:bg-primary-700 disabled:opacity-50"
          >
            <FiCheck size={15} />
            {primaryLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}
