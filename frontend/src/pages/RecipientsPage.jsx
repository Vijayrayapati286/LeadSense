import { useState, useCallback, useEffect } from 'react';
import {
  FiUpload, FiDownload, FiSave, FiUserPlus, FiTag, FiCheckSquare,
  FiSettings, FiTrash2, FiEdit2,
} from 'react-icons/fi';
import { recipientService, recipientGroupService, tagService, savedSearchService } from '../services/services';
import { useToast } from '../hooks/useToast';
import { useContactSearch } from '../hooks/useContactSearch';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import StatusBadge from '../components/ui/StatusBadge';
import UploadErrorModal from '../components/ui/UploadErrorModal';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import { MetricCard } from '../components/ui/GrowthWorkspace';
import FilterBuilder, { RESPONSE_TAGS } from '../components/FilterBuilder';
import { debounce, getMissingUploadColumns, buildDuplicateUploadMessage } from '../utils/helpers';

// Extensions accepted by the prospect-list upload input — mirrors the
// backend's SUPPORTED_EXTENSIONS in excel_service.py.
const UPLOAD_ACCEPT = '.xlsx,.xlsm,.xls,.xlsb,.ods,.csv,.tsv,.txt';

const RESPONSE_TAG_COLORS = {
  Cold: 'bg-blue-50 text-blue-700',
  Negative: 'bg-red-50 text-red-700',
  Warm: 'bg-amber-50 text-amber-700',
  Hot: 'bg-green-50 text-green-700',
};

export default function RecipientsPage() {
  const toast = useToast();
  const {
    search, setSearch, sortBy, setSortBy, sortOrder, setSortOrder,
    activeFieldKeys, filterValues, distinctOptions, distinctLoading,
    results, total, page, setPage, loading, activeParams,
    groups, tags, campaigns, loadGroups, loadTags,
    handleAddField, handleRemoveField, handleValueChange, clearAllFilters,
    refreshActiveDistinctOptions, loadSavedSearchFilters, loadResults,
  } = useContactSearch({ toast });

  // Upload
  const [uploading, setUploading] = useState(false);
  const [uploadGroupName, setUploadGroupName] = useState('');
  const [uploadMissingColumns, setUploadMissingColumns] = useState(null);
  const [pendingDuplicateUpload, setPendingDuplicateUpload] = useState(null);

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectingAll, setSelectingAll] = useState(false);
  const [savedSearches, setSavedSearches] = useState([]);

  // Modals
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [targetGroupId, setTargetGroupId] = useState('');
  const [newGroupName, setNewGroupName] = useState('');
  const [tagModalOpen, setTagModalOpen] = useState(false);
  const [targetTagId, setTargetTagId] = useState('');
  const [newTagName, setNewTagName] = useState('');
  const [manageModalOpen, setManageModalOpen] = useState(false);
  const [renamingGroupId, setRenamingGroupId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [deletingGroup, setDeletingGroup] = useState(null);
  const [deletingTag, setDeletingTag] = useState(null);

  useEffect(() => {
    savedSearchService.getAll().then(({ data }) => setSavedSearches(data)).catch(() => {});
  }, []);

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleSelectAllMatching = async () => {
    setSelectingAll(true);
    try {
      const { data } = await recipientService.searchIds(activeParams);
      setSelectedIds(new Set(data.ids));
      toast.success(`Selected all ${data.total} matching prospect(s) — duplicates across overlapping filters are automatically merged`);
    } catch {
      toast.error('Failed to select all matching prospects');
    } finally {
      setSelectingAll(false);
    }
  };

  const performUpload = async (file, groupName, confirm = false) => {
    setUploading(true);
    try {
      const { data } = await recipientService.uploadExcel(file, groupName, undefined, undefined, confirm);
      if (data.requires_confirmation) {
        setPendingDuplicateUpload({ file, groupName, total: data.total, duplicateCount: data.duplicate_count });
        return;
      }
      toast.success(data.message);
      setUploadGroupName('');
      loadResults();
      loadGroups();
      refreshActiveDistinctOptions();
    } catch (err) {
      const missingColumns = getMissingUploadColumns(err);
      if (missingColumns) {
        setUploadMissingColumns(missingColumns);
      } else {
        const detail = err.response?.data?.detail;
        toast.error((typeof detail === 'string' && detail) || 'Upload failed');
      }
    } finally {
      setUploading(false);
    }
  };

  const handleUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!uploadGroupName.trim()) {
      toast.error('Name this list before uploading — it makes the list identifiable and reusable later');
      e.target.value = '';
      return;
    }
    e.target.value = '';
    performUpload(file, uploadGroupName.trim());
  };

  const handleConfirmDuplicateUpload = () => {
    if (!pendingDuplicateUpload) return;
    const { file, groupName } = pendingDuplicateUpload;
    performUpload(file, groupName, true);
  };

  const handleExport = async () => {
    try {
      const response = await recipientService.export(activeParams);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'prospects_export.csv';
      link.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error('Export failed');
    }
  };

  const handleSaveSearch = async () => {
    if (!saveName.trim()) {
      toast.error('Enter a name for this search');
      return;
    }
    try {
      await savedSearchService.create({ name: saveName, filters: activeParams });
      toast.success('Search saved');
      setSaveModalOpen(false);
      setSaveName('');
      const { data } = await savedSearchService.getAll();
      setSavedSearches(data);
    } catch {
      toast.error('Failed to save search');
    }
  };

  const loadSavedSearch = (saved) => {
    loadSavedSearchFilters(saved.filters);
    toast.success(`Loaded "${saved.name}"`);
  };

  const handleAddToGroup = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    try {
      let groupId = targetGroupId;
      if (!groupId && newGroupName.trim()) {
        const { data } = await recipientGroupService.create({ name: newGroupName.trim() });
        groupId = data.id;
      }
      if (!groupId) {
        toast.error('Choose or create a group');
        return;
      }
      await recipientGroupService.addMembers(groupId, ids);
      toast.success(`Added ${ids.length} prospect(s) to group`);
      setGroupModalOpen(false);
      setTargetGroupId('');
      setNewGroupName('');
      setSelectedIds(new Set());
      loadGroups();
    } catch {
      toast.error('Failed to add to group');
    }
  };

  const handleAssignTag = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    try {
      let tagId = targetTagId;
      if (!tagId && newTagName.trim()) {
        const { data } = await tagService.create({ name: newTagName.trim() });
        tagId = data.id;
      }
      if (!tagId) {
        toast.error('Choose or create a tag');
        return;
      }
      await tagService.assign(tagId, ids);
      toast.success(`Tagged ${ids.length} prospect(s)`);
      setTagModalOpen(false);
      setTargetTagId('');
      setNewTagName('');
      setSelectedIds(new Set());
      loadTags();
    } catch {
      toast.error('Failed to assign tag');
    }
  };

  const handleRenameGroup = async (groupId) => {
    try {
      await recipientGroupService.update(groupId, { name: renameValue });
      setRenamingGroupId(null);
      loadGroups();
    } catch {
      toast.error('Failed to rename group');
    }
  };

  const handleDeleteGroup = async () => {
    try {
      await recipientGroupService.delete(deletingGroup.id);
      toast.success('Group deleted');
      loadGroups();
    } catch {
      toast.error('Failed to delete group');
    }
  };

  const handleDeleteTag = async () => {
    try {
      await tagService.delete(deletingTag.id);
      toast.success('Tag deleted');
      loadTags();
    } catch {
      toast.error('Failed to delete tag');
    }
  };

  const handleInlineResponseTag = async (recipientId, tag) => {
    try {
      const { data } = await recipientService.tagResponse([recipientId], tag);
      if (data.suppressed > 0) toast.success(`Tagged as ${tag} — auto-suppressed (blacklisted)`);
      else toast.success(`Tagged as ${tag}`);
      loadResults();
    } catch {
      toast.error('Failed to tag response');
    }
  };

  const handleBulkResponseTag = async (tag) => {
    const ids = [...selectedIds];
    if (ids.length === 0 || !tag) return;
    try {
      const { data } = await recipientService.tagResponse(ids, tag);
      toast.success(
        data.suppressed > 0
          ? `Tagged ${data.tagged} prospect(s) as ${tag} — ${data.suppressed} auto-suppressed`
          : `Tagged ${data.tagged} prospect(s) as ${tag}`
      );
      setSelectedIds(new Set());
      loadResults();
    } catch {
      toast.error('Failed to tag response');
    }
  };

  return (
    <PageShell maxWidth="max-w-[1440px]">
      <PageHeader
        eyebrow="Lead generation"
        title="Prospects"
        subtitle="Search, filter, and organize every prospect — individually, by group, by tag, or with any combination of filters."
        actions={
        <div className="flex items-center gap-2">
          <input
            className="control w-48"
            placeholder="List name *"
            title="Required — names this list so it's identifiable and reusable in future campaigns"
            value={uploadGroupName}
            onChange={(e) => setUploadGroupName(e.target.value)}
          />
          <label className="btn-primary flex items-center gap-2 cursor-pointer">
            {uploading ? <LoadingSpinner size="sm" /> : <FiUpload size={18} />}
            Upload Excel
            <input type="file" accept={UPLOAD_ACCEPT} onChange={handleUpload} className="hidden" />
          </label>
          <button onClick={() => setManageModalOpen(true)} className="btn-secondary flex items-center gap-2" title="Manage groups & tags">
            <FiSettings size={16} />
          </button>
        </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Matching prospects" value={total} hint="Current result set" icon={FiUserPlus} />
        <MetricCard label="Selected" value={selectedIds.size} hint="Ready for bulk action" tone="green" icon={FiCheckSquare} />
        <MetricCard label="Filters applied" value={activeFieldKeys.length} hint="Narrowing results" tone="amber" icon={FiTag} />
      </div>

      <div className="surface-card space-y-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <SearchInput
            onChange={debouncedSearch}
            placeholder="Quick search (name, email, company)..."
            className="flex-1 min-w-[240px]"
          />
          <select className="input-field w-auto" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            <option value="name">Sort: Name</option>
            <option value="email">Sort: Email</option>
            <option value="company">Sort: Company</option>
            <option value="designation">Sort: Designation</option>
            <option value="industry">Sort: Industry</option>
            <option value="department">Sort: Department</option>
            <option value="created_at">Sort: Date Added</option>
          </select>
          <select className="input-field w-auto" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
        </div>

        <div className="pt-2 border-t border-gray-100">
          <FilterBuilder
            activeFieldKeys={activeFieldKeys}
            values={filterValues}
            onAddField={handleAddField}
            onRemoveField={handleRemoveField}
            onValueChange={handleValueChange}
            distinctOptions={distinctOptions}
            distinctLoading={distinctLoading}
            groups={groups}
            tags={tags}
            campaigns={campaigns}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-gray-100">
          <button onClick={clearAllFilters} className="btn-secondary text-sm">Clear All</button>
          <button onClick={() => setSaveModalOpen(true)} className="btn-secondary text-sm flex items-center gap-1">
            <FiSave size={14} /> Save Search
          </button>
          <button onClick={handleExport} className="btn-secondary text-sm flex items-center gap-1">
            <FiDownload size={14} /> Export CSV
          </button>
          {savedSearches.length > 0 && (
            <select
              className="input-field w-auto text-sm"
              value=""
              onChange={(e) => {
                const saved = savedSearches.find((s) => String(s.id) === e.target.value);
                if (saved) loadSavedSearch(saved);
              }}
            >
              <option value="">Load saved search...</option>
              {savedSearches.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          )}
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2 ml-auto">
              <select
                className="input-field w-auto text-sm"
                value=""
                onChange={(e) => handleBulkResponseTag(e.target.value)}
                title="Tag response for selected prospects"
              >
                <option value="">Tag Response ({selectedIds.size})...</option>
                {RESPONSE_TAGS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <button onClick={() => setTagModalOpen(true)} className="btn-secondary text-sm flex items-center gap-1">
                <FiTag size={14} /> Tag {selectedIds.size}
              </button>
              <button onClick={() => setGroupModalOpen(true)} className="btn-primary text-sm flex items-center gap-1">
                <FiUserPlus size={14} /> Add {selectedIds.size} to Group
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <p className="text-sm text-gray-600">
          <span className="font-semibold text-gray-900">{total}</span> matching prospect{total !== 1 ? 's' : ''}
          {selectedIds.size > 0 && <span className="ml-2 text-primary-600 font-medium">({selectedIds.size} selected)</span>}
        </p>
        <button onClick={handleSelectAllMatching} disabled={selectingAll || total === 0} className="btn-secondary text-sm flex items-center gap-1">
          {selectingAll ? <LoadingSpinner size="sm" /> : <FiCheckSquare size={14} />} Select All {total} Matching
        </button>
      </div>

      <div className="surface-card overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12"><LoadingSpinner size="lg" /></div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="data-table min-w-[1050px]">
                <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95">
                  <tr>
                    <th className="px-4 py-3 w-10"></th>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Email</th>
                    <th className="px-4 py-3 font-medium">Company</th>
                    <th className="px-4 py-3 font-medium">Designation</th>
                    <th className="px-4 py-3 font-medium">Industry</th>
                    <th className="px-4 py-3 font-medium">Location</th>
                    <th className="px-4 py-3 font-medium">Response</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr
                      key={r.id}
                      className={`${
                        r.is_suppressed ? 'bg-slate-50 text-slate-400' : `${selectedIds.has(r.id) ? 'bg-primary-50/30' : ''}`
                      }`}
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={!r.is_suppressed && selectedIds.has(r.id)}
                          onChange={() => toggleSelect(r.id)}
                          disabled={r.is_suppressed}
                          title={r.is_suppressed ? 'Blacklisted prospects cannot be selected' : undefined}
                          className="rounded border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
                        />
                      </td>
                      <td className={`px-4 py-3 font-medium ${r.is_suppressed ? 'text-gray-400' : 'text-gray-900'}`}>{r.name}</td>
                      <td className={`px-4 py-3 ${r.is_suppressed ? '' : 'text-gray-600'}`}>{r.email}</td>
                      <td className={`px-4 py-3 ${r.is_suppressed ? '' : 'text-gray-600'}`}>{r.company || '—'}</td>
                      <td className={`px-4 py-3 ${r.is_suppressed ? '' : 'text-gray-600'}`}>{r.designation || '—'}</td>
                      <td className={`px-4 py-3 ${r.is_suppressed ? '' : 'text-gray-600'}`}>{r.industry || '—'}</td>
                      <td className={`px-4 py-3 ${r.is_suppressed ? '' : 'text-gray-600'}`}>{[r.city, r.state, r.country].filter(Boolean).join(', ') || '—'}</td>
                      <td className="px-4 py-3">
                        <select
                          className={`input-field text-xs py-1 ${r.response_tag ? RESPONSE_TAG_COLORS[r.response_tag] : ''}`}
                          value={r.response_tag || ''}
                          onChange={(e) => e.target.value && handleInlineResponseTag(r.id, e.target.value)}
                        >
                          <option value="">—</option>
                          {RESPONSE_TAGS.map((t) => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        {r.is_suppressed ? (
                          <span title={`Blacklisted: ${r.suppression_reason}`}>
                            <StatusBadge status={r.suppression_reason} />
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {results.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-12 text-center text-gray-400">
                        No prospects found. Upload an Excel file or adjust your filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="border-t border-gray-100 px-4">
              <Pagination page={page} pageSize={10} total={total} onPageChange={setPage} />
            </div>
          </>
        )}
      </div>

      <Modal isOpen={saveModalOpen} onClose={() => setSaveModalOpen(false)} title="Save Search" size="sm">
        <div className="space-y-4">
          <div>
            <label className="label">Search Name</label>
            <input className="input-field" value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="e.g. VP's in IT, India" autoFocus />
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setSaveModalOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleSaveSearch} className="btn-primary">Save</button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={groupModalOpen} onClose={() => setGroupModalOpen(false)} title="Add to Group" size="sm">
        <div className="space-y-4">
          <div>
            <label className="label">Existing Group</label>
            <select className="input-field" value={targetGroupId} onChange={(e) => setTargetGroupId(e.target.value)}>
              <option value="">Select a group...</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.name} ({g.prospect_count})</option>
              ))}
            </select>
          </div>
          <p className="text-xs text-gray-400 text-center">— or —</p>
          <div>
            <label className="label">Create New Group</label>
            <input className="input-field" value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} placeholder="New group name" />
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setGroupModalOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleAddToGroup} className="btn-primary">Add {selectedIds.size} Prospect(s)</button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={tagModalOpen} onClose={() => setTagModalOpen(false)} title="Tag Prospects" size="sm">
        <div className="space-y-4">
          <div>
            <label className="label">Existing Tag</label>
            <select className="input-field" value={targetTagId} onChange={(e) => setTargetTagId(e.target.value)}>
              <option value="">Select a tag...</option>
              {tags.map((t) => (
                <option key={t.id} value={t.id}>{t.name} ({t.recipient_count})</option>
              ))}
            </select>
          </div>
          <p className="text-xs text-gray-400 text-center">— or —</p>
          <div>
            <label className="label">Create New Tag</label>
            <input className="input-field" value={newTagName} onChange={(e) => setNewTagName(e.target.value)} placeholder="e.g. Decision Maker" />
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setTagModalOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleAssignTag} className="btn-primary">Tag {selectedIds.size} Prospect(s)</button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={manageModalOpen} onClose={() => setManageModalOpen(false)} title="Manage Groups & Tags" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-2">Prospect Groups</p>
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {groups.map((g) => (
                <div key={g.id} className="flex items-center justify-between gap-2 rounded-lg border border-gray-200 px-3 py-2">
                  {renamingGroupId === g.id ? (
                    <input
                      autoFocus
                      className="input-field text-sm py-1"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onBlur={() => handleRenameGroup(g.id)}
                      onKeyDown={(e) => e.key === 'Enter' && handleRenameGroup(g.id)}
                    />
                  ) : (
                    <span className="text-sm text-gray-800 truncate">{g.name} <span className="text-gray-400">({g.prospect_count})</span></span>
                  )}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => { setRenamingGroupId(g.id); setRenameValue(g.name); }} className="p-1 rounded hover:bg-gray-100 text-gray-400">
                      <FiEdit2 size={13} />
                    </button>
                    <button onClick={() => setDeletingGroup(g)} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600">
                      <FiTrash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
              {groups.length === 0 && <p className="text-sm text-gray-400">No groups yet.</p>}
            </div>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-2">Tags</p>
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {tags.map((t) => (
                <div key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-gray-200 px-3 py-2">
                  <span className="text-sm text-gray-800 truncate">{t.name} <span className="text-gray-400">({t.recipient_count})</span></span>
                  <button onClick={() => setDeletingTag(t)} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 flex-shrink-0">
                    <FiTrash2 size={13} />
                  </button>
                </div>
              ))}
              {tags.length === 0 && <p className="text-sm text-gray-400">No tags yet.</p>}
            </div>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!deletingGroup}
        onClose={() => setDeletingGroup(null)}
        onConfirm={handleDeleteGroup}
        title="Delete Group"
        message={`Delete "${deletingGroup?.name}"? Prospects stay in the system — this only removes the group.`}
        confirmText="Delete"
      />
      <ConfirmDialog
        isOpen={!!deletingTag}
        onClose={() => setDeletingTag(null)}
        onConfirm={handleDeleteTag}
        title="Delete Tag"
        message={`Delete "${deletingTag?.name}"? This removes the tag from every prospect.`}
        confirmText="Delete"
      />
      <UploadErrorModal
        isOpen={!!uploadMissingColumns}
        onClose={() => setUploadMissingColumns(null)}
        missingColumns={uploadMissingColumns || []}
      />
      <ConfirmDialog
        isOpen={!!pendingDuplicateUpload}
        onClose={() => setPendingDuplicateUpload(null)}
        onConfirm={handleConfirmDuplicateUpload}
        variant="primary"
        title="Duplicate Prospects Detected"
        message={
          pendingDuplicateUpload
            ? buildDuplicateUploadMessage(pendingDuplicateUpload.total, pendingDuplicateUpload.duplicateCount)
            : ''
        }
        confirmText="Import Anyway"
      />
    </PageShell>
  );
}
