import { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { FiPlus, FiShield } from 'react-icons/fi';
import { rbacService, userService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { hasPermission } from '../utils/permissions';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import SurfaceCard from '../components/ui/SurfaceCard';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import SegmentedControl from '../components/ui/SegmentedControl';
import SearchInput from '../components/ui/SearchInput';

function Pill({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700',
    violet: 'bg-violet-50 text-violet-700',
    sky: 'bg-sky-50 text-sky-700',
    amber: 'bg-amber-50 text-amber-800',
    emerald: 'bg-emerald-50 text-emerald-700',
  };
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone] || tones.slate}`}>
      {children}
    </span>
  );
}

export default function RolesAccessPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState('roles');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [members, setMembers] = useState([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignForm, setAssignForm] = useState({ user_id: '', role_id: '' });
  const [removeRow, setRemoveRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rolesRes, permsRes, assignRes, usersRes] = await Promise.all([
        rbacService.listRoles(),
        rbacService.listPermissions(),
        rbacService.listAssignments(),
        userService.getAll(),
      ]);
      setRoles(rolesRes.data || []);
      setPermissions(permsRes.data || []);
      setAssignments(assignRes.data || []);
      setMembers(usersRes.data || []);
    } catch {
      toast.error('Failed to load access data');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!hasPermission(user, 'access:read')) return;
    load();
  }, [user?.role, user?.org_id, user?.permissions, load]);

  const filteredRoles = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return roles;
    return roles.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.description || '').toLowerCase().includes(q) ||
        r.role_type.toLowerCase().includes(q),
    );
  }, [roles, search]);

  const filteredPermissions = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return permissions;
    return permissions.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q),
    );
  }, [permissions, search]);

  const filteredAssignments = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return assignments;
    return assignments.filter(
      (a) =>
        (a.user_name || '').toLowerCase().includes(q) ||
        (a.user_email || '').toLowerCase().includes(q) ||
        (a.role_name || '').toLowerCase().includes(q),
    );
  }, [assignments, search]);

  if (!hasPermission(user, 'access:read')) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleAssign = async (event) => {
    event.preventDefault();
    if (!assignForm.user_id || !assignForm.role_id) {
      toast.error('Select a member and a role');
      return;
    }
    setSaving(true);
    try {
      await rbacService.assignRole({
        user_id: Number(assignForm.user_id),
        role_id: assignForm.role_id,
      });
      toast.success('Role assigned');
      setAssignOpen(false);
      setAssignForm({ user_id: '', role_id: '' });
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to assign role');
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    if (!removeRow) return;
    setSaving(true);
    try {
      await rbacService.removeAssignment(removeRow.id);
      toast.success('Assignment removed');
      setRemoveRow(null);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to remove assignment');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageShell maxWidth="max-w-[1200px]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[2rem] font-bold tracking-tight text-slate-950">Roles & access</h1>
          <p className="mt-1 text-sm text-slate-500">
            Organization-scoped LeadSense permissions (campaigns, ICP, LinkedIn extract, members).
            There is no separate tenants table —{' '}
            <span className="font-medium">{user?.org_name || 'this org'}</span> is the workspace.
          </p>
        </div>
        {tab === 'assignments' && hasPermission(user, 'access:manage') ? (
          <Button type="button" onClick={() => setAssignOpen(true)} className="inline-flex items-center gap-2">
            <FiPlus size={16} /> Assign role
          </Button>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl
          value={tab}
          onChange={(next) => {
            setTab(next);
            setSearch('');
          }}
          options={[
            { key: 'roles', label: 'Roles', count: roles.length },
            { key: 'permissions', label: 'Permissions', count: permissions.length },
            { key: 'assignments', label: 'Assignments', count: assignments.length },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder={`Search ${tab}…`} />
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      ) : (
        <SurfaceCard className="overflow-hidden p-0">
          {tab === 'roles' ? (
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/80 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3 font-semibold">Role</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Scope</th>
                  <th className="px-5 py-3 font-semibold">Invitable</th>
                  <th className="px-5 py-3 font-semibold">Permissions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRoles.map((role) => (
                  <tr key={role.id} className="border-b border-slate-50 align-top">
                    <td className="px-5 py-3.5">
                      <div className="font-medium capitalize text-slate-900">{role.name.replaceAll('_', ' ')}</div>
                      <div className="mt-0.5 text-xs text-slate-500">{role.description}</div>
                    </td>
                    <td className="px-5 py-3.5">
                      <Pill tone={role.role_type === 'access' ? 'violet' : 'sky'}>{role.role_type}</Pill>
                    </td>
                    <td className="px-5 py-3.5">
                      <Pill tone={role.scope === 'provider' ? 'amber' : 'emerald'}>{role.scope}</Pill>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">{role.is_invitable ? 'Yes' : 'No'}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {(role.permissions || []).slice(0, 8).map((name) => (
                          <code key={name} className="rounded bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-600">
                            {name}
                          </code>
                        ))}
                        {(role.permissions || []).length > 8 ? (
                          <span className="text-xs text-slate-400">+{role.permissions.length - 8} more</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredRoles.length ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-slate-500">
                      No roles match.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          ) : null}

          {tab === 'permissions' ? (
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/80 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3 font-semibold">Permission</th>
                  <th className="px-5 py-3 font-semibold">Category</th>
                  <th className="px-5 py-3 font-semibold">Description</th>
                </tr>
              </thead>
              <tbody>
                {filteredPermissions.map((perm) => (
                  <tr key={perm.id} className="border-b border-slate-50">
                    <td className="px-5 py-3.5 font-mono text-xs text-slate-800">{perm.name}</td>
                    <td className="px-5 py-3.5">
                      <Pill>{perm.category.replaceAll('_', ' ')}</Pill>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">{perm.description}</td>
                  </tr>
                ))}
                {!filteredPermissions.length ? (
                  <tr>
                    <td colSpan={3} className="px-5 py-14 text-center text-slate-500">
                      No permissions match.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          ) : null}

          {tab === 'assignments' ? (
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/80 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3 font-semibold">Member</th>
                  <th className="px-5 py-3 font-semibold">Role</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Organization</th>
                  <th className="px-5 py-3 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {filteredAssignments.map((row) => (
                  <tr key={row.id} className="border-b border-slate-50">
                    <td className="px-5 py-3.5">
                      <div className="font-medium text-slate-900">{row.user_name || '—'}</div>
                      <div className="text-xs text-slate-500">{row.user_email}</div>
                    </td>
                    <td className="px-5 py-3.5 capitalize">{(row.role_name || '').replaceAll('_', ' ')}</td>
                    <td className="px-5 py-3.5">
                      <Pill tone={row.role_type === 'access' ? 'violet' : 'sky'}>{row.role_type || '—'}</Pill>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-xs text-slate-500">{row.organization_id}</td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        type="button"
                        className="text-sm font-medium text-rose-600 hover:text-rose-700"
                        onClick={() => setRemoveRow(row)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
                {!filteredAssignments.length ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-slate-500">
                      No role assignments yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          ) : null}
        </SurfaceCard>
      )}

      <Modal isOpen={assignOpen} onClose={() => !saving && setAssignOpen(false)} title="Assign role">
        <form onSubmit={handleAssign} className="space-y-4">
          <p className="flex items-start gap-2 text-sm text-slate-600">
            <FiShield className="mt-0.5 shrink-0" />
            Grant a catalog role to a member of this organization.
          </p>
          <label className="block text-sm font-medium text-slate-700">
            Member
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100"
              value={assignForm.user_id}
              onChange={(e) => setAssignForm((f) => ({ ...f, user_id: e.target.value }))}
              required
            >
              <option value="">Select member</option>
              {members.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name} ({member.email})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Role
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100"
              value={assignForm.role_id}
              onChange={(e) => setAssignForm((f) => ({ ...f, role_id: e.target.value }))}
              required
            >
              <option value="">Select role</option>
              {roles.filter((role) => role.is_invitable).map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name} — {role.role_type} / {role.scope}
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setAssignOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Assigning…' : 'Assign'}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={Boolean(removeRow)}
        title="Remove assignment"
        message={
          removeRow
            ? `Remove ${removeRow.role_name} from ${removeRow.user_name || removeRow.user_email}?`
            : ''
        }
        confirmText="Remove"
        onClose={() => setRemoveRow(null)}
        onConfirm={handleRemove}
      />
    </PageShell>
  );
}
