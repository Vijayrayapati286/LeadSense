import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { organizationService, userService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { hasPermission, isProviderOrg } from '../utils/permissions';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function formatToday() {
  return new Date().toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

const USER_DOT = ['#ea580c', '#0f766e', '#2563eb', '#334155'];

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [userFilter, setUserFilter] = useState('all');

  const load = useCallback(async () => {
    if (!isProviderOrg(user)) return;
    setLoading(true);
    try {
      const requests = [userService.getAll().then(({ data }) => data || []).catch(() => [])];
      if (hasPermission(user, 'orgs:onboard')) {
        requests.push(organizationService.list().then(({ data }) => data || []).catch(() => []));
      } else {
        requests.push(Promise.resolve([]));
      }
      const [nextUsers, nextOrgs] = await Promise.all(requests);
      setUsers(nextUsers);
      setOrgs(nextOrgs);
    } catch {
      toast.error('Failed to load provider dashboard');
      setUsers([]);
      setOrgs([]);
    } finally {
      setLoading(false);
    }
  }, [toast, user]);

  useEffect(() => {
    load();
  }, [load, user?.org_id]);

  const filteredUsers = useMemo(() => {
    if (userFilter === 'active') return users.filter((row) => String(row.status || '').toUpperCase() === 'ACTIVE');
    if (userFilter === 'inactive') return users.filter((row) => String(row.status || '').toUpperCase() !== 'ACTIVE');
    return users;
  }, [users, userFilter]);

  const tenants = useMemo(
    () => orgs.filter((org) => String(org.type || org.org_type || '').toUpperCase() === 'TENANT'),
    [orgs],
  );
  const activeTenants = tenants.filter((org) => String(org.status || '').toUpperCase() === 'ACTIVE').length;

  if (!isProviderOrg(user)) {
    return <Navigate to="/dashboard" replace />;
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1440px] space-y-5 pb-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Provider overview</h1>
          <p className="mt-1 text-sm text-slate-500">
            Organizations and provider users only. Data as of {formatToday()}.
          </p>
        </div>
        {hasPermission(user, 'orgs:onboard') ? (
          <Link
            to="/organizations"
            className="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
          >
            Onboard tenant
          </Link>
        ) : null}
      </header>

      <div className="flex flex-wrap items-end gap-4">
        <label className="text-sm text-slate-600">
          <span className="mb-1 block">User status</span>
          <select
            className="h-9 min-w-[10.5rem] rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-slate-400"
            value={userFilter}
            onChange={(event) => setUserFilter(event.target.value)}
          >
            <option value="all">All users</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
        {userFilter !== 'all' ? (
          <button
            type="button"
            onClick={() => setUserFilter('all')}
            className="mb-1 text-sm font-medium text-slate-600 underline-offset-2 hover:underline"
          >
            Clear filters
          </button>
        ) : (
          <span className="mb-1 text-sm text-slate-400">Clear filters</span>
        )}
      </div>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="text-base font-semibold text-slate-900">Tenants</h2>
          <p className="mt-1 text-sm text-slate-500">
            {formatCount(activeTenants)} active of {formatCount(tenants.length)} tenant organizations.
          </p>
          <div className="mt-4 max-h-[22rem] overflow-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                  <th className="pb-2 pr-3 font-medium">Organization</th>
                  <th className="pb-2 px-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {tenants.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="py-10 text-center text-slate-400">No tenants yet</td>
                  </tr>
                ) : tenants.map((org, index) => (
                  <tr key={org.organization_id || org.org_id || org.id || org.name} className="border-t border-slate-100">
                    <td className="py-2.5 pr-3">
                      <span className="inline-flex items-center gap-2 text-slate-800">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: USER_DOT[index % USER_DOT.length] }}
                        />
                        {org.name}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-slate-800">{org.status || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-sm">
            <Link to="/organizations" className="font-medium text-slate-700 underline-offset-2 hover:underline">
              View organizations
            </Link>
          </p>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="text-base font-semibold text-slate-900">Provider users</h2>
          <p className="mt-1 text-sm text-slate-500">
            {formatCount(users.length)} users in the provider organization.
          </p>
          <div className="mt-4 max-h-[22rem] overflow-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                  <th className="pb-2 pr-3 font-medium">User</th>
                  <th className="pb-2 px-2 font-medium">Email</th>
                  <th className="pb-2 pl-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-10 text-center text-slate-400">No users yet</td>
                  </tr>
                ) : filteredUsers.map((row, index) => (
                  <tr key={row.id || row.email} className="border-t border-slate-100">
                    <td className="py-2.5 pr-3">
                      <span className="inline-flex items-center gap-2 text-slate-800">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: USER_DOT[index % USER_DOT.length] }}
                        />
                        {row.name}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-slate-800">{row.email || '—'}</td>
                    <td className="py-2.5 pl-2 text-slate-800">
                      {String(row.status || '').toUpperCase() === 'ACTIVE' ? 'Active' : (row.status || 'Inactive')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasPermission(user, 'members:read') ? (
            <p className="mt-4 text-sm">
              <Link to="/users" className="font-medium text-slate-700 underline-offset-2 hover:underline">
                View users
              </Link>
            </p>
          ) : null}
        </article>
      </section>
    </div>
  );
}
