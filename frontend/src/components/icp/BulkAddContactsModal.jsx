import { useEffect, useRef, useState } from 'react';
import { FiDownload, FiFile, FiPlus, FiTrash2, FiUpload } from 'react-icons/fi';
import Modal from '../ui/Modal';
import LoadingSpinner from '../ui/LoadingSpinner';
import { icpService } from '../../services/services';
import { useToast } from '../../hooks/useToast';
import { downloadBlob } from '../../utils/helpers';

const ACCEPT = '.xlsx,.xls,.xlsm,.csv,.tsv,.txt,.ods';

const TEMPLATE_CSV =
  'First Name,Last Name,Email,Phone,Company,Designation,Location,LinkedIn URL\n' +
  'Priya,Nambiar,priya@company.com,5550100001,Acme,VP of Sales,"Austin, TX",https://www.linkedin.com/in/priya-nambiar\n';

const EMPTY_ROW = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  company_name: '',
  designation: '',
  linkedin_url: '',
};

function blankRows(count = 3) {
  return Array.from({ length: count }, () => ({ ...EMPTY_ROW }));
}

function inputClassName() {
  return 'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100';
}

function rowHasValue(row) {
  return Object.values(row).some((value) => String(value || '').trim());
}

export default function BulkAddContactsModal({ isOpen, onClose, onCreated }) {
  const toast = useToast();
  const fileInputRef = useRef(null);
  const [mode, setMode] = useState('upload');
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [rows, setRows] = useState(blankRows());
  const [saving, setSaving] = useState(false);
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setMode('upload');
    setFile(null);
    setDragOver(false);
    setRows(blankRows());
    setSaving(false);
    setSummary(null);
  }, [isOpen]);

  function downloadTemplate() {
    downloadBlob(new Blob([TEMPLATE_CSV], { type: 'text/csv;charset=utf-8;' }), 'icp_contacts_template.csv');
  }

  function updateRow(index, key, value) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }

  function handleFile(next) {
    setFile(next || null);
    setSummary(null);
  }

  async function submitUpload() {
    if (!file) {
      toast.error('Choose an Excel or CSV file');
      return;
    }
    setSaving(true);
    setSummary(null);
    try {
      const result = await icpService.bulkUpload(file);
      finish(result);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to import contacts');
    } finally {
      setSaving(false);
    }
  }

  async function submitTable() {
    const contacts = rows.filter(rowHasValue);
    if (!contacts.length) {
      toast.error('Add at least one contact');
      return;
    }
    setSaving(true);
    setSummary(null);
    try {
      const result = await icpService.bulkCreate(contacts);
      finish(result);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to add contacts');
    } finally {
      setSaving(false);
    }
  }

  function finish(result) {
    setSummary(result);
    const created = result?.created || 0;
    const updated = result?.updated || 0;
    const skipped = result?.skipped || 0;
    if (created || updated) {
      toast.success(
        `${created} added${updated ? `, ${updated} updated` : ''}${skipped ? `, ${skipped} skipped` : ''}`,
      );
      onCreated?.();
    } else {
      toast.error('No contacts were added. Check skipped rows.');
    }
  }

  const skipped = (summary?.results || []).filter((row) => row.status === 'skipped');

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add bulk contacts" size="xl">
      <div className="space-y-4 -mt-2">
        <p className="text-sm text-slate-500 border-b border-slate-100 pb-4">
          Add many people to the ICP Database without LinkedIn extraction. Upload a sheet or type rows.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setMode('upload')}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
              mode === 'upload'
                ? 'border-primary-400 bg-primary-50 text-primary-800'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            Upload file
          </button>
          <button
            type="button"
            onClick={() => setMode('table')}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
              mode === 'table'
                ? 'border-primary-400 bg-primary-50 text-primary-800'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            Enter rows
          </button>
          <button
            type="button"
            onClick={downloadTemplate}
            className="ml-auto inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700 hover:text-primary-900"
          >
            <FiDownload size={14} /> Download template
          </button>
        </div>

        {mode === 'upload' ? (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
            <button
              type="button"
              onClick={() => !saving && fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                if (!saving) setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                handleFile(e.dataTransfer.files?.[0] || null);
              }}
              disabled={saving}
              className={`w-full rounded-2xl border-2 border-dashed px-5 py-8 text-left transition-colors ${
                dragOver
                  ? 'border-primary-500 bg-primary-50'
                  : file
                    ? 'border-primary-200 bg-primary-50/40'
                    : 'border-slate-200 bg-slate-50 hover:border-primary-300 hover:bg-white'
              }`}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-primary-600">
                  {file ? <FiFile size={20} /> : <FiUpload size={20} />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-900">
                    {file ? file.name : 'Drop your sheet here, or click to browse'}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Columns such as First Name, Last Name, Email, Phone, Company, Designation, and LinkedIn URL.
                  </p>
                </div>
              </div>
            </button>
          </>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-[860px] w-full text-sm">
              <thead className="bg-slate-50 text-left text-[10px] font-bold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-2 py-2">First name</th>
                  <th className="px-2 py-2">Last name</th>
                  <th className="px-2 py-2">Email</th>
                  <th className="px-2 py-2">Phone</th>
                  <th className="px-2 py-2">Company</th>
                  <th className="px-2 py-2">Designation</th>
                  <th className="px-2 py-2">LinkedIn</th>
                  <th className="w-10 px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index} className="border-t border-slate-100">
                    {['first_name', 'last_name', 'email', 'phone', 'company_name', 'designation', 'linkedin_url'].map(
                      (key) => (
                        <td key={key} className="px-2 py-1.5">
                          <input
                            className={inputClassName()}
                            value={row[key]}
                            onChange={(e) => updateRow(index, key, e.target.value)}
                          />
                        </td>
                      ),
                    )}
                    <td className="px-1 py-1.5 text-center">
                      <button
                        type="button"
                        onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        aria-label="Remove row"
                        disabled={rows.length <= 1}
                      >
                        <FiTrash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-slate-100 px-3 py-2">
              <button
                type="button"
                onClick={() => setRows((prev) => [...prev, { ...EMPTY_ROW }])}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700"
              >
                <FiPlus size={14} /> Add row
              </button>
            </div>
          </div>
        )}

        {summary ? (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <p>
              <span className="font-semibold">{summary.created}</span> added,{' '}
              <span className="font-semibold">{summary.updated}</span> updated,{' '}
              <span className="font-semibold">{summary.skipped}</span> skipped.
            </p>
            {skipped.length ? (
              <ul className="mt-2 max-h-28 space-y-1 overflow-auto text-xs text-amber-800">
                {skipped.map((row) => (
                  <li key={row.row}>
                    Row {row.row}: {row.error}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>
            Close
          </button>
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-2"
            disabled={saving}
            onClick={mode === 'upload' ? submitUpload : submitTable}
          >
            {saving ? <LoadingSpinner size="sm" /> : <FiUpload size={15} />}
            {mode === 'upload' ? 'Import contacts' : 'Add contacts'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
