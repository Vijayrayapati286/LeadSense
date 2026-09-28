import { useCallback, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { FiCopy, FiPlus } from 'react-icons/fi';
import { organizationService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { hasPermission } from '../utils/permissions';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import SurfaceCard from '../components/ui/SurfaceCard';
import Modal from '../components/ui/Modal';

function CopyField({ label, value, hint, mono = true, hideValue = false }) {
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value || '');
      toast.success(`${label} copied`);
    } catch {
      toast.error('Could not copy to clipboard');
    }
  };
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</label>
        {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
      </div>
      <div className="flex items-center gap-2">
        <code
          className={`min-w-0 flex-1 truncate rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 ${
            mono ? 'font-mono' : ''
          }`}
        >
          {hideValue ? (value ? '••••••••••••' : '—') : (value || '—')}
        </code>
        <Button type="button" variant="secondary" size="sm" onClick={copy} disabled={!value} title={`Copy ${label}`}>
          <FiCopy size={14} />
        </Button>
      </div>
    </div>
  );
}

function TypePill({ type }) {
  const t = String(type || '').toUpperCase();
  const isProvider = t === 'PROVIDER';
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        isProvider ? 'bg-amber-50 text-amber-800' : 'bg-sky-50 text-sky-700'
      }`}
    >
      {t || '—'}
    </span>
  );
}

function StatusPill({ status }) {
  const active = String(status || '').toUpperCase() === 'ACTIVE';
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
      }`}
    >
      {active ? 'Active' : status || 'Unknown'}
    </span>
  );
}

export default function OrganizationsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: '',
    owner_name: '',
    owner_email: '',
  });
  /** One-time handoff after create — never listed again on this page. */
  const [handoff, setHandoff] = useState(null);

  const loadOrgs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await organizationService.list();
      setOrgs(data || []);
    } catch {
      toast.error('Failed to load organizations');
      setOrgs([]);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!hasPermission(user, 'orgs:onboard')) return;
    loadOrgs();
  }, [user?.role, user?.org_id, user?.org_type, user?.permissions, loadOrgs]);

  if (!hasPermission(user, 'orgs:onboard')) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleCreateOrg = async (e) => {
    e.preventDefault();
    if (!createForm.name.trim() || !createForm.owner_name.trim() || !createForm.owner_email.trim()) {
      toast.error('Tenant org name, admin name, and admin email are required');
      return;
    }
    setSaving(true);
    try {
      const adminName = createForm.owner_name.trim();
      const { data } = await organizationService.create({
        name: createForm.name.trim(),
        owner_name: adminName,
        owner_email: createForm.owner_email.trim(),
        client_name: adminName,
        type: 'TENANT',
        pat_name: 'SmartOps',
      });
      setCreateOpen(false);
      setCreateForm({ name: '', owner_name: '', owner_email: '' });
      if (!data?.token?.token) {
        toast.error('Organization created but credentials were not returned');
      } else {
        setHandoff({
          name: data.name,
          client_name: data.client_name,
          type: data.type,
          organization_id: data.organization_id,
          token: data.token.token,
          owner_email: data.owner_email,
          owner_verify_url: data.owner_verify_url,
        });
      }
      await loadOrgs();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create organization');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageShell>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Onboard tenant</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Each tenant org has one admin (the client). That admin belongs only to this org and can
            add users there. We email them a verification link to set their password.
          </p>
        </div>
        <Button type="button" onClick={() => setCreateOpen(true)} className="inline-flex items-center gap-2">
          <FiPlus size={16} /> Onboard organization
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      ) : (
        <SurfaceCard className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/80 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3 font-semibold">Name</th>
                  <th className="px-5 py-3 font-semibold">Admin</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((org) => (
                  <tr key={org.organization_id} className="border-b border-slate-50">
                    <td className="px-5 py-3.5 font-medium text-slate-900">{org.name}</td>
                    <td className="px-5 py-3.5 text-slate-700">{org.client_name || '—'}</td>
                    <td className="px-5 py-3.5">
                      <TypePill type={org.type} />
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusPill status={org.status} />
                    </td>
                  </tr>
                ))}
                {!orgs.length ? (
                  <tr>
                    <td colSpan={4} className="px-5 py-14 text-center text-slate-500">
                      No organizations yet. Onboard one to get started.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      )}

      <Modal isOpen={createOpen} onClose={() => !saving && setCreateOpen(false)} title="Onboard organization">
        <form onSubmit={handleCreateOrg} className="space-y-4">
          <p className="text-sm text-slate-600">
            Creates the tenant org and its admin (the client). Access is only for this org. A
            verification email is sent so they can set a password.
          </p>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Tenant org name</label>
            <input
              className="input-field w-full"
              value={createForm.name}
              onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Deloitte"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Admin name</label>
            <input
              className="input-field w-full"
              value={createForm.owner_name}
              onChange={(e) => setCreateForm((f) => ({ ...f, owner_name: e.target.value }))}
              placeholder="e.g. Sreelatha"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Admin email</label>
            <input
              type="email"
              className="input-field w-full"
              value={createForm.owner_email}
              onChange={(e) => setCreateForm((f) => ({ ...f, owner_email: e.target.value }))}
              placeholder="admin@client.com"
              required
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" disabled={saving} onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Creating…' : 'Create'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={Boolean(handoff)}
        onClose={() => setHandoff(null)}
        title="Copy credentials once"
      >
        {handoff ? (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              <span className="font-medium text-slate-800">{handoff.name}</span> is ready.
              Admin <span className="font-medium">{handoff.client_name || handoff.owner_email}</span> got a
              verification email at <span className="font-medium">{handoff.owner_email}</span>.
            </p>
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              The PAT is not stored on this page and will not be shown again. Copy it before closing.
            </p>
            <CopyField label="Organization ID (Tenant Id)" value={handoff.organization_id} hideValue />
            <CopyField label="PAT" value={handoff.token} />
            {handoff.owner_verify_url ? (
              <CopyField label="Admin verify link" value={handoff.owner_verify_url} mono={false} />
            ) : null}
            <div className="flex justify-end">
              <Button type="button" onClick={() => setHandoff(null)}>
                Done
              </Button>
            </div>
          </div>
        ) : null}
      </Modal>
    </PageShell>
  );
}
