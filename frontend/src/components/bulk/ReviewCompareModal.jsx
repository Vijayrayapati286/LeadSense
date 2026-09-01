import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  FiAlertTriangle,
  FiCheck,
  FiChevronDown,
  FiEdit2,
  FiExternalLink,
  FiX,
} from 'react-icons/fi';
import { StatusBadge } from '../ui/GrowthWorkspace';
import { formatDateTime } from '../../utils/helpers';
import { FIELDS, itemHasConflict } from './conflictUtils';

const SHEET = 'KEEP_EXISTING';
const LINKEDIN = 'KEEP_EXTRACTED';
const MANUAL = 'MANUAL_EDIT';

function display(value) {
  const text = value?.toString().trim();
  return text ? text : '—';
}

function hasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== '';
}

function buildConflicts(item) {
  // Prefer API conflicts list when present (even if empty) so stale *_match flags are ignored.
  if (Array.isArray(item?.conflicts)) return item.conflicts;
  return FIELDS.filter((f) => item?.[`${f.key}_match`] === false).map((f) => ({
    field: f.key,
    uploaded: item?.uploaded?.[f.key],
    extracted: item?.extracted?.[f.key],
    resolved: item?.resolved?.[f.key],
  }));
}

/** One cell in the side-by-side sheets. Both columns render every field in the
 * same order so each pair lines up on a shared grid row. */
function FieldCell({ label, value, side, isDiff, selected, custom, onClick, disabled }) {
  const isSheet = side === 'sheet';
  const empty = !hasValue(value);

  let tone = 'border-transparent bg-slate-50/40';
  if (isDiff && selected) {
    tone = isSheet
      ? 'border-slate-400 bg-white ring-2 ring-slate-200'
      : 'border-primary-400 bg-primary-50/60 ring-2 ring-primary-100';
  } else if (isDiff) {
    tone = 'border-amber-200 bg-amber-50/40 hover:border-amber-300 hover:bg-amber-50';
  }

  return (
    <button
      type="button"
      disabled={disabled || !isDiff}
      onClick={onClick}
      aria-pressed={isDiff ? selected : undefined}
      className={`flex h-full w-full flex-col rounded-lg border px-3 py-2.5 text-left transition-all ${tone} ${
        isDiff && !disabled ? 'cursor-pointer' : 'cursor-default'
      } disabled:opacity-100`}
    >
      <span className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.06em] text-slate-400">
          {label}
        </span>
        {isDiff && selected ? (
          <span
            className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-white ${
              isSheet ? 'bg-slate-600' : 'bg-primary-600'
            }`}
            aria-hidden="true"
          >
            <FiCheck size={10} strokeWidth={3} />
          </span>
        ) : null}
      </span>
      <span
        className={`block break-words text-sm leading-5 ${
          empty
            ? 'italic text-slate-400'
            : isDiff
              ? 'font-medium text-slate-900'
              : 'text-slate-500'
        }`}
      >
        {empty ? 'No value' : value}
      </span>
      {custom ? (
        <span className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-primary-600">
          Replaced by custom value
        </span>
      ) : null}
    </button>
  );
}

export default function ReviewCompareModal({
  item,
  isOpen,
  onClose,
  onResolve,
  busy = false,
  position = null,
  autoAdvance = false,
}) {
  const conflicts = useMemo(() => (item ? buildConflicts(item) : []), [item]);
  const conflictKeys = useMemo(() => new Set(conflicts.map((c) => c.field)), [conflicts]);
  const hasConflicts = conflicts.length > 0;
  const canResolve = item ? hasConflicts || itemHasConflict(item) : false;
  const displayName =
    item?.extracted?.name || item?.uploaded?.name || `Row ${item?.source_row_number}`;

  const initial = useMemo(() => {
    const map = {};
    FIELDS.forEach((f) => {
      const extracted = item?.extracted?.[f.key] || '';
      const linkedInEmpty = !String(extracted).trim();
      const preferSheet = conflictKeys.has(f.key) && linkedInEmpty;
      map[f.key] = {
        resolution: preferSheet ? SHEET : LINKEDIN,
        edited_value: preferSheet ? item?.uploaded?.[f.key] || '' : extracted,
        editing: false,
      };
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.item_id, hasConflicts, conflicts.length]);

  const [decisions, setDecisions] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [editField, setEditField] = useState(null);
  const [visible, setVisible] = useState(false);
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!isOpen) {
      setVisible(false);
      return undefined;
    }
    setDecisions(initial);
    setSaving(false);
    setEditField(null);
    const frame = requestAnimationFrame(() => setVisible(true));
    const focusFrame = requestAnimationFrame(() => dialogRef.current?.focus());
    document.body.style.overflow = 'hidden';
    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(focusFrame);
      document.body.style.overflow = '';
    };
  }, [isOpen, initial]);

  const isBusy = busy || saving;

  const ready = useMemo(() => {
    const fields = hasConflicts ? conflicts : FIELDS.map((f) => ({ field: f.key }));
    return fields.every((c) => {
      const d = decisions[c.field];
      if (!d) return false;
      if (d.resolution === MANUAL && !String(d.edited_value || '').trim()) return false;
      return Boolean(d.resolution);
    });
  }, [conflicts, decisions, hasConflicts]);

  function setField(field, patch) {
    setDecisions((prev) => ({ ...prev, [field]: { ...prev[field], ...patch } }));
  }

  function chooseSource(field, resolution) {
    const source = resolution === SHEET ? item?.uploaded?.[field] : item?.extracted?.[field];
    setField(field, { resolution, editing: false, edited_value: source || '' });
    if (editField === field) setEditField(null);
  }

  function useAll(side) {
    const resolution = side === 'sheet' ? SHEET : LINKEDIN;
    const next = { ...decisions };
    FIELDS.forEach((f) => {
      if (!conflictKeys.has(f.key) && hasConflicts) {
        next[f.key] = {
          ...next[f.key],
          resolution: LINKEDIN,
          editing: false,
          edited_value: item?.extracted?.[f.key] || '',
        };
        return;
      }
      const value = resolution === SHEET ? item?.uploaded?.[f.key] : item?.extracted?.[f.key];
      next[f.key] = { resolution, editing: false, edited_value: value || '' };
    });
    setDecisions(next);
    setEditField(null);
  }

  function startEdit(field) {
    const d = decisions[field] || {};
    const seed =
      d.edited_value ||
      (d.resolution === SHEET ? item?.uploaded?.[field] : item?.extracted?.[field]) ||
      '';
    setField(field, { resolution: MANUAL, editing: true, edited_value: seed });
    setEditField(field);
  }

  function buildPayload() {
    const fields = hasConflicts ? conflicts : FIELDS.map((f) => ({ field: f.key }));
    return fields.map((c) => {
      const d = decisions[c.field];
      const row = { field: c.field, resolution: d.resolution };
      if (d.resolution === MANUAL) row.edited_value = d.edited_value;
      return row;
    });
  }

  async function approve() {
    setSaving(true);
    try {
      await onResolve(buildPayload());
      // When the parent walks a queue it decides what opens next, so closing
      // here would fight that; otherwise the dialog dismisses itself.
      if (!autoAdvance) onClose();
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape' && !isBusy) {
        onClose();
        return;
      }
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target?.tagName);
      if (typing || isBusy || !canResolve) return;
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && ready) {
        event.preventDefault();
        approve();
      } else if (event.key.toLowerCase() === 's' && hasConflicts) {
        event.preventDefault();
        useAll('sheet');
      } else if (event.key.toLowerCase() === 'l' && hasConflicts) {
        event.preventDefault();
        useAll('linkedin');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (!isOpen || !item) return null;

  const allSheet = hasConflicts && conflicts.every((c) => decisions[c.field]?.resolution === SHEET);
  const allLinkedIn =
    hasConflicts && conflicts.every((c) => decisions[c.field]?.resolution === LINKEDIN);

  // Fields whose chosen value ends up blank while the other sheet had something.
  const clearedFields = conflicts
    .map((c) => FIELDS.find((f) => f.key === c.field))
    .filter((field) => {
      if (!field) return false;
      const d = decisions[field.key];
      const chosen =
        d?.resolution === MANUAL
          ? d.edited_value
          : d?.resolution === SHEET
            ? item?.uploaded?.[field.key]
            : item?.extracted?.[field.key];
      return (
        !hasValue(chosen) &&
        (hasValue(item?.uploaded?.[field.key]) || hasValue(item?.extracted?.[field.key]))
      );
    });

  const resolvedFields = FIELDS.filter((field) => hasValue(item?.resolved?.[field.key]));
  const extractedDetails = [
    ['Headline', item?.extracted?.headline],
    ['Followers', item?.extracted?.followers],
    ['Connections', item?.extracted?.connections],
  ].filter(([, value]) => hasValue(value));
  const uploadedEntries = Object.entries(item?.uploaded_raw || {}).filter(([, value]) =>
    hasValue(value),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <div
        className={`absolute inset-0 bg-slate-900/50 backdrop-blur-[3px] transition-opacity duration-300 ${
          visible ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={() => !isBusy && onClose()}
        aria-hidden
      />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-compare-title"
        tabIndex={-1}
        className={`relative flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-[20px] border border-white/70 bg-white shadow-[0_24px_80px_-20px_rgba(15,23,42,0.45)] outline-none transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
          visible ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-4 scale-[0.97] opacity-0'
        }`}
      >
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 sm:px-7">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id="review-compare-title"
                className="truncate text-lg font-semibold tracking-[-0.01em] text-slate-900"
              >
                {displayName}
              </h2>
              {position?.total > 1 ? (
                <span className="badge badge-neutral">
                  {position.index} of {position.total}
                </span>
              ) : null}
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-slate-500">
              <span>Row {item.source_row_number}</span>
              <span aria-hidden="true">·</span>
              <StatusBadge status={item.verification_status || 'NOT_VERIFIED'} kind="verification" />
              {hasConflicts ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="font-medium text-amber-700">
                    {conflicts.length} difference{conflicts.length === 1 ? '' : 's'}
                  </span>
                </>
              ) : null}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {item?.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-primary-600 transition hover:bg-primary-50 hover:text-primary-700"
              >
                Profile <FiExternalLink size={13} />
              </a>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              disabled={isBusy}
              className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
              aria-label="Close"
            >
              <FiX size={19} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5 sm:px-7">
          {hasConflicts ? (
            <p className="text-sm text-slate-600">
              Highlighted fields differ. Click a value to keep it, or use a whole sheet.
            </p>
          ) : (
            <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 p-3.5">
              <FiCheck className="shrink-0 text-emerald-600" size={18} />
              <p className="text-sm font-medium text-emerald-900">
                Both sheets agree on every field. Verify to move this record on.
              </p>
            </div>
          )}

          {/* Two sheets, side by side. One grid keeps each field on a shared row. */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 sm:gap-x-4">
            <div
              className={`rounded-xl border px-4 py-3 transition-colors ${
                allSheet ? 'border-slate-400 bg-slate-100' : 'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Uploaded</p>
                  <p className="text-[11px] text-slate-500">From spreadsheet</p>
                </div>
                <button
                  type="button"
                  disabled={isBusy || !canResolve || !hasConflicts}
                  onClick={() => useAll('sheet')}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${
                    allSheet
                      ? 'border-slate-600 bg-slate-700 text-white'
                      : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  {allSheet ? 'Using this' : 'Use all'}
                </button>
              </div>
            </div>

            <div
              className={`rounded-xl border px-4 py-3 transition-colors ${
                allLinkedIn ? 'border-primary-300 bg-primary-100/60' : 'border-primary-100 bg-primary-50/50'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Extracted</p>
                  <p className="text-[11px] text-slate-500">From LinkedIn</p>
                </div>
                <button
                  type="button"
                  disabled={isBusy || !canResolve || !hasConflicts}
                  onClick={() => useAll('linkedin')}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${
                    allLinkedIn
                      ? 'border-primary-600 bg-primary-600 text-white'
                      : 'border-primary-200 bg-white text-primary-700 hover:bg-primary-50'
                  }`}
                >
                  {allLinkedIn ? 'Using this' : 'Use all'}
                </button>
              </div>
            </div>

            {FIELDS.map((f) => {
              const isDiff = conflictKeys.has(f.key);
              const decision = decisions[f.key];
              const custom = isDiff && decision?.resolution === MANUAL;
              return (
                <Fragment key={f.key}>
                  <FieldCell
                    label={f.label}
                    value={item?.uploaded?.[f.key]}
                    side="sheet"
                    isDiff={isDiff}
                    selected={decision?.resolution === SHEET}
                    custom={custom}
                    disabled={isBusy || !canResolve}
                    onClick={() => chooseSource(f.key, SHEET)}
                  />
                  <FieldCell
                    label={f.label}
                    value={item?.extracted?.[f.key]}
                    side="linkedin"
                    isDiff={isDiff}
                    selected={decision?.resolution === LINKEDIN}
                    custom={custom}
                    disabled={isBusy || !canResolve}
                    onClick={() => chooseSource(f.key, LINKEDIN)}
                  />
                </Fragment>
              );
            })}
          </div>

          {clearedFields.length ? (
            <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <FiAlertTriangle size={14} className="mt-0.5 shrink-0" />
              {clearedFields.map((f) => f.label).join(', ')} will be saved empty. Pick the other
              sheet or type a value to keep data.
            </p>
          ) : null}

          {/* Manual edit */}
          {canResolve && hasConflicts ? (
            <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/80 p-3.5">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
                Or type your own value
              </p>
              <div className="flex flex-wrap gap-2">
                {conflicts.map((c) => {
                  const f = FIELDS.find((x) => x.key === c.field);
                  const active = editField === c.field;
                  const isCustom = decisions[c.field]?.resolution === MANUAL;
                  return (
                    <button
                      key={c.field}
                      type="button"
                      disabled={isBusy}
                      onClick={() => startEdit(c.field)}
                      className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
                        active || isCustom
                          ? 'border-primary-300 bg-primary-50 text-primary-800'
                          : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                      }`}
                    >
                      <FiEdit2 size={11} />
                      {f?.label || c.field}
                    </button>
                  );
                })}
              </div>
              {editField ? (
                <div className="animate-slide-up-in space-y-2 pt-1">
                  <textarea
                    rows={2}
                    autoFocus
                    disabled={isBusy}
                    className="w-full rounded-lg border border-primary-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-200"
                    value={decisions[editField]?.edited_value || ''}
                    onChange={(e) =>
                      setField(editField, {
                        edited_value: e.target.value,
                        resolution: MANUAL,
                        editing: true,
                      })
                    }
                    placeholder={`Custom ${FIELDS.find((f) => f.key === editField)?.label || 'value'}`}
                  />
                  <div className="flex gap-3">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => {
                        setField(editField, { editing: false });
                        setEditField(null);
                      }}
                      className="text-xs font-semibold text-primary-700 hover:underline"
                    >
                      Done
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() =>
                        chooseSource(
                          editField,
                          hasValue(item?.extracted?.[editField]) ? LINKEDIN : SHEET,
                        )
                      }
                      className="text-xs text-slate-500 hover:text-slate-700"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {resolvedFields.length ? (
            <section className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
                <FiCheck className="text-emerald-600" /> Final resolved values
              </h3>
              <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {resolvedFields.map((field) => (
                  <div key={field.key}>
                    <dt className="text-[10px] font-bold uppercase tracking-wide text-emerald-700/60">
                      {field.label}
                    </dt>
                    <dd className="mt-0.5 text-sm font-medium text-slate-800">
                      {display(item.resolved[field.key])}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : null}

          {extractedDetails.length || hasValue(item?.extracted?.about) ? (
            <details className="group rounded-xl border border-slate-200 bg-white">
              <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-slate-600">
                <FiChevronDown
                  size={15}
                  className="text-slate-400 transition-transform group-open:rotate-180"
                />
                More LinkedIn data
              </summary>
              <div className="border-t border-slate-100 p-4">
                {extractedDetails.length ? (
                  <dl className="grid gap-3 sm:grid-cols-3">
                    {extractedDetails.map(([label, value]) => (
                      <div key={label}>
                        <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                          {label}
                        </dt>
                        <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                {hasValue(item?.extracted?.about) ? (
                  <div className={extractedDetails.length ? 'mt-3 border-t border-slate-100 pt-3' : ''}>
                    <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">About</p>
                    <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                      {item.extracted.about}
                    </p>
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}

          {uploadedEntries.length ? (
            <details className="group rounded-xl border border-slate-200 bg-white">
              <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-slate-600">
                <FiChevronDown
                  size={15}
                  className="text-slate-400 transition-transform group-open:rotate-180"
                />
                Original spreadsheet row
                <span className="badge badge-neutral ml-auto">{uploadedEntries.length} columns</span>
              </summary>
              <dl className="grid gap-x-6 gap-y-3 border-t border-slate-100 p-4 sm:grid-cols-2 lg:grid-cols-3">
                {uploadedEntries.map(([label, value]) => (
                  <div key={label} className="min-w-0">
                    <dt className="truncate text-[10px] font-bold uppercase tracking-wide text-slate-400">
                      {label}
                    </dt>
                    <dd className="mt-0.5 break-words text-sm text-slate-700">{display(value)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          ) : null}

          <details className="group rounded-xl border border-slate-200 bg-white">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-slate-600">
              <FiChevronDown
                size={15}
                className="text-slate-400 transition-transform group-open:rotate-180"
              />
              Extraction details
            </summary>
            <div className="border-t border-slate-100 p-4">
              <dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="font-bold uppercase tracking-wide text-slate-400">Extracted at</dt>
                  <dd className="mt-0.5 text-slate-700">
                    {formatDateTime(item.completed_at || item.updated_at)}
                  </dd>
                </div>
                <div>
                  <dt className="font-bold uppercase tracking-wide text-slate-400">Attempts</dt>
                  <dd className="mt-0.5 text-slate-700">{item.attempt_count || 0}</dd>
                </div>
                <div>
                  <dt className="font-bold uppercase tracking-wide text-slate-400">Match score</dt>
                  <dd className="mt-0.5 text-slate-700">{item.verification_score ?? 0}%</dd>
                </div>
                <div>
                  <dt className="font-bold uppercase tracking-wide text-slate-400">Notes</dt>
                  <dd className="mt-0.5 text-slate-700">
                    {item.resolution_summary || item.verification_reason || 'None'}
                  </dd>
                </div>
              </dl>
              {item.error ? (
                <p className="mt-3 flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
                  <FiAlertTriangle className="mt-0.5 shrink-0" /> {item.error}
                </p>
              ) : null}
            </div>
          </details>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/70 px-5 py-4 sm:px-7">
          <div className="flex items-center gap-3">
            <button type="button" onClick={onClose} disabled={isBusy} className="btn-secondary">
              Close
            </button>
            {canResolve && hasConflicts ? (
              <p className="hidden text-xs text-slate-400 sm:block">
                <kbd className="rounded border border-slate-200 bg-white px-1 font-sans">S</kbd>{' '}
                spreadsheet ·{' '}
                <kbd className="rounded border border-slate-200 bg-white px-1 font-sans">L</kbd>{' '}
                LinkedIn
              </p>
            ) : null}
          </div>
          {canResolve ? (
            <button
              type="button"
              onClick={approve}
              disabled={isBusy || !ready}
              className="btn-primary inline-flex items-center gap-2 px-5 py-2.5"
            >
              <FiCheck size={16} />
              {isBusy
                ? 'Saving…'
                : hasConflicts
                  ? autoAdvance && position?.total > 1
                    ? 'Approve & next'
                    : 'Approve'
                  : 'Verify'}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
