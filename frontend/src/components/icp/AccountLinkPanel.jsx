import { useCallback, useEffect, useState } from 'react';
import { FiBriefcase, FiCheck, FiPlus } from 'react-icons/fi';
import { icpService } from '../../services/services';
import { useToast } from '../../hooks/useToast';

/**
 * 360-style account linker for a contact: pick an existing company bucket
 * or create a new one by setting company fields on the ICP record.
 */
export default function AccountLinkPanel({ record, onLinked }) {
  const toast = useToast();
  const hasAccount = Boolean(record?.company_name?.trim());
  const [mode, setMode] = useState('link'); // link | create
  const [accounts, setAccounts] = useState([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState('');
  const [newAccount, setNewAccount] = useState({
    company_name: '',
    industry: '',
    location: '',
    company_website: '',
    company_size: '',
  });
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(!hasAccount);

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    try {
      const data = await icpService.listAccounts({ page: 1, page_size: 200 });
      setAccounts(data.items || []);
    } catch {
      setAccounts([]);
    } finally {
      setLoadingAccounts(false);
    }
  }, []);

  useEffect(() => {
    setEditing(!record?.company_name?.trim());
    setSelectedCompany('');
    setNewAccount({
      company_name: '',
      industry: '',
      location: '',
      company_website: '',
      company_size: '',
    });
    setMode('link');
    loadAccounts();
  }, [record?.id, record?.company_name, loadAccounts]);

  async function linkExisting() {
    const name = selectedCompany?.trim();
    if (!name) {
      toast.error('Select an account');
      return;
    }
    const account = accounts.find((a) => a.company_name === name);
    setSaving(true);
    try {
      const updated = await icpService.update(record.id, {
        company_name: name,
        industry: account?.industry || record.industry || undefined,
        company_size: account?.company_size || record.company_size || undefined,
        location: account?.location || record.location || undefined,
        company_website: account?.company_website || record.company_website || undefined,
      });
      toast.success(`Linked to ${name}`);
      setEditing(false);
      onLinked?.(updated);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not link account');
    } finally {
      setSaving(false);
    }
  }

  async function createAndLink() {
    const name = newAccount.company_name?.trim();
    if (!name) {
      toast.error('Account name is required');
      return;
    }
    setSaving(true);
    try {
      const updated = await icpService.update(record.id, {
        company_name: name,
        industry: newAccount.industry?.trim() || undefined,
        location: newAccount.location?.trim() || undefined,
        company_website: newAccount.company_website?.trim() || undefined,
        company_size: newAccount.company_size?.trim() || undefined,
      });
      toast.success(`Account “${name}” created and linked`);
      setEditing(false);
      onLinked?.(updated);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not create account');
    } finally {
      setSaving(false);
    }
  }

  if (hasAccount && !editing) {
    return (
      <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-2">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Account</p>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs font-semibold text-primary-600 hover:text-primary-800"
          >
            Change
          </button>
        </div>
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
            <FiBriefcase size={18} />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">{record.company_name}</p>
            <p className="mt-0.5 text-xs text-slate-500">
              {[record.industry, record.location].filter(Boolean).join(' · ') || 'Linked account'}
            </p>
            {record.company_website ? (
              <a
                href={record.company_website}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block text-xs text-primary-600 hover:underline break-all"
              >
                {record.company_website}
              </a>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4 rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50/80 to-white p-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-amber-700">Account</p>
        <p className="mt-1 text-sm font-semibold text-slate-900">
          {hasAccount ? 'Change company link' : 'No company linked'}
        </p>
        <p className="mt-0.5 text-xs text-slate-500">
          Link this person to an existing company or create a new one. Other contact details stay as they are.
        </p>
      </div>

      <div className="flex rounded-xl border border-slate-200 bg-white p-1">
        <button
          type="button"
          onClick={() => setMode('link')}
          className={`flex-1 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
            mode === 'link' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          Link existing
        </button>
        <button
          type="button"
          onClick={() => setMode('create')}
          className={`flex-1 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
            mode === 'create' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          Create new
        </button>
      </div>

      {mode === 'link' ? (
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">Existing account</span>
            <select
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
              value={selectedCompany}
              onChange={(e) => setSelectedCompany(e.target.value)}
              disabled={loadingAccounts || saving}
            >
              <option value="">Select account…</option>
              {accounts.map((a) => (
                <option key={a.company_name} value={a.company_name}>
                  {a.company_name}
                  {a.contact_count ? ` (${a.contact_count})` : ''}
                </option>
              ))}
            </select>
          </label>
          {loadingAccounts ? (
            <p className="text-xs text-slate-400">Loading accounts…</p>
          ) : accounts.length === 0 ? (
            <p className="text-xs text-amber-800">No accounts yet — switch to Create new.</p>
          ) : null}
          <button
            type="button"
            disabled={saving || !selectedCompany}
            onClick={linkExisting}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
          >
            <FiCheck size={15} />
            {saving ? 'Linking…' : 'Link to account'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">
              Account name <span className="text-red-500">*</span>
            </span>
            <input
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
              placeholder="Acme Corp"
              value={newAccount.company_name}
              onChange={(e) => setNewAccount((p) => ({ ...p, company_name: e.target.value }))}
              disabled={saving}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-medium text-slate-600">Industry</span>
              <input
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                placeholder="Banking"
                value={newAccount.industry}
                onChange={(e) => setNewAccount((p) => ({ ...p, industry: e.target.value }))}
                disabled={saving}
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-600">Location</span>
              <input
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
                placeholder="United States"
                value={newAccount.location}
                onChange={(e) => setNewAccount((p) => ({ ...p, location: e.target.value }))}
                disabled={saving}
              />
            </label>
          </div>
          <label className="block">
            <span className="text-xs font-medium text-slate-600">Website</span>
            <input
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
              placeholder="https://company.com"
              value={newAccount.company_website}
              onChange={(e) => setNewAccount((p) => ({ ...p, company_website: e.target.value }))}
              disabled={saving}
            />
          </label>
          <button
            type="button"
            disabled={saving || !newAccount.company_name?.trim()}
            onClick={createAndLink}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
          >
            <FiPlus size={15} />
            {saving ? 'Creating…' : 'Create & link account'}
          </button>
        </div>
      )}

      {hasAccount ? (
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="w-full text-center text-xs font-medium text-slate-500 hover:text-slate-700"
        >
          Cancel
        </button>
      ) : null}
    </section>
  );
}
