import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { FiPlus, FiUsers } from 'react-icons/fi';
import { userService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import SurfaceCard from '../components/ui/SurfaceCard';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import SearchInput from '../components/ui/SearchInput';

const EMPTY_CREATE = {
  name: '',
  email: '',
  password: '',
  role: 'USER',
  department: 'Sales',
  status: 'ACTIVE',
};

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase();
}

function RolePill({ role }) {
  const isAdmin = role === 'ADMIN';
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        isAdmin ? 'bg-violet-50 text-violet-700' : 'bg-sky-50 text-sky-700'
      }`}
    >
      {isAdmin ? 'Admin' : 'User'}
    </span>
  );
}

export default function UsersPage() {
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState(EMPTY_CREATE);
  const [roleUser, setRoleUser] = useState(null);
  const [nextRole, setNextRole] = useState('USER');
  const [statusUser, setStatusUser] = useState(null);
  const [deleteUser, setDeleteUser] = useState(null);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await userService.getAll();
      setUsers(data || []);
    } catch {
      toast.error('Failed to load members');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  // Reload whenever the signed-in tenant changes (e.g. switch admin login)
  useEffect(() => {
    if (!user?.org_id) {
      setUsers([]);
      setLoading(false);
      return;
    }
    loadUsers();
  }, [user?.org_id, loadUsers]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        (u.name || '').toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q) ||
        (u.role || '').toLowerCase().includes(q),
    );
  }, [users, search]);

  if (user?.role !== 'ADMIN') {
    return <Navigate to="/dashboard" replace />;
  }

  const fieldClass =
    'mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100';

  const handleCreate = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await userService.create(createForm);
      toast.success('Member added');
      setCreateOpen(false);
      setCreateForm(EMPTY_CREATE);
      await loadUsers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to add member');
    } finally {
      setSaving(false);
    }
  };

  const handleChangeRole = async () => {
    if (!roleUser) return;
    setSaving(true);
    try {
      await userService.update(roleUser.id, { role: nextRole });
      toast.success('Role updated');
      setRoleUser(null);
      await loadUsers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to change role');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!statusUser) return;
    const next = statusUser.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    setSaving(true);
    try {
      await userService.updateStatus(statusUser.id, next);
      toast.success(next === 'ACTIVE' ? 'Member activated' : 'Member deactivated');
      setStatusUser(null);
      await loadUsers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to update status');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteUser) return;
    setSaving(true);
    try {
      await userService.remove(deleteUser.id);
      toast.success('Member removed');
      setDeleteUser(null);
      await loadUsers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to remove member');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageShell maxWidth="max-w-[1200px]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[2rem] font-bold tracking-tight text-slate-950">Members</h1>
          <p className="mt-1 text-sm text-slate-500">
            {users.length} member{users.length === 1 ? '' : 's'} in{' '}
            {user?.org_name || user?.org_id || 'your organization'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50"
          >
            <FiPlus size={16} />
            Add User
          </button>
          <button
            type="button"
            onClick={() => navigate('/invites')}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
          >
            <FiPlus size={16} />
            Invite Member
          </button>
        </div>
      </div>

      <div className="mt-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3">
          <SearchInput value={search} onChange={setSearch} placeholder="Search members..." />
        </div>
        <div className="overflow-hidden p-0">
        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <LoadingSpinner size="lg" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-100 text-xs font-semibold uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Org Role</th>
                  <th className="px-5 py-3">Department</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-slate-400">
                      <FiUsers className="mx-auto mb-2" size={22} />
                      No members found
                    </td>
                  </tr>
                ) : (
                  filtered.map((row) => {
                    const isSelf = row.id === user?.id;
                    return (
                      <tr key={row.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                              {initials(row.name)}
                            </span>
                            <div className="min-w-0">
                              <p className="truncate font-semibold text-slate-900">
                                {row.name}
                                {isSelf ? <span className="ml-1.5 text-xs font-normal text-slate-400">(you)</span> : null}
                              </p>
                              <p className="truncate text-xs text-slate-500">{row.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4"><RolePill role={row.role} /></td>
                        <td className="px-5 py-4 text-slate-600">{row.department || '—'}</td>
                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                              row.status === 'ACTIVE'
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-slate-100 text-slate-500'
                            }`}
                          >
                            {row.status === 'ACTIVE' ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-sm">
                            <button
                              type="button"
                              className="font-medium text-primary-600 hover:text-primary-700"
                              onClick={() => {
                                setRoleUser(row);
                                setNextRole(row.role === 'ADMIN' ? 'USER' : 'ADMIN');
                              }}
                            >
                              Change Role
                            </button>
                            <button
                              type="button"
                              className="font-medium text-rose-600 hover:text-rose-700 disabled:opacity-40"
                              disabled={isSelf}
                              onClick={() => setStatusUser(row)}
                            >
                              {row.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}
                            </button>
                            <button
                              type="button"
                              className="font-medium text-rose-600 hover:text-rose-700 disabled:opacity-40"
                              disabled={isSelf}
                              onClick={() => setDeleteUser(row)}
                            >
                              Remove
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-400">
        Need to invite someone by email first?{' '}
        <Link to="/invites" className="font-medium text-primary-600 hover:underline">Go to Invites</Link>
      </p>

      <Modal isOpen={createOpen} onClose={() => setCreateOpen(false)} title="Add User">
        <form className="space-y-4" onSubmit={handleCreate}>
          <label className="block text-sm font-medium text-slate-700">
            Name
            <input className={fieldClass} required value={createForm.name} onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))} />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Email
            <input type="email" className={fieldClass} required value={createForm.email} onChange={(e) => setCreateForm((f) => ({ ...f, email: e.target.value }))} />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Password
            <input type="password" className={fieldClass} required minLength={8} value={createForm.password} onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm font-medium text-slate-700">
              Role
              <select className={fieldClass} value={createForm.role} onChange={(e) => setCreateForm((f) => ({ ...f, role: e.target.value }))}>
                <option value="USER">User</option>
                <option value="ADMIN">Admin</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Department
              <input className={fieldClass} value={createForm.department} onChange={(e) => setCreateForm((f) => ({ ...f, department: e.target.value }))} />
            </label>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Add User</Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={Boolean(roleUser)} onClose={() => setRoleUser(null)} title="Change Role" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Change role for <span className="font-semibold text-slate-900">{roleUser?.name}</span>
          </p>
          <select className={fieldClass} value={nextRole} onChange={(e) => setNextRole(e.target.value)}>
            <option value="USER">User</option>
            <option value="ADMIN">Admin</option>
          </select>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setRoleUser(null)}>Cancel</Button>
            <Button loading={saving} onClick={handleChangeRole}>Save</Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={Boolean(statusUser)}
        title={statusUser?.status === 'ACTIVE' ? 'Deactivate member?' : 'Activate member?'}
        message={
          statusUser?.status === 'ACTIVE'
            ? `${statusUser?.name} will no longer be able to sign in.`
            : `${statusUser?.name} will be able to sign in again.`
        }
        confirmText={statusUser?.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}
        variant={statusUser?.status === 'ACTIVE' ? 'danger' : 'primary'}
        onConfirm={handleToggleStatus}
        onClose={() => setStatusUser(null)}
      />

      <ConfirmDialog
        isOpen={Boolean(deleteUser)}
        title="Remove member?"
        message={deleteUser ? `Remove ${deleteUser.name} (${deleteUser.email})? This cannot be undone.` : ''}
        confirmText="Remove"
        onConfirm={handleDelete}
        onClose={() => setDeleteUser(null)}
      />
    </PageShell>
  );
}
