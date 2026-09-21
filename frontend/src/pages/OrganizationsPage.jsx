import { useCallback, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { FiCopy, FiPlus } from 'react-icons/fi';
import { organizationService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import SurfaceCard from '../components/ui/SurfaceCard';
import Modal from '../components/ui/Modal';

function CopyField({ label, value, hint, mono = true }) {
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
          {value || '—'}
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
  const [createForm, setCreateForm] = useState({ name: '', type: 'TENANT' });
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
    if (user?.role !== 'ADMIN') return;
    loadOrgs();
  }, [user?.role, user?.org_id, loadOrgs]);

  if (user?.role !== 'ADMIN') {
    return <Navigate to="/dashboard" replace />;
  }

  const handleCreateOrg = async (e) => {
    e.preventDefault();
    if (!createForm.name.trim()) {
      toast.error('Organization name is required');
      return;
    }
    setSaving(true);
    try {
      const { data } = await organizationService.create({
        name: createForm.name.trim(),
        type: createForm.type,
        pat_name: createForm.type === 'PROVIDER' ? 'Provider' : 'SmartOps',
      });
      setCreateOpen(false);
      setCreateForm({ name: '', type: 'TENANT' });
      if (!data?.token?.token) {
        toast.error('Organization created but credentials were not returned');
      } else {
        setHandoff({
          name: data.name,
          type: data.type,
          organization_id: data.organization_id,
          token: data.token.token,
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
          <h1 className="text-2xl font-semibold text-slate-900">Onboard organization</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Enter name and type (<span className="font-medium">TENANT</span> or{' '}
            <span className="font-medium">PROVIDER</span>). We create the org and a PAT automatically.
            Credentials are shown <span className="font-medium">once</span> after create — not stored on this page.
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
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Organization ID</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((org) => (
                  <tr key={org.organization_id} className="border-b border-slate-50">
                    <td className="px-5 py-3.5 font-medium text-slate-900">{org.name}</td>
                    <td className="px-5 py-3.5">
                      <TypePill type={org.type} />
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex max-w-md items-center gap-2">
                        <code className="truncate font-mono text-xs text-slate-600">{org.organization_id}</code>
                        <button
                          type="button"
                          className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          title="Copy Organization ID"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(org.organization_id);
                              toast.success('Organization ID copied');
                            } catch {
                              toast.error('Could not copy');
                            }
                          }}
                        >
                          <FiCopy size={14} />
                        </button>
                      </div>
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
            Creates the organization and issues a PAT in one step. You will copy both values once on the next screen.
          </p>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Organization name</label>
            <input
              className="input-field w-full"
              value={createForm.name}
              onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Acme Corp"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Type</label>
            <select
              className="input-field w-full"
              value={createForm.type}
              onChange={(e) => setCreateForm((f) => ({ ...f, type: e.target.value }))}
            >
              <option value="TENANT">TENANT</option>
              <option value="PROVIDER">PROVIDER</option>
            </select>
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
              <span className="font-medium text-slate-800">{handoff.name}</span> ({handoff.type}) is ready.
              Paste into SmartOps: Organization ID → <span className="font-medium">Tenant Id</span>, PAT → API token.
            </p>
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              The PAT is not stored on this page and will not be shown again. Copy it before closing.
            </p>
            <CopyField label="Organization ID (Tenant Id)" value={handoff.organization_id} />
            <CopyField label="PAT" value={handoff.token} />
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
