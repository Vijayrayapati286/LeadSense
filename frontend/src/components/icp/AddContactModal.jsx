import { useCallback, useEffect, useState } from 'react';
import { FiChevronDown, FiChevronRight } from 'react-icons/fi';
import Modal from '../ui/Modal';
import LoadingSpinner from '../ui/LoadingSpinner';
import { icpService } from '../../services/services';
import { useToast } from '../../hooks/useToast';

const ACCOUNT_NONE = '__none__';

const COUNTRY_CODES = [
  { value: '+1', label: 'US/CA (+1)' },
  { value: '+44', label: 'UK (+44)' },
  { value: '+91', label: 'India (+91)' },
  { value: '+61', label: 'Australia (+61)' },
  { value: '+49', label: 'Germany (+49)' },
  { value: '+33', label: 'France (+33)' },
];

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'verified', label: 'Verified' },
];

export const EMPTY_CONTACT_FORM = {
  company_name: '',
  first_name: '',
  last_name: '',
  designation: '',
  department: '',
  status: 'active',
  country_code: '+1',
  phone: '',
  fax: '',
  email: '',
  linkedin_url: '',
};

function FormField({ label, required, hint, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-xs font-medium text-slate-600">
        {label}
        {required ? <span className="text-red-500"> *</span> : null}
      </span>
      <div className="mt-1.5">{children}</div>
      {hint ? <p className="mt-1 text-[11px] text-slate-400">{hint}</p> : null}
    </label>
  );
}

function inputClassName() {
  return 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100';
}

function SectionCard({ title, description, open, onToggle, headerAction, children }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50/60">
      <div className="flex items-center gap-2 px-4 py-3.5">
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900">{title}</p>
            {description ? <p className="mt-0.5 text-xs text-slate-500">{description}</p> : null}
          </div>
          {open ? (
            <FiChevronDown className="shrink-0 text-slate-400" size={18} />
          ) : (
            <FiChevronRight className="shrink-0 text-slate-400" size={18} />
          )}
        </button>
        {headerAction ? <div className="shrink-0">{headerAction}</div> : null}
      </div>
      {open ? <div className="border-t border-slate-200 px-4 pb-4 pt-3">{children}</div> : null}
    </section>
  );
}

function buildTags(form) {
  const tags = [];
  if (form.department?.trim()) tags.push(`dept:${form.department.trim()}`);
  if (form.phone?.trim()) tags.push(`phone:${form.country_code || ''}${form.phone.trim()}`);
  if (form.fax?.trim()) tags.push(`fax:${form.fax.trim()}`);
  return tags.length ? tags : undefined;
}

function resolveCompanyName(form) {
  const choice = form.company_name;
  if (!choice || choice === ACCOUNT_NONE) return undefined;
  return choice.trim() || undefined;
}

export default function AddContactModal({ isOpen, onClose, onCreated, defaultCompany = '' }) {
  const toast = useToast();
  const [form, setForm] = useState({ ...EMPTY_CONTACT_FORM });
  const [accountLinkOpen, setAccountLinkOpen] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [skipAccount, setSkipAccount] = useState(false);

  const loadAccounts = useCallback(async () => {
    setAccountsLoading(true);
    try {
      const data = await icpService.listAccounts({ page: 1, page_size: 100 });
      setAccounts(data.items || []);
      return data.items || [];
    } catch (err) {
      setAccounts([]);
      toast.error(err?.response?.data?.detail || 'Failed to load accounts');
      return [];
    } finally {
      setAccountsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!isOpen) return;
    const initialCompany = defaultCompany?.trim() || '';
    setForm({
      ...EMPTY_CONTACT_FORM,
      company_name: initialCompany,
    });
    setSkipAccount(false);
    setAccountLinkOpen(true);
    setDetailsOpen(true);
    loadAccounts();
  }, [isOpen, defaultCompany, loadAccounts]);

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const firstName = form.first_name?.trim();
    const lastName = form.last_name?.trim();
    const phone = form.phone?.trim();
    const company = resolveCompanyName(form);

    if (!firstName || !lastName) {
      toast.error('First name and last name are required');
      return;
    }
    if (!phone) {
      toast.error('Phone is required');
      return;
    }

    const fullName = `${firstName} ${lastName}`.trim();
    const selectedAccount = company ? accounts.find((a) => a.company_name === company) : null;

    setSaving(true);
    try {
      await icpService.create({
        name: fullName,
        company_name: company,
        designation: form.designation?.trim() || undefined,
        email: form.email?.trim() || undefined,
        linkedin_url: form.linkedin_url?.trim() || undefined,
        icp_status: form.status || 'active',
        industry: selectedAccount?.industry || undefined,
        company_size: selectedAccount?.company_size || undefined,
        location: selectedAccount?.location || undefined,
        company_website: selectedAccount?.company_website || undefined,
        tags: buildTags(form),
      });
      toast.success('Contact created');
      onClose();
      onCreated?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create contact');
    } finally {
      setSaving(false);
    }
  }

  const withoutAccount = skipAccount || form.company_name === ACCOUNT_NONE;

  const accountOptions = (() => {
    const names = new Set(accounts.map((a) => a.company_name).filter(Boolean));
    const initial = defaultCompany?.trim();
    if (initial) names.add(initial);
    return [...names].sort((a, b) => a.localeCompare(b));
  })();

  function handleContinueWithoutAccount() {
    setSkipAccount(true);
    updateField('company_name', ACCOUNT_NONE);
    setAccountLinkOpen(true);
  }

  function handleAccountSelect(value) {
    setSkipAccount(false);
    updateField('company_name', value);
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add contact" size="xl">
      <form onSubmit={handleSubmit} className="space-y-4 -mt-2">
        <p className="text-sm text-slate-500 border-b border-slate-100 pb-4">
          Link a person to an existing account or continue without one. Full name is saved from first and last name.
        </p>

        <SectionCard
          title="Account link"
          open={accountLinkOpen}
          onToggle={() => setAccountLinkOpen((o) => !o)}
          headerAction={
            <button
              type="button"
              onClick={handleContinueWithoutAccount}
              className={`inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors whitespace-nowrap ${
                withoutAccount
                  ? 'border-primary-400 bg-primary-50 text-primary-800 shadow-sm'
                  : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50'
              }`}
            >
              Continue without account
            </button>
          }
        >
          {withoutAccount ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">
                This contact will not be linked to any account. You can add an account later from their profile.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSkipAccount(false);
                  updateField('company_name', '');
                }}
                className="text-xs font-semibold text-primary-600 hover:text-primary-800 hover:underline"
              >
                Select an account instead
              </button>
            </div>
          ) : (
            <FormField label="Account" hint="Choose the company this contact belongs to">
              <select
                className={inputClassName()}
                value={form.company_name === ACCOUNT_NONE ? '' : form.company_name}
                onChange={(e) => handleAccountSelect(e.target.value)}
                disabled={accountsLoading}
              >
                <option value="">Select account…</option>
                {accountOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              {accountsLoading ? (
                <p className="mt-1.5 text-xs text-slate-400">Loading accounts…</p>
              ) : accountOptions.length === 0 ? (
                <p className="mt-1.5 text-xs text-amber-700">
                  No accounts yet — use Continue without account, or create accounts on the Accounts page first.
                </p>
              ) : null}
            </FormField>
          )}
        </SectionCard>

        <SectionCard
          title="Contact details"
          description="Name, role, and communication preferences."
          open={detailsOpen}
          onToggle={() => setDetailsOpen((o) => !o)}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="First name" required>
              <input
                className={inputClassName()}
                placeholder="Priya"
                value={form.first_name}
                onChange={(e) => updateField('first_name', e.target.value)}
                required
              />
            </FormField>

            <FormField label="Last name" required>
              <input
                className={inputClassName()}
                placeholder="Nambiar"
                value={form.last_name}
                onChange={(e) => updateField('last_name', e.target.value)}
                required
              />
            </FormField>

            <FormField label="Designation">
              <input
                className={inputClassName()}
                placeholder="VP of Sales"
                value={form.designation}
                onChange={(e) => updateField('designation', e.target.value)}
              />
            </FormField>

            <FormField label="Department">
              <input
                className={inputClassName()}
                placeholder="Sales"
                value={form.department}
                onChange={(e) => updateField('department', e.target.value)}
              />
            </FormField>

            <FormField label="Status">
              <select
                className={inputClassName()}
                value={form.status}
                onChange={(e) => updateField('status', e.target.value)}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </FormField>

            <FormField label="Country code" required>
              <select
                className={inputClassName()}
                value={form.country_code}
                onChange={(e) => updateField('country_code', e.target.value)}
              >
                {COUNTRY_CODES.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </FormField>

            <FormField label="Phone" required hint="Enter number without country code">
              <input
                className={inputClassName()}
                placeholder="5550100001"
                inputMode="tel"
                value={form.phone}
                onChange={(e) => updateField('phone', e.target.value)}
                required
              />
            </FormField>

            <FormField label="Fax">
              <input
                className={inputClassName()}
                placeholder="+1 555 010 0002"
                value={form.fax}
                onChange={(e) => updateField('fax', e.target.value)}
              />
            </FormField>

            <FormField label="Email">
              <input
                type="email"
                className={inputClassName()}
                placeholder="priya@company.com"
                value={form.email}
                onChange={(e) => updateField('email', e.target.value)}
              />
            </FormField>

            <FormField label="LinkedIn">
              <input
                className={inputClassName()}
                placeholder="https://www.linkedin.com/in/username"
                value={form.linkedin_url}
                onChange={(e) => updateField('linkedin_url', e.target.value)}
              />
            </FormField>
          </div>
        </SectionCard>

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="btn-primary inline-flex items-center gap-2" disabled={saving}>
            {saving ? <LoadingSpinner size="sm" /> : null}
            Add contact
          </button>
        </div>
      </form>
    </Modal>
  );
}
