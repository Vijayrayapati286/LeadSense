import { useEffect, useState } from 'react';
import { FiChevronDown, FiChevronRight } from 'react-icons/fi';
import Modal from '../ui/Modal';
import LoadingSpinner from '../ui/LoadingSpinner';
import { icpService } from '../../services/services';
import { useToast } from '../../hooks/useToast';

const ACCOUNT_TYPES = [
  'Prospect',
  'Customer',
  'Partner',
  'Enterprise',
  'SMB',
];

const INDUSTRIES = [
  'Banking',
  'Financial Services',
  'Technology',
  'Healthcare',
  'Manufacturing',
  'Retail',
  'Professional Services',
  'Other',
];

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'verified', label: 'Verified' },
];

export const EMPTY_ACCOUNT_FORM = {
  account_name: '',
  account_type: '',
  industry: '',
  email: '',
  website: '',
  phone: '',
  status: 'active',
  annual_revenue: '',
  employee_count: '',
  address_line: '',
  city: '',
  state: '',
  country: '',
};

function FormField({ label, required, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-xs font-medium text-slate-600">
        {label}
        {required ? <span className="text-red-500"> *</span> : null}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function inputClassName() {
  return 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100';
}

function SectionCard({ title, description, open, onToggle, children }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50/60">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-3 px-4 py-3.5 text-left"
      >
        <div>
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          {description ? <p className="mt-0.5 text-xs text-slate-500">{description}</p> : null}
        </div>
        {open ? (
          <FiChevronDown className="mt-0.5 shrink-0 text-slate-400" size={18} />
        ) : (
          <FiChevronRight className="mt-0.5 shrink-0 text-slate-400" size={18} />
        )}
      </button>
      {open ? <div className="border-t border-slate-200 px-4 pb-4 pt-3">{children}</div> : null}
    </section>
  );
}

function composeLocation(form) {
  const parts = [form.address_line, form.city, form.state, form.country].filter((p) => p?.trim());
  return parts.join(', ') || undefined;
}

function buildTags(form) {
  const tags = [];
  if (form.account_type?.trim()) tags.push(`type:${form.account_type.trim()}`);
  if (form.phone?.trim()) tags.push(`phone:${form.phone.trim()}`);
  if (form.annual_revenue?.trim()) tags.push(`revenue:${form.annual_revenue.trim()}`);
  return tags.length ? tags : undefined;
}

export default function AddAccountModal({ isOpen, onClose, onCreated }) {
  const toast = useToast();
  const [form, setForm] = useState({ ...EMPTY_ACCOUNT_FORM });
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [addressOpen, setAddressOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setForm({ ...EMPTY_ACCOUNT_FORM });
    setDetailsOpen(true);
    setAddressOpen(false);
  }, [isOpen]);

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const accountName = form.account_name?.trim();
    if (!accountName) {
      toast.error('Account name is required');
      return;
    }

    setSaving(true);
    try {
      await icpService.create({
        name: accountName,
        company_name: accountName,
        email: form.email?.trim() || undefined,
        industry: form.industry || undefined,
        company_website: form.website?.trim() || undefined,
        company_size: form.employee_count?.trim() || undefined,
        location: composeLocation(form),
        icp_status: form.status || 'active',
        tags: buildTags(form),
      });
      toast.success('Account created');
      onClose();
      onCreated?.(accountName);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create account');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add account" size="xl">
      <form onSubmit={handleSubmit} className="space-y-4 -mt-2">
        <p className="text-sm text-slate-500 border-b border-slate-100 pb-4">
          Create a client account. You will be set as the owner. Add contacts on the Contacts tab.
        </p>

        <SectionCard
          title="Account details"
          description="Core account information, assignment, and business metrics."
          open={detailsOpen}
          onToggle={() => setDetailsOpen((o) => !o)}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Account name" required className="sm:col-span-2">
              <input
                className={inputClassName()}
                placeholder="Horizon Capital — Enterprise"
                value={form.account_name}
                onChange={(e) => updateField('account_name', e.target.value)}
                required
              />
            </FormField>

            <FormField label="Account type">
              <select
                className={inputClassName()}
                value={form.account_type}
                onChange={(e) => updateField('account_type', e.target.value)}
              >
                <option value="">Select type…</option>
                {ACCOUNT_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </FormField>

            <FormField label="Industry">
              <select
                className={inputClassName()}
                value={form.industry}
                onChange={(e) => updateField('industry', e.target.value)}
              >
                <option value="">Select industry…</option>
                {INDUSTRIES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </FormField>

            <FormField label="Email">
              <input
                type="email"
                className={inputClassName()}
                placeholder="account@company.com"
                value={form.email}
                onChange={(e) => updateField('email', e.target.value)}
              />
            </FormField>

            <FormField label="Website">
              <input
                className={inputClassName()}
                placeholder="https://company.com"
                value={form.website}
                onChange={(e) => updateField('website', e.target.value)}
              />
            </FormField>

            <FormField label="Phone">
              <input
                className={inputClassName()}
                placeholder="+1 555 010 0000"
                value={form.phone}
                onChange={(e) => updateField('phone', e.target.value)}
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

            <FormField label="Annual revenue">
              <input
                className={inputClassName()}
                placeholder="5000000"
                inputMode="numeric"
                value={form.annual_revenue}
                onChange={(e) => updateField('annual_revenue', e.target.value)}
              />
            </FormField>

            <FormField label="Employee count" className="sm:col-span-2">
              <input
                className={inputClassName()}
                placeholder="250"
                inputMode="numeric"
                value={form.employee_count}
                onChange={(e) => updateField('employee_count', e.target.value)}
              />
            </FormField>
          </div>
        </SectionCard>

        <SectionCard
          title="Address"
          description="Primary business location for this account."
          open={addressOpen}
          onToggle={() => setAddressOpen((o) => !o)}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Street address" className="sm:col-span-2">
              <input
                className={inputClassName()}
                placeholder="900 Main Street"
                value={form.address_line}
                onChange={(e) => updateField('address_line', e.target.value)}
              />
            </FormField>
            <FormField label="City">
              <input
                className={inputClassName()}
                placeholder="Columbus"
                value={form.city}
                onChange={(e) => updateField('city', e.target.value)}
              />
            </FormField>
            <FormField label="State / Province">
              <input
                className={inputClassName()}
                placeholder="Mississippi"
                value={form.state}
                onChange={(e) => updateField('state', e.target.value)}
              />
            </FormField>
            <FormField label="Country" className="sm:col-span-2">
              <input
                className={inputClassName()}
                placeholder="United States"
                value={form.country}
                onChange={(e) => updateField('country', e.target.value)}
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
            Add account
          </button>
        </div>
      </form>
    </Modal>
  );
}
