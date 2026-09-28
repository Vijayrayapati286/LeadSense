import { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { FiMoreVertical, FiPlus, FiSearch } from 'react-icons/fi';
import { inviteService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { hasPermission } from '../utils/permissions';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import PageShell from '../components/ui/PageShell';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';

const TABS = [
  { key: 'ALL', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'ACCEPTED', label: 'Accepted' },
  { key: 'CANCELLED', label: 'Cancelled' },
  { key: 'EXPIRED', label: 'Expired' },
];

const STATUS_PILL = {
  PENDING: 'bg-amber-50 text-amber-700 border border-amber-100',
  ACCEPTED: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  CANCELLED: 'bg-rose-50 text-rose-600 border border-rose-100',
  EXPIRED: 'bg-slate-100 text-slate-600 border border-slate-200',
};

const RESOLVED_TEXT = {
  PENDING: 'text-slate-500',
  ACCEPTED: 'text-emerald-600',
  CANCELLED: 'text-rose-600',
  EXPIRED: 'text-slate-500',
};

function formatStatusLabel(status) {
  const s = String(status || '').toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function InvitesPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('ALL');
  const [search, setSearch] = useState('');

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'USER' });

  const [resendInvite, setResendInvite] = useState(null);
  const [cancelInvite, setCancelInvite] = useState(null);
  const [menuId, setMenuId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await inviteService.list({ search: search || undefined });
      setInvites(data || []);
    } catch {
      toast.error('Failed to load invites');
    } finally {
      setLoading(false);
    }
  }, [search, toast]);

  useEffect(() => {
    if (!user?.org_id) {
      setInvites([]);
      setLoading(false);
      return;
    }
    load();
  }, [load, user?.org_id]);

  const filtered = useMemo(() => {
    if (tab === 'ALL') return invites;
    return invites.filter((row) => row.status === tab);
  }, [invites, tab]);

  if (!hasPermission(user, 'members:invite')) {
    return <Navigate to="/dashboard" replace />;
  }

  const fieldClass =
    'mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100';

  const handleInvite = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await inviteService.create(inviteForm);
      toast.success('Verification email sent');
      setInviteOpen(false);
      setInviteForm({ email: '', role: 'USER' });
      setTab('PENDING');
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create invite');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = async () => {
    if (!cancelInvite) return;
    setSaving(true);
    try {
      await inviteService.cancel(cancelInvite.id);
      toast.success('Invite cancelled');
      setCancelInvite(null);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to cancel invite');
    } finally {
      setSaving(false);
    }
  };

  const handleResend = async () => {
    if (!resendInvite) return;
    setSaving(true);
    try {
      await inviteService.resend(resendInvite.id);
      toast.success('Verification email resent');
      setResendInvite(null);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to resend invite');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageShell maxWidth="max-w-[1200px]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[2rem] font-bold tracking-tight text-slate-950">Invites</h1>
          <p className="mt-1 text-sm text-slate-500">
            Invite members into your organization ({user?.org_name || user?.org_id})
          </p>
        </div>
        <button
          type="button"
          onClick={() => setInviteOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
        >
          <FiPlus size={16} />
          Invite Member
        </button>
      </div>

      <div className="mt-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap gap-1 border-b border-slate-100 px-4 pt-3">
          {TABS.map((t) => {
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`rounded-t-lg px-4 py-2.5 text-sm font-medium transition ${
                  active
                    ? 'bg-slate-100 text-slate-900'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="border-b border-slate-100 px-4 py-3">
          <div className="relative">
            <FiSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by email..."
              className="w-full rounded-xl border border-slate-200 py-2.5 pl-10 pr-4 text-sm text-slate-900 outline-none focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
            />
          </div>
        </div>

        {loading ? (
          <div className="flex h-52 items-center justify-center">
            <LoadingSpinner size="lg" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <th className="px-5 py-3">Email</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Tenant / Hierarchy</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Invited By</th>
                  <th className="px-5 py-3">Resolved</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-5 py-16 text-center text-sm text-slate-400">
                      No invites found
                    </td>
                  </tr>
                ) : (
                  filtered.map((row) => (
                    <tr key={row.id} className="border-t border-slate-100 hover:bg-slate-50/50">
                      <td className="px-5 py-4 font-medium text-slate-900">{row.email}</td>
                      <td className="px-5 py-4 text-slate-700">{row.role === 'ADMIN' ? 'Admin' : 'User'}</td>
                      <td className="px-5 py-4 text-slate-600">{user?.org_name || 'Organization'}</td>
                      <td className="px-5 py-4">
                        <span
                          className={`inline-flex rounded-full px-3 py-0.5 text-xs font-semibold ${STATUS_PILL[row.status] || 'bg-slate-100 text-slate-600'}`}
                        >
                          {formatStatusLabel(row.status)}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-slate-700">{row.invited_by || '—'}</td>
                      <td className={`max-w-xs px-5 py-4 text-sm ${RESOLVED_TEXT[row.status] || 'text-slate-500'}`}>
                        {row.resolved_note || (row.status === 'PENDING' ? 'Awaiting response' : '—')}
                      </td>
                      <td className="relative px-5 py-4 text-right">
                        <button
                          type="button"
                          className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          onClick={() => setMenuId(menuId === row.id ? null : row.id)}
                          aria-label="Actions"
                        >
                          <FiMoreVertical size={16} />
                        </button>
                        {menuId === row.id ? (
                          <>
                            <button
                              type="button"
                              className="fixed inset-0 z-10 cursor-default"
                              aria-label="Close menu"
                              onClick={() => setMenuId(null)}
                            />
                            <div className="absolute right-5 z-20 mt-1 w-44 rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                              {row.status === 'PENDING' ? (
                                <>
                                  <button
                                    type="button"
                                    className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                                    onClick={() => {
                                      setMenuId(null);
                                      setResendInvite(row);
                                    }}
                                  >
                                    Resend email
                                  </button>
                                  <button
                                    type="button"
                                    className="block w-full px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50"
                                    onClick={() => {
                                      setMenuId(null);
                                      setCancelInvite(row);
                                    }}
                                  >
                                    Cancel invite
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  className="block w-full px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-50"
                                  onClick={() => setMenuId(null)}
                                >
                                  Close
                                </button>
                              )}
                            </div>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={inviteOpen} onClose={() => setInviteOpen(false)} title="Invite Member">
        <form className="space-y-4" onSubmit={handleInvite}>
          <label className="block text-sm font-medium text-slate-700">
            Email address
            <input
              type="email"
              required
              className={fieldClass}
              placeholder="colleague@company.com"
              value={inviteForm.email}
              onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))}
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Role
            <select
              className={fieldClass}
              value={inviteForm.role}
              onChange={(e) => setInviteForm((f) => ({ ...f, role: e.target.value }))}
            >
              <option value="USER">User</option>
              <option value="ADMIN">Admin</option>
            </select>
          </label>
          <p className="text-xs text-slate-500">
            They will be invited to <span className="font-medium">{user?.org_name || user?.org_id}</span> only.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setInviteOpen(false)}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {saving ? 'Sending…' : 'Send invite'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={Boolean(resendInvite)}
        title="Resend verification?"
        message={resendInvite ? `Send the verification email again to ${resendInvite.email}?` : ''}
        confirmText="Resend email"
        onConfirm={handleResend}
        onClose={() => setResendInvite(null)}
      />

      <ConfirmDialog
        isOpen={Boolean(cancelInvite)}
        title="Cancel invite?"
        message={cancelInvite ? `Cancel the invite for ${cancelInvite.email}?` : ''}
        confirmText="Cancel invite"
        onConfirm={handleCancel}
        onClose={() => setCancelInvite(null)}
      />
    </PageShell>
  );
}
