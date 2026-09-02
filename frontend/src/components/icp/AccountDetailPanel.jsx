import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiCheck, FiExternalLink, FiMapPin, FiUser } from 'react-icons/fi';
import SlideOver from '../ui/SlideOver';
import LoadingSpinner from '../ui/LoadingSpinner';
import IcpRecordDetail from './IcpRecordDetail';
import { icpService } from '../../services/services';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'contacts', label: 'Contacts' },
];

function Field({ label, value, href }) {
  if (value == null || value === '') {
    return (
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-gray-400">{label}</dt>
        <dd className="mt-0.5 text-sm text-gray-400">—</dd>
      </div>
    );
  }
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900 break-words">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline inline-flex items-center gap-1">
            {value}
            <FiExternalLink size={12} />
          </a>
        ) : value}
      </dd>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 border-b border-slate-100 pb-2">
        {title}
      </p>
      <dl className="space-y-3">{children}</dl>
    </section>
  );
}

function accountSubtitle(account) {
  const parts = [account?.company_size, account?.industry].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}

function websiteHref(url) {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;
  return trimmed.startsWith('http') ? trimmed : `https://${trimmed}`;
}

export default function AccountDetailPanel({ account, isOpen, onClose }) {
  const [tab, setTab] = useState('overview');
  const [contacts, setContacts] = useState([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [selectedContact, setSelectedContact] = useState(null);

  const loadContacts = useCallback(async () => {
    if (!account?.company_name) return;
    setContactsLoading(true);
    try {
      const data = await icpService.list({
        company: account.company_name,
        limit: 100,
        sort_by: 'name',
        sort_order: 'asc',
      });
      setContacts(data.items || []);
    } catch {
      setContacts([]);
    } finally {
      setContactsLoading(false);
    }
  }, [account?.company_name]);

  useEffect(() => {
    if (!isOpen || !account) return;
    setTab('overview');
    setSelectedContact(null);
    loadContacts();
  }, [isOpen, account?.company_name, loadContacts]);

  if (!account) return null;

  const primaryContact = contacts[0] || null;
  const subtitle = accountSubtitle(account);

  return (
    <>
      <SlideOver
        isOpen={isOpen}
        onClose={onClose}
        title={account.company_name}
        subtitle={subtitle}
        width="2xl"
      >
        <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          <Field label="Type" value={account.company_size} />
          <Field label="Industry" value={account.industry} />
          <Field label="Location" value={account.location} />
          <Field label="Contacts" value={String(account.contact_count ?? contacts.length)} />
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-gray-400">Status</dt>
            <dd className="mt-0.5">
              <span className="inline-flex rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                Active
              </span>
            </dd>
          </div>
        </div>

        <div className="mb-5 flex border-b border-slate-200">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                tab === t.id
                  ? 'border-primary-600 text-primary-700'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'overview' ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Section title="Company">
                <Field
                  label="Website"
                  value={account.company_website}
                  href={websiteHref(account.company_website)}
                />
                <Field label="Industry" value={account.industry} />
                <Field label="Company size" value={account.company_size} />
                <Field label="Primary contact" value={primaryContact?.name} />
                <Field label="Primary email" value={primaryContact?.email} />
              </Section>
              <Section title="Location">
                <Field label="Location" value={account.location} />
                {account.location ? (
                  <div className="flex items-start gap-1.5 text-sm text-slate-600">
                    <FiMapPin size={14} className="mt-0.5 shrink-0" />
                    <span>{account.location}</span>
                  </div>
                ) : null}
              </Section>
            </div>

            {primaryContact?.about ? (
              <Section title="Summary">
                <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {primaryContact.about}
                </p>
              </Section>
            ) : null}

            <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <p className="text-sm text-slate-600">
                {contacts.length} {contacts.length === 1 ? 'person' : 'people'} at this account
              </p>
              <Link
                to={`/icp-contacts?company=${encodeURIComponent(account.company_name)}`}
                className="text-sm font-semibold text-primary-700 hover:underline"
              >
                View in Contacts
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {contactsLoading ? (
              <div className="py-12 text-center"><LoadingSpinner /></div>
            ) : contacts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 py-12 text-center text-sm text-slate-500">
                No contacts linked to this account yet.
                <br />
                <Link
                  to="/icp-contacts"
                  className="mt-2 inline-block font-semibold text-primary-700 hover:underline"
                >
                  Add a contact
                </Link>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                {contacts.map((person) => (
                  <li key={person.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedContact(person)}
                      className="flex w-full items-start gap-3 px-4 py-3.5 text-left hover:bg-primary-50/50 transition-colors"
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-100 text-primary-700">
                        <FiUser size={16} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-slate-900">{person.name || 'Unnamed'}</p>
                        <p className="text-sm text-slate-500">{person.designation || '—'}</p>
                        {person.email ? (
                          <p className="mt-0.5 text-sm text-primary-600">{person.email}</p>
                        ) : null}
                      </div>
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700">
                        <FiCheck size={12} />
                        {person.icp_status || 'Active'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </SlideOver>

      <IcpRecordDetail
        record={selectedContact}
        isOpen={Boolean(selectedContact)}
        onClose={() => setSelectedContact(null)}
        onSaved={(updated) => {
          setSelectedContact(updated);
          setContacts((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
        }}
      />
    </>
  );
}
