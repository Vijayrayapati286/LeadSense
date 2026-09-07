import { useEffect, useMemo, useRef, useState } from 'react';
import { FiAlertCircle, FiAlertTriangle, FiCheck, FiChevronRight, FiLoader } from 'react-icons/fi';
import ReviewCompareModal from './ReviewCompareModal';
import { itemDisplayName, itemHasConflict, isVerifiedItem, FIELDS } from './conflictUtils';

const EXIT_MS = 360;

function extractionStatus(item) {
  return (item?.extraction_status || item?.status || '').toUpperCase();
}

function isExtractedSuccess(item) {
  return extractionStatus(item) === 'SUCCESS';
}

function isInProgress(item) {
  return ['PENDING', 'QUEUED', 'PROCESSING', 'RETRY_WAIT'].includes(extractionStatus(item));
}

function isFailed(item) {
  return ['FINAL_FAILED', 'FAILED'].includes(extractionStatus(item));
}

function conflictFieldKeys(item) {
  if (Array.isArray(item?.conflicts)) return item.conflicts.map((c) => c.field);
  return FIELDS.filter((f) => item?.[`${f.key}_match`] === false).map((f) => f.key);
}

function fieldLabel(key) {
  return FIELDS.find((f) => f.key === key)?.label || key;
}

function hasText(value) {
  return value !== null && value !== undefined && String(value).trim() !== '';
}

/** Fields a bulk "keep LinkedIn" would blank out, so the confirm step can say so. */
function fieldsClearedByLinkedIn(item) {
  return conflictFieldKeys(item).filter(
    (key) => !hasText(item?.extracted?.[key]) && hasText(item?.uploaded?.[key]),
  );
}

function PendingRow({ item, selected, checked, exiting, onOpen, onToggle, busy, selectable }) {
  const hasIssue = itemHasConflict(item);
  const diffKeys = conflictFieldKeys(item);
  const displayName = itemDisplayName(item);
  const wrapRef = useRef(null);
  const [exitStyle, setExitStyle] = useState(null);

  useEffect(() => {
    if (!exiting || !wrapRef.current) return undefined;
    const el = wrapRef.current;
    const startHeight = el.scrollHeight;
    setExitStyle({ height: startHeight, opacity: 1, transform: 'translateY(0)' });
    const frame = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setExitStyle({ height: 0, opacity: 0, transform: 'translateY(-18px)' });
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [exiting]);

  return (
    <div
      ref={wrapRef}
      className={`overflow-hidden border-b border-slate-100 last:border-b-0 ${
        selected ? 'bg-primary-50/40' : ''
      }`}
      style={
        exiting
          ? {
              height: exitStyle?.height ?? 'auto',
              opacity: exitStyle?.opacity ?? 1,
              transform: exitStyle?.transform ?? 'translateY(0)',
              transition:
                'height 0.36s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.28s ease, transform 0.36s cubic-bezier(0.22, 1, 0.36, 1)',
              pointerEvents: 'none',
            }
          : undefined
      }
    >
      <div className="group flex items-center gap-1 transition-colors hover:bg-slate-50">
        {selectable ? (
          <label className="flex shrink-0 cursor-pointer items-center py-4 pl-4 pr-1">
            <input
              type="checkbox"
              checked={checked}
              onChange={onToggle}
              disabled={exiting || busy}
              aria-label={`Select ${displayName}`}
              className="h-4 w-4 cursor-pointer rounded border-slate-300 text-primary-600 focus:ring-primary-400"
            />
          </label>
        ) : null}

        <button
          type="button"
          onClick={onOpen}
          disabled={exiting || busy}
          className="flex min-w-0 flex-1 items-center gap-3 px-3 py-3 text-left disabled:opacity-70"
        >
          <span
            className={`mt-0.5 flex h-2 w-2 shrink-0 rounded-full ${
              hasIssue ? 'bg-amber-400' : 'bg-emerald-500'
            }`}
            aria-hidden="true"
          />

          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-slate-900">
              {displayName}
            </span>
          </span>

          <span className="hidden shrink-0 flex-wrap justify-end gap-1 sm:flex">
            {diffKeys.length ? (
              diffKeys.slice(0, 3).map((key) => (
                <span key={key} className="badge badge-warning">
                  {fieldLabel(key)}
                </span>
              ))
            ) : (
              <span className="badge badge-success">Match</span>
            )}
            {diffKeys.length > 3 ? (
              <span className="badge badge-neutral">+{diffKeys.length - 3}</span>
            ) : null}
          </span>

          <FiChevronRight
            size={16}
            className="shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-500"
            aria-hidden="true"
          />
        </button>
      </div>
    </div>
  );
}

function ProgressRow({ item }) {
  const displayName = itemDisplayName(item);
  const failed = isFailed(item);
  return (
    <div className="flex animate-slide-up-in items-center gap-3 border-b border-slate-100 bg-slate-50/60 px-4 py-2.5">
      {failed ? (
        <span className="badge badge-danger">Failed</span>
      ) : (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-primary-600">
          <FiLoader className="animate-spin" size={12} /> Extracting…
        </span>
      )}
      <span className="min-w-0 truncate text-sm font-medium text-slate-900">{displayName}</span>
    </div>
  );
}

function VerifiedRow({ item, animateIn }) {
  const name = itemDisplayName(item);
  const status = (item.verification_status || '').toUpperCase();

  return (
    <div
      className={`flex items-center gap-2.5 border-b border-slate-100 px-4 py-3 last:border-b-0 ${
        animateIn ? 'animate-slide-up-in' : ''
      }`}
    >
      <FiCheck className="shrink-0 text-emerald-600" size={15} />
      <span className="flex-1 truncate text-sm font-medium text-slate-900">{name}</span>
      <span className="badge badge-success shrink-0">
        {status === 'RESOLVED' ? 'Resolved' : 'Verified'}
      </span>
    </div>
  );
}

export default function ExtractionReviewPanel({
  items = [],
  busy = false,
  onResolve,
  onBulkResolve,
  emptyMessage = 'No records to review yet.',
  showInProgress = true,
}) {
  const [activeId, setActiveId] = useState(null);
  const [exitingId, setExitingId] = useState(null);
  const [freshVerified, setFreshVerified] = useState(() => new Set());
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [pendingBulk, setPendingBulk] = useState(null);
  const exitTimerRef = useRef(null);

  const { pending, verified, progress } = useMemo(() => {
    const successItems = items.filter(isExtractedSuccess);
    return {
      pending: successItems.filter((item) => !isVerifiedItem(item)),
      verified: successItems.filter(isVerifiedItem),
      progress: showInProgress ? items.filter((item) => isInProgress(item) || isFailed(item)) : [],
    };
  }, [items, showInProgress]);

  const activeIndex = useMemo(
    () => pending.findIndex((p) => p.item_id === activeId),
    [pending, activeId],
  );
  const activeItem = activeIndex >= 0 ? pending[activeIndex] : null;
  const selectable = Boolean(onBulkResolve);

  useEffect(() => {
    return () => {
      if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
    };
  }, []);

  // Drop selections for rows that left the queue.
  useEffect(() => {
    setSelectedIds((prev) => {
      const alive = new Set(pending.map((p) => p.item_id));
      const next = new Set([...prev].filter((id) => alive.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [pending]);

  useEffect(() => {
    if (activeId && !pending.some((p) => p.item_id === activeId) && !exitingId) {
      setActiveId(null);
    }
  }, [pending, activeId, exitingId]);

  function openRow(itemId) {
    if (exitingId) return;
    setActiveId(itemId);
  }

  function closeModal() {
    if (exitingId || busy) return;
    setActiveId(null);
  }

  function toggleRow(itemId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  function toggleAll() {
    setSelectedIds((prev) =>
      prev.size === pending.length ? new Set() : new Set(pending.map((p) => p.item_id)),
    );
  }

  async function handleResolve(item, decisions) {
    if (exitingId) return;

    // Work out the next record before the queue shifts, so approving can walk
    // the user straight into it instead of dumping them back on the list.
    const index = pending.findIndex((p) => p.item_id === item.item_id);
    const nextItem = index >= 0 ? pending[index + 1] || pending[index - 1] || null : null;

    try {
      await onResolve(item, decisions);
      setActiveId(nextItem ? nextItem.item_id : null);
      setExitingId(item.item_id);
      setFreshVerified((prev) => new Set(prev).add(item.item_id));
      await new Promise((resolve) => {
        exitTimerRef.current = setTimeout(resolve, EXIT_MS);
      });
    } catch (err) {
      setActiveId(item.item_id);
      throw err;
    } finally {
      setExitingId(null);
    }
  }

  async function runBulk(side) {
    const ids = [...selectedIds];
    if (!ids.length) return;
    const resolution = side === 'linkedin' ? 'KEEP_EXTRACTED' : 'KEEP_EXISTING';
    const decisions = FIELDS.map((f) => ({ field: f.key, resolution }));
    try {
      await onBulkResolve(ids, decisions);
      setSelectedIds(new Set());
      setPendingBulk(null);
    } catch {
      // Keep the selection intact so the user can retry after a failure.
      setPendingBulk(null);
    }
  }

  const selectedItems = pending.filter((p) => selectedIds.has(p.item_id));
  const clearingCount =
    pendingBulk === 'linkedin'
      ? selectedItems.filter((p) => fieldsClearedByLinkedIn(p).length > 0).length
      : 0;

  const hasAny = pending.length + verified.length + progress.length > 0;

  if (!hasAny) {
    return (
      <div className="empty-state">
        <span className="empty-state-icon">
          <FiCheck size={22} />
        </span>
        <p className="mt-4 text-sm font-semibold text-slate-800">Review queue is clear</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <>
      <div className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">Records to review</p>
            <p className="text-xs text-slate-500">
              Open a record to compare values, or select several to resolve at once.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="badge badge-warning">
              <FiAlertCircle size={12} /> {pending.length} open
            </span>
            <span className="badge badge-success">
              <FiCheck size={12} /> {verified.length} verified
            </span>
          </div>
        </div>

        {selectable && selectedIds.size > 0 ? (
          <div className="animate-slide-up-in border-b border-primary-100 bg-primary-50/70 px-4 py-3">
            {pendingBulk ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-slate-700">
                  Apply{' '}
                  <span className="font-semibold">
                    {pendingBulk === 'linkedin' ? 'LinkedIn' : 'spreadsheet'}
                  </span>{' '}
                  values to {selectedIds.size} record{selectedIds.size === 1 ? '' : 's'}?
                  {clearingCount > 0 ? (
                    <span className="mt-1 flex items-center gap-1.5 text-xs font-medium text-amber-700">
                      <FiAlertTriangle size={13} />
                      {clearingCount} record{clearingCount === 1 ? '' : 's'} would have a field
                      cleared because LinkedIn returned no value.
                    </span>
                  ) : null}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPendingBulk(null)}
                    disabled={busy}
                    className="btn-secondary py-1.5 text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => runBulk(pendingBulk)}
                    disabled={busy}
                    className="btn-primary py-1.5 text-xs"
                  >
                    {busy ? 'Applying…' : 'Confirm'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm font-semibold text-slate-800">
                  {selectedIds.size} selected
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPendingBulk('sheet')}
                    disabled={busy}
                    className="btn-secondary py-1.5 text-xs"
                  >
                    Keep spreadsheet
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingBulk('linkedin')}
                    disabled={busy}
                    className="btn-secondary py-1.5 text-xs"
                  >
                    Keep LinkedIn
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedIds(new Set())}
                    className="px-2 py-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800"
                  >
                    Clear
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {pending.length > 0 && selectable ? (
          <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50/80 px-4 py-2">
            <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <input
                type="checkbox"
                checked={selectedIds.size === pending.length && pending.length > 0}
                onChange={toggleAll}
                className="h-4 w-4 cursor-pointer rounded border-slate-300 text-primary-600 focus:ring-primary-400"
              />
              Select all
            </label>
          </div>
        ) : null}

        <div className="max-h-[440px] overflow-y-auto">
          {pending.map((item) => (
            <PendingRow
              key={item.item_id}
              item={item}
              selected={activeId === item.item_id}
              checked={selectedIds.has(item.item_id)}
              exiting={exitingId === item.item_id}
              onOpen={() => openRow(item.item_id)}
              onToggle={() => toggleRow(item.item_id)}
              busy={busy || Boolean(exitingId)}
              selectable={selectable}
            />
          ))}

          {progress.map((item) => (
            <ProgressRow key={`p-${item.item_id}`} item={item} />
          ))}

          {pending.length === 0 && progress.length === 0 ? (
            <div className="animate-slide-up-in border-b border-slate-100 px-4 py-4 text-center text-sm text-slate-500">
              All extracted records verified — see below.
            </div>
          ) : null}
        </div>

        <div className="border-t border-slate-200">
          <div className="bg-emerald-50/70 px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-emerald-700">
            Verified
            {verified.length > 0 ? (
              <span className="ml-2 font-medium normal-case text-emerald-600/70">
                ({verified.length})
              </span>
            ) : null}
          </div>
          {verified.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-slate-400">
              Resolved records will appear here.
            </div>
          ) : (
            <div className="max-h-[240px] overflow-y-auto">
              {verified.map((item) => (
                <VerifiedRow
                  key={item.item_id}
                  item={item}
                  animateIn={freshVerified.has(item.item_id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <ReviewCompareModal
        item={activeItem}
        isOpen={Boolean(activeItem)}
        onClose={closeModal}
        busy={busy || Boolean(exitingId)}
        autoAdvance
        position={{ index: activeIndex + 1, total: pending.length }}
        onResolve={(decisions) => handleResolve(activeItem, decisions)}
      />
    </>
  );
}
