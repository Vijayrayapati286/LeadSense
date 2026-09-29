import { useCallback, useEffect, useRef, useState } from 'react';
import { FiBell } from 'react-icons/fi';
import { notificationService } from '../services/services';
import { formatDateTime } from '../utils/helpers';

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const rootRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await notificationService.list();
      setItems(data.items || []);
      setUnread(data.unread_count || 0);
    } catch {
      // The dashboard still works if notices cannot be loaded.
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    function onPointer(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  async function onToggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      await load();
      setLoading(false);
    }
  }

  async function onRead(item) {
    if (item.read) return;
    try {
      await notificationService.markRead(item.id);
      await load();
    } catch {
      // Leave the row unread if the request fails.
    }
  }

  async function onReadAll() {
    try {
      const { data } = await notificationService.markAllRead();
      setItems(data.items || []);
      setUnread(data.unread_count || 0);
    } catch {
      // Keep the current list if marking all read fails.
    }
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={onToggle}
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-700 transition hover:bg-slate-50 hover:border-slate-400"
      >
        <FiBell size={18} />
        {unread > 0 ? (
          <span className="absolute -right-1 -top-1 inline-flex min-w-[1.15rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-4 text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-80 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-900">Notifications</p>
            {unread > 0 ? (
              <button type="button" onClick={onReadAll} className="text-xs font-semibold text-primary-700 hover:underline">
                Mark all read
              </button>
            ) : null}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {loading && items.length === 0 ? (
              <p className="px-4 py-6 text-sm text-slate-500">Loading…</p>
            ) : items.length === 0 ? (
              <p className="px-4 py-6 text-sm text-slate-500">No notifications yet.</p>
            ) : (
              <ul>
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => onRead(item)}
                      className={`w-full px-4 py-3 text-left transition hover:bg-slate-50 ${item.read ? '' : 'bg-primary-50/60'}`}
                    >
                      <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                      <p className="mt-0.5 text-xs text-slate-600">{item.body}</p>
                      <p className="mt-1 text-[11px] text-slate-400">{formatDateTime(item.created_at)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
