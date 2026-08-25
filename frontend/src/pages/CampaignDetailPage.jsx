import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import DOMPurify from 'dompurify';
import {
  FiArrowLeft,
  FiEdit2,
  FiMail,
  FiUsers,
  FiEye,
  FiSend,
  FiCheckSquare,
  FiClock,
  FiPlus,
  FiTrash2,
  FiUpload,
  FiUserPlus,
  FiSave,
  FiBookOpen,
  FiList,
  FiGrid,
  FiLayers,
  FiCalendar,
  FiRefreshCw,
  FiTarget,
  FiTrendingUp,
} from 'react-icons/fi';
import {
  campaignService,
  recipientService,
  recipientGroupService,
  engagementStudioService,
  templateService,
  mailerService,
  emailService,
  customFieldService,
} from '../services/services';
import { useToast } from '../hooks/useToast';
import { useContactSearch } from '../hooks/useContactSearch';
import { extractPlaceholders, isTemplateBodyEmpty, ensureManualBodyIsHtml } from '../utils/helpers';
import { buildRecipientContext, buildSamplePreviewContext, getUnknownPlaceholders } from '../utils/mergeFields';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import UploadErrorModal from '../components/ui/UploadErrorModal';
import EmailPreview from '../components/EmailPreview';
import FilterBuilder from '../components/FilterBuilder';
import TemplateEditor from '../components/TemplateEditor';
import {
  formatDate, formatDateTime, renderTemplate, debounce, getMissingUploadColumns, buildDuplicateUploadMessage,
} from '../utils/helpers';

// Extensions accepted by the prospect-list upload inputs — mirrors the
// backend's SUPPORTED_EXTENSIONS in excel_service.py.
const UPLOAD_ACCEPT = '.xlsx,.xlsm,.xls,.xlsb,.ods,.csv,.tsv,.txt';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'template', label: 'Template' },
  { id: 'candidates', label: 'Prospects' },
  { id: 'engagement-studio', label: 'Engagement Studio' },
];

const EMPTY_STAGE_FORM = {
  delay_value: 3, delay_unit: 'days', mailer_id: null, subject: '', body: '', closing: '', cta: '', skip_if_tagged: true,
};
const EMPTY_TEMPLATE_CONTENT = { subject: '', body: '', closing: '', cta: '' };
const EMPTY_RECIPIENT_FORM = { name: '', email: '', company: '', designation: '', industry: '' };

// Local time, 5 minutes out — formatted for a <input type="datetime-local">'s
// value/min, and a sensible default the moment "Schedule for later" is picked.
function defaultScheduleValue() {
  const d = new Date(Date.now() + 5 * 60 * 1000);
  d.setSeconds(0, 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Same <input type="datetime-local"> formatting as defaultScheduleValue, for
// an arbitrary Date (e.g. "3 days from now") rather than a fixed 5-minute offset.
function toDateTimeLocalValue(date) {
  const d = new Date(date);
  d.setSeconds(0, 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function CampaignDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();

  const preselectedContactIds = location.state?.preselectedContactIds;

  const [campaign, setCampaign] = useState(null);
  const [templates, setTemplates] = useState([]);
  const primaryTemplate = templates[0] ?? null;
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(preselectedContactIds ? 'candidates' : 'overview');

  const {
    search, setSearch, sortBy, setSortBy, sortOrder, setSortOrder,
    activeFieldKeys, filterValues, distinctOptions, distinctLoading,
    results, total, page, setPage, loading: contactsLoading,
    groups, tags, campaigns, activeParams, loadResults,
    handleAddField, handleRemoveField, handleValueChange, clearAllFilters,
  } = useContactSearch({ toast });

  const [selectedIds, setSelectedIds] = useState(preselectedContactIds || []);
  const [selectingAll, setSelectingAll] = useState(false);

  useEffect(() => {
    if (preselectedContactIds?.length) {
      toast.success(`${preselectedContactIds.length} prospect(s) carried over from creation`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewRecipientId, setPreviewRecipientId] = useState(null);
  const [scheduleAt, setScheduleAt] = useState('');
  const [useRecipientTz, setUseRecipientTz] = useState(false);
  const [sending, setSending] = useState(false);

  const [stages, setStages] = useState([]);
  const [stageLoading, setStageLoading] = useState(false);
  const [stageForm, setStageForm] = useState(EMPTY_STAGE_FORM);
  const [stageContentSource, setStageContentSource] = useState('library');
  const [addingStage, setAddingStage] = useState(false);
  const [deletingStageId, setDeletingStageId] = useState(null);

  const [campaignLists, setCampaignLists] = useState([]);
  const [targetListIds, setTargetListIds] = useState([]);
  const [savingLists, setSavingLists] = useState(false);
  const [studioOverview, setStudioOverview] = useState(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [showNonResponsive, setShowNonResponsive] = useState(false);

  const loadCampaign = useCallback(async () => {
    try {
      const [campaignRes, templatesRes] = await Promise.all([
        campaignService.getById(id),
        campaignService.getTemplates(id).catch(() => ({ data: [] })),
      ]);
      setCampaign(campaignRes.data);
      setTemplates(templatesRes?.data ?? []);
    } catch {
      toast.error('Failed to load campaign details');
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    loadCampaign();
  }, [loadCampaign]);

  const loadTemplates = useCallback(async () => {
    try {
      const { data } = await campaignService.getTemplates(id);
      setTemplates(data);
    } catch {
      toast.error('Failed to load templates');
    }
  }, [id, toast]);

  const loadStages = useCallback(async () => {
    setStageLoading(true);
    try {
      const { data } = await engagementStudioService.getStages(id);
      setStages(data);
    } catch {
      toast.error('Failed to load Engagement Studio');
    } finally {
      setStageLoading(false);
    }
  }, [id, toast]);

  const loadStudioLists = useCallback(async () => {
    try {
      const [listsRes, targetRes] = await Promise.all([
        campaignService.getLists(id),
        engagementStudioService.getLists(id),
      ]);
      setCampaignLists(listsRes.data ?? []);
      setTargetListIds(targetRes.data?.group_ids ?? []);
    } catch {
      toast.error('Failed to load target prospect lists');
    }
  }, [id, toast]);

  const loadStudioOverview = useCallback(async () => {
    setOverviewLoading(true);
    try {
      const { data } = await engagementStudioService.getOverview(id);
      setStudioOverview(data);
    } catch {
      toast.error('Failed to load engagement overview');
    } finally {
      setOverviewLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    if (activeTab === 'engagement-studio') {
      loadStages();
      loadStudioLists();
      loadStudioOverview();
    }
  }, [activeTab, loadStages, loadStudioLists, loadStudioOverview]);

  const handleAddStage = async () => {
    const usingLibrary = stageContentSource === 'library';
    if (usingLibrary && !stageForm.mailer_id) {
      toast.error('Select a template from the library');
      return;
    }
    if (!usingLibrary && (!stageForm.subject || !stageForm.body)) {
      toast.error('Subject and body are required');
      return;
    }
    setAddingStage(true);
    try {
      const nextOrder = stages.length > 0 ? Math.max(...stages.map((s) => s.stage_order)) + 1 : 1;
      const payload = usingLibrary
        ? { ...stageForm, subject: null, body: null, closing: null, stage_order: nextOrder }
        : { ...stageForm, mailer_id: null, stage_order: nextOrder };
      await engagementStudioService.createStage(id, payload);
      toast.success('Engagement Studio stage added');
      setStageForm(EMPTY_STAGE_FORM);
      loadStages();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add stage');
    } finally {
      setAddingStage(false);
    }
  };

  const handleDeleteStage = async () => {
    try {
      await engagementStudioService.deleteStage(deletingStageId);
      toast.success('Stage removed');
      loadStages();
    } catch {
      toast.error('Failed to remove stage');
    }
  };

  const toggleTargetList = (groupId) => {
    setTargetListIds((prev) =>
      prev.includes(groupId) ? prev.filter((gid) => gid !== groupId) : [...prev, groupId]
    );
  };

  const handleSaveTargetLists = async () => {
    setSavingLists(true);
    try {
      await engagementStudioService.setLists(id, targetListIds);
      toast.success('Target prospect lists saved');
      loadStudioOverview();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save target lists');
    } finally {
      setSavingLists(false);
    }
  };

  // ── Template tab — "Add New Template" popup (same fields/options as the
  // Create Campaign wizard's Template step, reusing <TemplateEditor>). ──────
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [templateType, setTemplateType] = useState('manual');
  const [emailContent, setEmailContent] = useState(EMPTY_TEMPLATE_CONTENT);
  const [placeholderTemplates, setPlaceholderTemplates] = useState([]);
  const [selectedPlaceholderTemplate, setSelectedPlaceholderTemplate] = useState(null);
  const [placeholderValues, setPlaceholderValues] = useState({});
  const [aiPrompt, setAiPrompt] = useState({ additional_context: '' });
  const [aiLoading, setAiLoading] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [deletingTemplateId, setDeletingTemplateId] = useState(null);
  const [editingTemplateId, setEditingTemplateId] = useState(null);

  const [mailers, setMailers] = useState([]);
  const [saveMailerModalOpen, setSaveMailerModalOpen] = useState(false);
  const [newMailerName, setNewMailerName] = useState('');
  const [savingMailer, setSavingMailer] = useState(false);

  const [customFields, setCustomFields] = useState([]);
  const [unknownFields, setUnknownFields] = useState(null);

  useEffect(() => {
    customFieldService.getAll().then(({ data }) => setCustomFields(data)).catch(() => {});
  }, []);

  useEffect(() => {
    mailerService.getAll().then(({ data }) => setMailers(data)).catch(() => {});
  }, []);

  const resetTemplateForm = () => {
    setNewTemplateName('');
    setTemplateType('manual');
    setEmailContent(EMPTY_TEMPLATE_CONTENT);
    setSelectedPlaceholderTemplate(null);
    setPlaceholderValues({});
    setAiPrompt({ additional_context: '' });
  };

  const handleOpenAddTemplate = () => {
    resetTemplateForm();
    setEditingTemplateId(null);
    setTemplateModalOpen(true);
  };

  const handleOpenEditTemplate = (template) => {
    setEditingTemplateId(template.id);
    setNewTemplateName(template.name || '');
    setTemplateType(template.type);
    setEmailContent({
      subject: template.subject || '',
      body: template.type === 'manual' ? ensureManualBodyIsHtml(template.body || '') : (template.body || ''),
      closing: template.closing || '',
      cta: template.cta || '',
    });
    setSelectedPlaceholderTemplate(null);
    setPlaceholderValues({});
    setAiPrompt({ additional_context: '' });
    setTemplateModalOpen(true);
  };

  const loadPlaceholderTemplates = async () => {
    if (placeholderTemplates.length > 0) return;
    try {
      const { data } = await templateService.getPlaceholderTemplates();
      setPlaceholderTemplates(data);
    } catch {
      toast.error('Failed to load templates');
    }
  };

  const handleTemplateTypeChange = (type) => {
    setTemplateType(type);
    if (type === 'placeholder') loadPlaceholderTemplates();
  };

  const handleSelectPlaceholderTemplate = (tpl) => {
    setSelectedPlaceholderTemplate(tpl);
    const placeholders = extractPlaceholders(tpl.subject + ' ' + tpl.body);
    const values = {};
    placeholders.forEach((p) => { values[p] = ''; });
    setPlaceholderValues(values);
    setEmailContent({ subject: tpl.subject, body: tpl.body, closing: '', cta: '' });
  };

  const handleGenerateAI = async () => {
    setAiLoading(true);
    try {
      const { data } = await templateService.generateAI({
        campaign_name: campaign.campaign_name,
        campaign_description: campaign.description,
        target_audience: campaign.target_audience,
        additional_context: aiPrompt.additional_context,
      });
      setEmailContent({ subject: data.subject, body: data.body, closing: data.closing, cta: data.cta });
      if (data.is_mock) toast.info('Using mock AI response (OpenAI not configured)');
      else toast.success('AI email generated successfully');
    } catch {
      toast.error('Failed to generate AI template');
    } finally {
      setAiLoading(false);
    }
  };

  const handleSelectMailer = (mailerId) => {
    const mailer = mailers.find((m) => String(m.id) === mailerId);
    if (!mailer) return;
    setTemplateType(mailer.type);
    setEmailContent({
      subject: mailer.subject,
      body: mailer.type === 'manual' ? ensureManualBodyIsHtml(mailer.body) : mailer.body,
      closing: mailer.closing || '',
      cta: mailer.cta || '',
    });
    toast.success(`Loaded mailer "${mailer.name}"`);
  };

  const handleConfirmSaveMailer = async () => {
    if (!newMailerName.trim()) {
      toast.error('Enter a name for this mailer');
      return;
    }
    if (!emailContent.subject.trim() || isTemplateBodyEmpty(emailContent.body, templateType)) {
      toast.error('Subject and body are required to save a mailer');
      return;
    }
    setSavingMailer(true);
    try {
      await mailerService.create({
        name: newMailerName.trim(),
        type: templateType,
        subject: emailContent.subject,
        body: emailContent.body,
        closing: emailContent.closing,
        cta: emailContent.cta,
      });
      toast.success('Saved as a reusable mailer');
      setSaveMailerModalOpen(false);
      setNewMailerName('');
      const { data } = await mailerService.getAll();
      setMailers(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save mailer');
    } finally {
      setSavingMailer(false);
    }
  };

  const templatePreviewContext = buildSamplePreviewContext(placeholderValues);

  const performSaveTemplate = async () => {
    setSavingTemplate(true);
    try {
      const payload = {
        name: newTemplateName.trim() || undefined,
        type: templateType,
        subject: emailContent.subject,
        body: emailContent.body,
        closing: emailContent.closing,
        cta: emailContent.cta,
      };
      if (editingTemplateId) {
        await campaignService.updateTemplate(editingTemplateId, payload);
        toast.success('Template updated');
      } else {
        await campaignService.saveTemplate(id, { ...payload, campaign_id: Number(id) });
        toast.success('Template added');
      }
      setTemplateModalOpen(false);
      setEditingTemplateId(null);
      loadTemplates();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save template');
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleSaveTemplate = () => {
    if (!emailContent.subject.trim() || isTemplateBodyEmpty(emailContent.body, templateType)) {
      toast.error('Subject and body are required');
      return;
    }
    const unknown = getUnknownPlaceholders(
      [emailContent.subject, emailContent.body, emailContent.closing, emailContent.cta],
      customFields.map((f) => f.name)
    );
    if (unknown.length > 0) {
      setUnknownFields(unknown);
      return;
    }
    performSaveTemplate();
  };

  const handleProceedWithUnknownFields = async () => {
    try {
      await Promise.all(unknownFields.map((name) => customFieldService.create(name)));
      const { data } = await customFieldService.getAll();
      setCustomFields(data);
    } catch {
      // Registration failing shouldn't block the save the user already confirmed.
    } finally {
      performSaveTemplate();
    }
  };

  const handleDeleteTemplate = async () => {
    try {
      await campaignService.deleteTemplate(deletingTemplateId);
      toast.success('Template removed');
      loadTemplates();
    } catch {
      toast.error('Failed to remove template');
    } finally {
      setDeletingTemplateId(null);
    }
  };

  // ── Prospects tab — Upload Excel / Add Manually, both tag the touched
  // recipient(s) to the chosen template for this campaign. ─────────────────
  const [uploadGroupName, setUploadGroupName] = useState('');
  const [listNameError, setListNameError] = useState(false);
  const [uploadTemplateId, setUploadTemplateId] = useState('');
  const [uploadingProspects, setUploadingProspects] = useState(false);

  const [addProspectModalOpen, setAddProspectModalOpen] = useState(false);
  const [recipientForm, setRecipientForm] = useState(EMPTY_RECIPIENT_FORM);
  const [recipientTemplateId, setRecipientTemplateId] = useState('');
  const [addRecipientGroupName, setAddRecipientGroupName] = useState('');
  const [savingRecipient, setSavingRecipient] = useState(false);
  const [uploadingToList, setUploadingToList] = useState(false);
  const [uploadMissingColumns, setUploadMissingColumns] = useState(null);
  const [pendingProspectsUpload, setPendingProspectsUpload] = useState(null);
  const [pendingListUpload, setPendingListUpload] = useState(null);
  const [refreshingProspects, setRefreshingProspects] = useState(false);

  const handleListNameChange = (value) => {
    setUploadGroupName(value);
    if (value.trim()) setListNameError(false);
  };

  const requireListName = () => {
    if (!uploadGroupName.trim()) {
      setListNameError(true);
      toast.error('Enter a list name first');
      return false;
    }
    return true;
  };

  const handleUploadClick = (e) => {
    if (!requireListName()) e.preventDefault();
  };

  const performUploadProspects = async (file, groupName, confirm = false) => {
    setUploadingProspects(true);
    try {
      const { data } = await recipientService.uploadExcel(file, groupName, id, uploadTemplateId || null, confirm);
      if (data.requires_confirmation) {
        setPendingProspectsUpload({ file, groupName, total: data.total, duplicateCount: data.duplicate_count });
        return;
      }
      toast.success(data.message);
      setUploadGroupName('');
      loadResults();
      if (browseMode === 'lists') loadLists();
    } catch (err) {
      const missingColumns = getMissingUploadColumns(err);
      if (missingColumns) {
        setUploadMissingColumns(missingColumns);
      } else {
        const detail = err.response?.data?.detail;
        toast.error((typeof detail === 'string' && detail) || 'Upload failed');
      }
    } finally {
      setUploadingProspects(false);
    }
  };

  const handleUploadProspects = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!requireListName()) {
      e.target.value = '';
      return;
    }
    e.target.value = '';
    performUploadProspects(file, uploadGroupName.trim());
  };

  const handleConfirmProspectsUpload = () => {
    if (!pendingProspectsUpload) return;
    const { file, groupName } = pendingProspectsUpload;
    performUploadProspects(file, groupName, true);
  };

  const handleRefreshProspects = async () => {
    setRefreshingProspects(true);
    try {
      if (browseMode === 'lists') {
        if (openListId) await loadListMembers(openListId);
        else await loadLists();
      } else {
        await loadResults();
      }
    } finally {
      setRefreshingProspects(false);
    }
  };

  const handleOpenAddProspect = () => {
    if (!requireListName()) return;
    setRecipientForm(EMPTY_RECIPIENT_FORM);
    setRecipientTemplateId(uploadTemplateId);
    setAddRecipientGroupName(uploadGroupName.trim());
    setAddProspectModalOpen(true);
  };

  // ── Adding directly into an already-open list — reuses the same modal and
  // endpoint as the toolbar's "Add Manually", but targets the currently
  // opened list's name/template instead of requiring it to be retyped. ────
  const handleOpenAddToList = () => {
    setRecipientForm(EMPTY_RECIPIENT_FORM);
    setRecipientTemplateId(listTemplateId);
    setAddRecipientGroupName(openListName);
    setAddProspectModalOpen(true);
  };

  const performUploadToList = async (file, confirm = false) => {
    setUploadingToList(true);
    try {
      const { data } = await recipientService.uploadExcel(file, openListName, id, listTemplateId || null, confirm);
      if (data.requires_confirmation) {
        setPendingListUpload({ file, total: data.total, duplicateCount: data.duplicate_count });
        return;
      }
      toast.success(data.message);
      loadListMembers(openListId);
      loadLists();
    } catch (err) {
      const missingColumns = getMissingUploadColumns(err);
      if (missingColumns) {
        setUploadMissingColumns(missingColumns);
      } else {
        const detail = err.response?.data?.detail;
        toast.error((typeof detail === 'string' && detail) || 'Upload failed');
      }
    } finally {
      setUploadingToList(false);
    }
  };

  const handleUploadToList = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    performUploadToList(file);
  };

  const handleConfirmListUpload = () => {
    if (!pendingListUpload) return;
    performUploadToList(pendingListUpload.file, true);
  };

  const handleAddRecipient = async () => {
    if (!recipientForm.name.trim() || !recipientForm.email.trim()) {
      toast.error('Name and Email are required');
      return;
    }
    setSavingRecipient(true);
    try {
      await recipientService.create({
        ...recipientForm,
        campaign_id: Number(id),
        template_id: recipientTemplateId || null,
        group_name: addRecipientGroupName,
      });
      toast.success('Prospect added to this campaign');
      setAddProspectModalOpen(false);
      loadResults();
      if (browseMode === 'lists') {
        loadLists();
        if (openListId) loadListMembers(openListId);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add prospect');
    } finally {
      setSavingRecipient(false);
    }
  };

  // ── Prospects tab — "By List" browse mode: group prospects by the list
  // (RecipientGroup) they were tagged under for this campaign, with a
  // per-list default template and its own select/send/status view. ────────
  const [browseMode, setBrowseMode] = useState('lists'); // 'all' | 'lists'
  const [lists, setLists] = useState([]);
  const [listsLoading, setListsLoading] = useState(false);
  const [openListId, setOpenListId] = useState(null);
  const [openListName, setOpenListName] = useState('');
  const [listMembers, setListMembers] = useState([]);
  const [listMembersLoading, setListMembersLoading] = useState(false);
  const [listSelectedIds, setListSelectedIds] = useState([]);
  const [listSearch, setListSearch] = useState('');
  const [listDisplayMode, setListDisplayMode] = useState('table'); // 'table' | 'catalog'
  const [listTemplateId, setListTemplateId] = useState('');
  const [retaggingList, setRetaggingList] = useState(false);
  const [scheduleModalList, setScheduleModalList] = useState(null);
  const [scheduleListValue, setScheduleListValue] = useState('');
  const [schedulingList, setSchedulingList] = useState(false);

  const loadLists = useCallback(async () => {
    setListsLoading(true);
    try {
      const { data } = await campaignService.getLists(id);
      setLists(data);
    } catch {
      toast.error('Failed to load lists');
    } finally {
      setListsLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    if (activeTab === 'candidates' && browseMode === 'lists' && !openListId) loadLists();
  }, [activeTab, browseMode, openListId, loadLists]);

  const loadListMembers = useCallback(async (groupId) => {
    setListMembersLoading(true);
    try {
      const { data } = await campaignService.getListMembers(id, groupId);
      setListMembers(data);
    } catch {
      toast.error('Failed to load list members');
    } finally {
      setListMembersLoading(false);
    }
  }, [id, toast]);

  const handleOpenList = (list) => {
    setOpenListId(list.group_id);
    setOpenListName(list.name);
    setListTemplateId(list.template_id ? String(list.template_id) : '');
    setListSelectedIds([]);
    setListSearch('');
    loadListMembers(list.group_id);
  };

  const handleBackToLists = () => {
    setOpenListId(null);
    setOpenListName('');
    setListMembers([]);
    setListSelectedIds([]);
  };

  const [deletingList, setDeletingList] = useState(null);

  const handleDeleteList = async () => {
    if (!deletingList) return;
    const { group_id, name } = deletingList;
    try {
      await recipientGroupService.delete(group_id);
      toast.success(`Deleted list "${name}"`);
      if (openListId === group_id) handleBackToLists();
      loadLists();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete list');
    }
  };

  const openScheduleList = (e, list) => {
    e.stopPropagation();
    setScheduleModalList(list);
    setScheduleListValue(toDateTimeLocalValue(new Date(Date.now() + 3 * 24 * 60 * 60 * 1000)));
  };

  const closeScheduleList = () => {
    setScheduleModalList(null);
    setScheduleListValue('');
  };

  const handleScheduleList = async () => {
    if (!scheduleModalList || !scheduleListValue) return;
    setSchedulingList(true);
    try {
      const { data } = await campaignService.scheduleList(
        id,
        scheduleModalList.group_id,
        new Date(scheduleListValue).toISOString()
      );
      let message = `Scheduled ${data.scheduled} email(s) in "${scheduleModalList.name}" for ${new Date(scheduleListValue).toLocaleString()}.`;
      if (data.skipped_suppressed > 0) message += ` (${data.skipped_suppressed} skipped — blacklisted)`;
      toast.success(message);
      closeScheduleList();
      loadLists();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to schedule list');
    } finally {
      setSchedulingList(false);
    }
  };

  const handleChangeListTemplate = async (newTemplateId) => {
    setListTemplateId(newTemplateId);
    setRetaggingList(true);
    try {
      await campaignService.retagList(id, openListId, newTemplateId || null);
      toast.success('List re-tagged to the new template');
      loadListMembers(openListId);
      loadLists();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to re-tag list');
    } finally {
      setRetaggingList(false);
    }
  };

  const toggleListRecipient = (recipientId) => {
    setListSelectedIds((prev) =>
      prev.includes(recipientId) ? prev.filter((rid) => rid !== recipientId) : [...prev, recipientId]
    );
  };

  const clearListSelection = () => setListSelectedIds([]);

  const filteredListMembers = listMembers.filter((m) => {
    if (!listSearch.trim()) return true;
    const q = listSearch.toLowerCase();
    return m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q);
  });

  const handleSelectAllListMembers = () => {
    setListSelectedIds(filteredListMembers.filter((m) => !m.is_suppressed).map((m) => m.id));
  };

  const isListMode = browseMode === 'lists' && !!openListId;
  // What's actually about to be sent/previewed — the opened list's tagged
  // template when browsing "By List", else the campaign's primary template.
  const effectiveTemplate = isListMode
    ? templates.find((t) => t.id === Number(listTemplateId)) || primaryTemplate
    : primaryTemplate;

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  const toggleRecipient = (recipientId) => {
    setSelectedIds((prev) =>
      prev.includes(recipientId) ? prev.filter((rid) => rid !== recipientId) : [...prev, recipientId]
    );
  };

  const clearSelection = () => setSelectedIds([]);

  const handleSelectAllMatching = async () => {
    setSelectingAll(true);
    try {
      const { data } = await recipientService.searchIds({ ...activeParams, exclude_suppressed: true });
      setSelectedIds(data.ids);
      toast.success(`Selected all ${data.total} matching prospect(s)`);
    } catch {
      toast.error('Failed to select all matching prospects');
    } finally {
      setSelectingAll(false);
    }
  };

  const activeSelectedIds = isListMode ? listSelectedIds : selectedIds;
  const activeResultsPool = isListMode ? listMembers : results;
  const selectedRecipients = activeResultsPool.filter((r) => activeSelectedIds.includes(r.id));

  useEffect(() => {
    if (selectedRecipients.length === 0) {
      setPreviewRecipientId(null);
    } else if (!selectedRecipients.some((r) => r.id === previewRecipientId)) {
      setPreviewRecipientId(selectedRecipients[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSelectedIds, activeResultsPool]);

  const previewRecipient = activeResultsPool.find((r) => r.id === previewRecipientId);
  const previewContext = previewRecipient ? buildRecipientContext(previewRecipient) : null;

  const handleOpenPreview = () => {
    if (!effectiveTemplate) {
      toast.error('This campaign has no template yet. Add one from the Template tab.');
      setActiveTab('template');
      return;
    }
    if (activeSelectedIds.length === 0) {
      toast.error('Select at least one prospect first');
      setActiveTab('candidates');
      return;
    }
    setUseRecipientTz(!!campaign.use_recipient_timezone);
    setPreviewOpen(true);
  };

  const handleSend = async () => {
    setSending(true);
    try {
      if (scheduleAt || useRecipientTz !== !!campaign.use_recipient_timezone) {
        await campaignService.update(campaign.id, {
          ...(scheduleAt ? { scheduled_at: new Date(scheduleAt).toISOString() } : {}),
          use_recipient_timezone: useRecipientTz,
        });
      }
      const { data } = await emailService.send({
        campaign_id: campaign.id,
        subject: effectiveTemplate.subject,
        body: effectiveTemplate.body + (effectiveTemplate.closing ? `\n\n${effectiveTemplate.closing}` : ''),
        type: effectiveTemplate.type,
        recipient_ids: activeSelectedIds,
      });
      if (data.immediate_sent > 0) {
        toast.success('Test email sent (mock mode, no real prospects selected)');
      } else {
        if (data.queued > 0) {
          let message = scheduleAt
            ? `Scheduled ${data.queued} email(s) for ${new Date(scheduleAt).toLocaleString()}, staggered from there to protect deliverability.`
            : `Queued ${data.queued} email(s) — sending in the background, spaced out to protect deliverability. Each prospect uses their tagged template.`;
          if (data.skipped_suppressed > 0) {
            message += ` (${data.skipped_suppressed} skipped — blacklisted)`;
          }
          toast.success(message);
        }
        if (data.skipped_incomplete_data > 0) {
          const byField = {};
          (data.incomplete || []).forEach(({ email, missing_fields }) => {
            missing_fields.forEach((field) => {
              (byField[field] = byField[field] || []).push(email);
            });
          });
          const detail = Object.entries(byField)
            .map(([field, emails]) => {
              const shown = emails.slice(0, 3).join(', ');
              const more = emails.length > 3 ? ` +${emails.length - 3} more` : '';
              return `{{${field}}} missing for ${shown}${more}`;
            })
            .join('; ');
          toast.error(
            `${data.skipped_incomplete_data} prospect(s) skipped — ${detail}. Re-upload the list with that column filled in, then resend to them.`
          );
        }
      }
      setPreviewOpen(false);
      setScheduleAt('');
      if (isListMode) {
        clearListSelection();
        loadListMembers(openListId);
        loadLists();
      } else {
        clearSelection();
      }
      loadCampaign();
      setActiveTab('candidates');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send emails');
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!campaign) {
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/campaigns')} className="btn-secondary flex items-center gap-2">
            <FiArrowLeft size={16} /> Back
          </button>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold text-gray-900">{campaign.campaign_name}</h1>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-gray-500 mt-1">{campaign.campaign_id}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(`/campaigns/${id}/edit`)} className="btn-secondary flex items-center gap-2">
            <FiEdit2 size={16} /> Edit Campaign
          </button>
          <button onClick={handleOpenPreview} className="btn-primary flex items-center gap-2">
            <FiSend size={16} /> Send Campaign
            {activeSelectedIds.length > 0 && (
              <span className="bg-white/20 rounded-full px-1.5 text-xs">{activeSelectedIds.length}</span>
            )}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className={`grid grid-cols-1 gap-6 ${activeTab === 'overview' ? 'lg:grid-cols-3' : ''}`}>
        <div className={activeTab === 'overview' ? 'lg:col-span-2 space-y-6' : 'space-y-6'}>
          {activeTab === 'overview' && (
            <div className="card">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Campaign Overview</h2>
                <StatusBadge status={campaign.status} />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm">
                <div>
                  <p className="text-gray-500">Owner</p>
                  <p className="font-medium text-gray-900">{campaign.owner}</p>
                </div>
                <div>
                  <p className="text-gray-500">Department</p>
                  <p className="font-medium text-gray-900">{campaign.department || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Target Audience</p>
                  <p className="font-medium text-gray-900">{campaign.target_audience || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Created</p>
                  <p className="font-medium text-gray-900">{formatDate(campaign.created_at)}</p>
                </div>
                <div>
                  <p className="text-gray-500">Scheduled For</p>
                  <p className="font-medium text-gray-900">
                    {campaign.scheduled_at ? formatDateTime(campaign.scheduled_at) : 'Not scheduled — sends immediately'}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500">Time-Zone Optimization</p>
                  <p className="font-medium text-gray-900">
                    {campaign.use_recipient_timezone ? 'On — sends within each prospect\'s local business hours' : 'Off'}
                  </p>
                </div>
              </div>
              {campaign.description && (
                <div className="mt-4">
                  <p className="text-gray-500">Description</p>
                  <p className="text-gray-700 mt-1">{campaign.description}</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'template' && (
            <div className="card">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="text-lg font-semibold">Email Templates</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    A campaign can hold several templates — tag a prospect list to one from the Prospects tab.
                  </p>
                </div>
                <button onClick={handleOpenAddTemplate} className="btn-primary text-sm flex items-center gap-2 flex-shrink-0">
                  <FiPlus size={16} /> Add New Template
                </button>
              </div>

              {templates.length === 0 ? (
                <div className="mt-4 rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
                  No templates yet — click "Add New Template" to create the first one.
                </div>
              ) : (
                <div className="mt-4 space-y-3">
                  {templates.map((t, i) => (
                    <div key={t.id} className="rounded-xl border border-gray-200 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-gray-900">{t.name || `Template ${i + 1}`}</p>
                            {i === 0 && (
                              <span className="text-xs px-1.5 py-0.5 rounded-full bg-primary-50 text-primary-600">Primary</span>
                            )}
                            <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600 capitalize">{t.type}</span>
                          </div>
                          <p className="truncate text-sm text-gray-700 mt-1.5">{t.subject}</p>
                          {t.type === 'manual' ? (
                            <div
                              className="prose prose-sm mt-1 line-clamp-2 max-w-none overflow-hidden text-xs text-gray-500"
                              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(t.body || '') }}
                            />
                          ) : (
                            <p className="line-clamp-2 whitespace-pre-wrap text-xs text-gray-500 mt-1">{t.body}</p>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            onClick={() => handleOpenEditTemplate(t)}
                            className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                            title="Edit template"
                            aria-label={`Edit ${t.name || `Template ${i + 1}`}`}
                          >
                            <FiEdit2 size={15} />
                          </button>
                          <button
                            onClick={() => setDeletingTemplateId(t.id)}
                            className="p-1.5 rounded-lg text-gray-500 hover:bg-red-50 hover:text-red-600"
                            title="Delete template"
                            aria-label={`Delete ${t.name || `Template ${i + 1}`}`}
                          >
                            <FiTrash2 size={15} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'engagement-studio' && (
            <div className="space-y-6">
              <div className="card">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <FiClock size={18} /> Engagement Studio
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  Stage 0 is the email on the Template tab, sent immediately. Add stages below — each fires
                  automatically after the configured delay. A reply auto-tags the prospect "Hot" and stops the
                  sequence for them (if the stage says so); no reply auto-tags "Cold" and they keep moving
                  through the remaining stages. Bounced or suppressed prospects always stop.
                </p>
              </div>

              <div className="card">
                <h3 className="text-base font-semibold flex items-center gap-2">
                  <FiTarget size={16} /> Target Prospect Lists
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Choose which of this campaign's prospect lists are enrolled in automated follow-ups.
                  Select none to enroll every prospect in the campaign.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {campaignLists.map((list) => (
                    <label
                      key={list.group_id}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm cursor-pointer ${
                        targetListIds.includes(list.group_id)
                          ? 'border-primary-500 bg-primary-50 text-primary-700'
                          : 'border-gray-200 text-gray-600'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="hidden"
                        checked={targetListIds.includes(list.group_id)}
                        onChange={() => toggleTargetList(list.group_id)}
                      />
                      {list.name} <span className="text-gray-400">({list.total})</span>
                    </label>
                  ))}
                  {campaignLists.length === 0 && (
                    <p className="text-sm text-gray-400">No prospect lists tagged into this campaign yet.</p>
                  )}
                </div>
                {campaignLists.length > 0 && (
                  <button
                    onClick={handleSaveTargetLists}
                    disabled={savingLists}
                    className="btn-secondary mt-3 flex items-center gap-2"
                  >
                    {savingLists ? <LoadingSpinner size="sm" /> : <FiSave size={14} />} Save Target Lists
                  </button>
                )}
              </div>

              <div className="card">
                <h3 className="text-base font-semibold flex items-center gap-2">
                  <FiTrendingUp size={16} /> Engagement Overview
                </h3>
                {overviewLoading ? (
                  <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
                ) : studioOverview && (
                  <>
                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <div className="rounded-xl border border-gray-200 p-3 text-center">
                        <p className="text-2xl font-semibold text-gray-900">{studioOverview.total}</p>
                        <p className="text-xs text-gray-500 mt-1">Total Engaged</p>
                      </div>
                      <div className="rounded-xl border border-gray-200 p-3 text-center">
                        <p className="text-2xl font-semibold text-green-600">{studioOverview.responded}</p>
                        <p className="text-xs text-gray-500 mt-1">Responded</p>
                      </div>
                      <div className="rounded-xl border border-gray-200 p-3 text-center">
                        <p className="text-2xl font-semibold text-amber-600">{studioOverview.non_responsive}</p>
                        <p className="text-xs text-gray-500 mt-1">Non-responsive</p>
                      </div>
                    </div>
                    {studioOverview.non_responsive_recipients.length > 0 && (
                      <div className="mt-3">
                        <button
                          onClick={() => setShowNonResponsive((v) => !v)}
                          className="text-sm text-primary-600 hover:underline"
                        >
                          {showNonResponsive ? 'Hide' : 'View'} non-responsive prospects
                        </button>
                        {showNonResponsive && (
                          <div className="mt-2 max-h-64 overflow-y-auto space-y-1">
                            {studioOverview.non_responsive_recipients.map((r) => (
                              <div key={r.id} className="text-sm text-gray-600 flex justify-between border-b border-gray-100 py-1">
                                <span>{r.name} — {r.email}</span>
                                <span className="text-gray-400">{r.company}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="card">
                <h3 className="text-base font-semibold">Stages</h3>
                {stageLoading ? (
                  <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
                ) : (
                  <div className="mt-4 space-y-3">
                    {stages.map((s) => (
                      <div key={s.id} className="rounded-xl border border-gray-200 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-gray-900">
                              Stage {s.stage_order} — after {s.delay_value} {s.delay_unit}
                              {s.skip_if_tagged && (
                                <span className="ml-2 text-xs font-normal text-gray-400">(skips prospects who replied / tagged Hot)</span>
                              )}
                            </p>
                            {s.mailer_name ? (
                              <p className="text-sm text-gray-600 mt-1">
                                From template library: <span className="font-medium">{s.mailer_name}</span>
                              </p>
                            ) : (
                              <>
                                <p className="text-sm text-gray-600 mt-1">{s.subject}</p>
                                <p className="text-xs text-gray-500 mt-1 whitespace-pre-wrap">{s.body}</p>
                              </>
                            )}
                          </div>
                          <button
                            onClick={() => setDeletingStageId(s.id)}
                            className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600"
                          >
                            <FiTrash2 size={15} />
                          </button>
                        </div>
                      </div>
                    ))}
                    {stages.length === 0 && (
                      <p className="text-sm text-gray-400">No stages yet — this campaign only sends the initial email.</p>
                    )}
                  </div>
                )}

                <div className="mt-6 pt-4 border-t border-gray-100 space-y-3">
                  <p className="text-sm font-medium text-gray-700">Add a stage</p>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">Send after</span>
                    <input
                      type="number"
                      min={1}
                      className="input-field w-20"
                      value={stageForm.delay_value}
                      onChange={(e) => setStageForm((p) => ({ ...p, delay_value: Number(e.target.value) }))}
                    />
                    <select
                      className="input-field w-auto"
                      value={stageForm.delay_unit}
                      onChange={(e) => setStageForm((p) => ({ ...p, delay_unit: e.target.value }))}
                    >
                      <option value="minutes">Minutes</option>
                      <option value="hours">Hours</option>
                      <option value="days">Days</option>
                    </select>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => setStageContentSource('library')}
                      className={`px-3 py-1.5 rounded-lg text-sm border ${stageContentSource === 'library' ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600'}`}
                    >
                      From Template Library
                    </button>
                    <button
                      onClick={() => setStageContentSource('custom')}
                      className={`px-3 py-1.5 rounded-lg text-sm border ${stageContentSource === 'custom' ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600'}`}
                    >
                      Custom Content
                    </button>
                  </div>

                  {stageContentSource === 'library' ? (
                    <select
                      className="input-field"
                      value={stageForm.mailer_id ?? ''}
                      onChange={(e) => setStageForm((p) => ({ ...p, mailer_id: e.target.value ? Number(e.target.value) : null }))}
                    >
                      <option value="">Select a template…</option>
                      {mailers.map((m) => (
                        <option key={m.id} value={m.id}>{m.name} — {m.subject}</option>
                      ))}
                    </select>
                  ) : (
                    <>
                      <input
                        className="input-field"
                        placeholder="Subject"
                        value={stageForm.subject}
                        onChange={(e) => setStageForm((p) => ({ ...p, subject: e.target.value }))}
                      />
                      <textarea
                        className="input-field font-mono text-sm"
                        rows={5}
                        placeholder="Body — use {{Name}}, {{Company}} etc for personalization"
                        value={stageForm.body}
                        onChange={(e) => setStageForm((p) => ({ ...p, body: e.target.value }))}
                      />
                      <input
                        className="input-field"
                        placeholder="Closing (optional)"
                        value={stageForm.closing}
                        onChange={(e) => setStageForm((p) => ({ ...p, closing: e.target.value }))}
                      />
                    </>
                  )}

                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    <input
                      type="checkbox"
                      checked={stageForm.skip_if_tagged}
                      onChange={(e) => setStageForm((p) => ({ ...p, skip_if_tagged: e.target.checked }))}
                    />
                    Skip prospects who replied (auto-tagged Hot) — non-repliers (Cold) still get this stage
                  </label>

                  <button onClick={handleAddStage} disabled={addingStage} className="btn-primary flex items-center gap-2">
                    {addingStage ? <LoadingSpinner size="sm" /> : <FiPlus size={16} />} Add Stage
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'candidates' && (
            <div className="card">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <FiUsers size={18} /> Prospects
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">
                    Search, filter, and select who should receive this campaign, then preview and send.
                  </p>
                </div>
                <button
                  onClick={handleOpenPreview}
                  disabled={activeSelectedIds.length === 0}
                  className="btn-primary flex items-center gap-2 disabled:opacity-50"
                >
                  <FiEye size={16} /> Preview & Send
                </button>
              </div>

              <div className="mt-4 inline-flex rounded-lg border border-gray-200 p-1 bg-gray-50">
                <button
                  onClick={() => setBrowseMode('all')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    browseMode === 'all' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  All Prospects
                </button>
                <button
                  onClick={() => setBrowseMode('lists')}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors flex items-center gap-1.5 ${
                    browseMode === 'lists' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <FiLayers size={14} /> By List
                </button>
              </div>

              {!primaryTemplate && (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  This campaign doesn't have an email template yet.{' '}
                  <button onClick={() => setActiveTab('template')} className="underline font-medium">
                    Add one
                  </button>{' '}
                  before sending.
                </div>
              )}

              <div className="mt-4 rounded-xl border border-gray-200 bg-gray-50 p-4">
                <p className="text-sm font-semibold text-gray-700 mb-3">Add Prospects to This Campaign</p>
                <div className="flex flex-wrap items-start gap-3">
                  <div className="w-full sm:w-56">
                    <label className="label">List Name *</label>
                    <input
                      className={`input-field ${listNameError ? 'border-red-500 ring-1 ring-red-500 focus:ring-red-500' : ''}`}
                      placeholder="e.g. Uploaded — Jul batch"
                      value={uploadGroupName}
                      onChange={(e) => handleListNameChange(e.target.value)}
                    />
                    {listNameError && <p className="text-xs text-red-600 mt-1">List name is required</p>}
                  </div>
                  <div className="w-full sm:w-52">
                    <label className="label">Tag to Template</label>
                    <select
                      className="input-field"
                      value={uploadTemplateId}
                      onChange={(e) => setUploadTemplateId(e.target.value)}
                      disabled={templates.length === 0}
                    >
                      <option value="">{templates.length === 0 ? 'No templates yet' : 'Primary template'}</option>
                      {/* templates[0] IS the primary template — already covered by the
                          option above, so only list the additional ones here to avoid
                          showing the same template twice under two different labels. */}
                      {templates.slice(1).map((t, i) => (
                        <option key={t.id} value={t.id}>{t.name || `Template ${i + 2}`}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <span className="label invisible block">Upload</span>
                    <label onClick={handleUploadClick} className="btn-primary h-[42px] flex items-center gap-2 cursor-pointer flex-shrink-0">
                      {uploadingProspects ? <LoadingSpinner size="sm" /> : <FiUpload size={16} />}
                      Upload Excel
                      <input type="file" accept={UPLOAD_ACCEPT} onChange={handleUploadProspects} className="hidden" />
                    </label>
                  </div>
                  <div>
                    <span className="label invisible block">Add</span>
                    <button onClick={handleOpenAddProspect} className="btn-primary h-[42px] flex items-center gap-2 flex-shrink-0">
                      <FiUserPlus size={16} /> Prospect List Manually
                    </button>
                  </div>
                  <div>
                    <span className="label invisible block">Refresh</span>
                    <button
                      onClick={handleRefreshProspects}
                      disabled={refreshingProspects}
                      className="btn-secondary h-[42px] flex items-center gap-2 flex-shrink-0"
                      title="Reload the latest prospects/lists without refreshing the page"
                    >
                      {refreshingProspects ? <LoadingSpinner size="sm" /> : <FiRefreshCw size={16} />}
                      Refresh
                    </button>
                  </div>
                </div>
              </div>

              {browseMode === 'all' && (
                <>
                  <div className="mt-4 space-y-3">
                    <div className="flex flex-wrap items-start gap-2">
                      <SearchInput
                        onChange={debouncedSearch}
                        placeholder="Search name, email, company..."
                        className="w-64"
                      />
                      <select className="input-field w-auto text-sm" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                        <option value="name">Sort: Name</option>
                        <option value="email">Sort: Email</option>
                        <option value="company">Sort: Company</option>
                        <option value="designation">Sort: Designation</option>
                        <option value="industry">Sort: Industry</option>
                      </select>
                      <select className="input-field w-auto text-sm" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
                        <option value="asc">Ascending</option>
                        <option value="desc">Descending</option>
                      </select>
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
                      <button onClick={clearAllFilters} className="btn-secondary text-sm">Clear All</button>
                      <button onClick={clearSelection} className="btn-secondary text-sm">Clear Selection</button>
                      <button onClick={handleSelectAllMatching} disabled={selectingAll || total === 0} className="btn-secondary text-sm flex items-center gap-1 ml-auto">
                        {selectingAll ? <LoadingSpinner size="sm" /> : <FiCheckSquare size={14} />} Select All {total} Matching
                      </button>
                    </div>
                  </div>

                  <p className="text-sm text-gray-600 mt-3">
                    <span className="font-semibold text-gray-900">{total}</span> matching prospect{total !== 1 ? 's' : ''}
                    {selectedIds.length > 0 && <span className="ml-2 text-primary-600 font-medium">({selectedIds.length} selected)</span>}
                  </p>

                  {contactsLoading ? (
                    <div className="flex justify-center py-6">
                      <LoadingSpinner size="md" />
                    </div>
                  ) : results.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 mt-3">
                      No prospects found. Upload prospects from the Prospects page or adjust your filters.
                    </div>
                  ) : (
                    <>
                      <div className="space-y-2 max-h-96 overflow-y-auto pr-1 mt-3">
                        {results.map((r) => (
                          <label
                            key={r.id}
                            className={`flex items-start gap-3 rounded-xl border p-3 ${
                              r.is_suppressed
                                ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
                                : 'cursor-pointer border-gray-200 bg-white hover:border-primary-300'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={!r.is_suppressed && selectedIds.includes(r.id)}
                              onChange={() => toggleRecipient(r.id)}
                              disabled={r.is_suppressed}
                              title={r.is_suppressed ? 'Blacklisted prospects cannot be selected' : undefined}
                              className="mt-1 rounded border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
                            />
                            <div className="flex-1">
                              <div className="flex items-center justify-between gap-3">
                                <p className={`font-medium ${r.is_suppressed ? 'text-gray-400' : 'text-gray-900'}`}>{r.name}</p>
                                <span className="text-xs text-gray-500">{r.company || '—'}</span>
                              </div>
                              <p className={`text-sm ${r.is_suppressed ? 'text-gray-400' : 'text-gray-600'}`}>{r.email}</p>
                              <p className="text-xs text-gray-500">
                                {r.designation || '—'} • {r.industry || '—'}
                              </p>
                              {r.is_suppressed && (
                                <div className="mt-1"><StatusBadge status={r.suppression_reason} /></div>
                              )}
                            </div>
                          </label>
                        ))}
                      </div>
                      <div className="mt-2">
                        <Pagination page={page} pageSize={10} total={total} onPageChange={setPage} />
                      </div>
                    </>
                  )}
                </>
              )}

              {browseMode === 'lists' && (
                <div className="mt-4">
                  {!openListId ? (
                    listsLoading ? (
                      <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
                    ) : lists.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
                        No lists yet — upload an Excel file or add a prospect manually above with a List Name to create one.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {lists.map((l) => {
                          const tpl = templates.find((t) => t.id === l.template_id);
                          return (
                            <div
                              key={l.group_id}
                              onClick={() => handleOpenList(l)}
                              role="button"
                              tabIndex={0}
                              onKeyDown={(e) => { if (e.key === 'Enter') handleOpenList(l); }}
                              className="relative text-left cursor-pointer rounded-xl border border-gray-200 bg-white p-4 hover:border-primary-300 hover:shadow-sm transition-all"
                            >
                              <button
                                onClick={(e) => openScheduleList(e, l)}
                                title="Schedule this list"
                                className="absolute top-3 right-9 p-1.5 rounded-lg text-gray-400 hover:text-primary-600 hover:bg-primary-50 transition-colors"
                              >
                                <FiCalendar size={16} />
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); setDeletingList({ group_id: l.group_id, name: l.name }); }}
                                title="Delete this list"
                                className="absolute top-3 right-3 p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                              >
                                <FiTrash2 size={16} />
                              </button>
                              <p className="font-semibold text-gray-900 pr-14">{l.name}</p>
                              <p className="text-sm text-gray-500 mt-1">{l.total} prospect{l.total !== 1 ? 's' : ''}</p>
                              <p className="text-xs text-gray-500 mt-1">Sent {l.sent_count} / {l.total}</p>
                              <p className="text-xs text-gray-500 mt-2">
                                Template: <span className="font-medium text-gray-700">{tpl ? (tpl.name || 'Untitled') : 'No template'}</span>
                              </p>
                              {l.scheduled_at && (
                                <p className="text-xs text-primary-600 mt-2 flex items-center gap-1">
                                  <FiCalendar size={12} /> Scheduled for {new Date(l.scheduled_at).toLocaleString()}
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )
                  ) : (
                    <div>
                      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
                        <button onClick={handleBackToLists} className="btn-secondary text-sm flex items-center gap-2">
                          <FiArrowLeft size={14} /> Back to Lists
                        </button>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setDeletingList({ group_id: openListId, name: openListName })}
                            className="btn-secondary text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                          >
                            <FiTrash2 size={14} /> Delete List
                          </button>
                          <div className="flex items-center gap-1 rounded-lg border border-gray-200 p-1">
                            <button
                              onClick={() => setListDisplayMode('table')}
                              className={`p-1.5 rounded ${listDisplayMode === 'table' ? 'bg-gray-100 text-gray-900' : 'text-gray-400'}`}
                              title="List view"
                            >
                              <FiList size={16} />
                            </button>
                            <button
                              onClick={() => setListDisplayMode('catalog')}
                              className={`p-1.5 rounded ${listDisplayMode === 'catalog' ? 'bg-gray-100 text-gray-900' : 'text-gray-400'}`}
                              title="Catalog view"
                            >
                              <FiGrid size={16} />
                            </button>
                          </div>
                        </div>
                      </div>

                      <h3 className="text-base font-semibold text-gray-900">{openListName}</h3>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <span className="text-sm text-gray-500 mr-1">Add more prospects to this list:</span>
                        <label className="btn-primary text-sm flex items-center gap-2 cursor-pointer">
                          {uploadingToList ? <LoadingSpinner size="sm" /> : <FiUpload size={14} />}
                          Upload Excel
                          <input type="file" accept={UPLOAD_ACCEPT} onChange={handleUploadToList} className="hidden" />
                        </label>
                        <button onClick={handleOpenAddToList} className="btn-primary text-sm flex items-center gap-2">
                          <FiUserPlus size={14} /> Add Manually
                        </button>
                      </div>

                      <div className="mt-3 flex flex-wrap items-end gap-3">
                        <div className="w-full sm:w-56">
                          <label className="label">Default Template</label>
                          <select
                            className="input-field"
                            value={listTemplateId}
                            onChange={(e) => handleChangeListTemplate(e.target.value)}
                            disabled={retaggingList || templates.length === 0}
                          >
                            <option value="">{templates.length === 0 ? 'No templates yet' : 'Primary template'}</option>
                            {templates.slice(1).map((t, i) => (
                              <option key={t.id} value={t.id}>{t.name || `Template ${i + 2}`}</option>
                            ))}
                          </select>
                        </div>
                        <SearchInput
                          key={openListId}
                          onChange={setListSearch}
                          placeholder="Search this list..."
                          className="w-56"
                        />
                        <button onClick={handleSelectAllListMembers} className="btn-secondary text-sm">Select All</button>
                        <button onClick={clearListSelection} className="btn-secondary text-sm">Clear Selection</button>
                      </div>

                      <p className="text-sm text-gray-600 mt-3">
                        <span className="font-semibold text-gray-900">{filteredListMembers.length}</span> prospect{filteredListMembers.length !== 1 ? 's' : ''}
                        {listSelectedIds.length > 0 && <span className="ml-2 text-primary-600 font-medium">({listSelectedIds.length} selected)</span>}
                      </p>

                      {listMembersLoading ? (
                        <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
                      ) : filteredListMembers.length === 0 ? (
                        <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 mt-3">
                          No prospects match.
                        </div>
                      ) : listDisplayMode === 'table' ? (
                        <div className="space-y-2 max-h-96 overflow-y-auto pr-1 mt-3">
                          {filteredListMembers.map((m) => (
                            <label
                              key={m.id}
                              className={`flex items-start gap-3 rounded-xl border p-3 ${
                                m.is_suppressed
                                  ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
                                  : 'cursor-pointer border-gray-200 bg-white hover:border-primary-300'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={!m.is_suppressed && listSelectedIds.includes(m.id)}
                                onChange={() => toggleListRecipient(m.id)}
                                disabled={m.is_suppressed}
                                title={m.is_suppressed ? 'Blacklisted prospects cannot be selected' : undefined}
                                className="mt-1 rounded border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
                              />
                              <div className="flex-1">
                                <div className="flex items-center justify-between gap-3">
                                  <p className={`font-medium ${m.is_suppressed ? 'text-gray-400' : 'text-gray-900'}`}>{m.name}</p>
                                  <StatusBadge status={m.is_suppressed ? m.suppression_reason : m.status} />
                                </div>
                                <p className={`text-sm ${m.is_suppressed ? 'text-gray-400' : 'text-gray-600'}`}>{m.email}</p>
                                <p className="text-xs text-gray-500">{m.company || '—'}</p>
                              </div>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
                          {filteredListMembers.map((m) => (
                            <div
                              key={m.id}
                              className={`rounded-xl border p-3 ${m.is_suppressed ? 'border-gray-200 bg-gray-50' : 'border-gray-200 bg-white'}`}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <input
                                  type="checkbox"
                                  checked={!m.is_suppressed && listSelectedIds.includes(m.id)}
                                  onChange={() => toggleListRecipient(m.id)}
                                  disabled={m.is_suppressed}
                                  className="mt-1 rounded border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
                                />
                                <StatusBadge status={m.is_suppressed ? m.suppression_reason : m.status} />
                              </div>
                              <p className={`font-medium mt-2 ${m.is_suppressed ? 'text-gray-400' : 'text-gray-900'}`}>{m.name}</p>
                              <p className={`text-sm ${m.is_suppressed ? 'text-gray-400' : 'text-gray-600'}`}>{m.email}</p>
                              <p className="text-xs text-gray-500 mt-1">{m.company || '—'}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </div>

        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="card">
              <h2 className="text-lg font-semibold">Statistics</h2>
              <div className="space-y-3 mt-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Emails Sent</span>
                  <span className="font-medium text-gray-900">{campaign.emails_sent}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Last Updated</span>
                  <span className="font-medium text-gray-900">{formatDateTime(campaign.created_at)}</span>
                </div>
              </div>
            </div>

            <div className="card">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <FiMail size={18} /> Next Steps
              </h2>
              <ul className="mt-4 space-y-2 text-sm text-gray-600">
                <li>• Review the campaign details in the Overview tab.</li>
                <li>• Confirm the email content in the Template tab.</li>
                <li>• Select prospects and preview & send from the Prospects tab.</li>
              </ul>
            </div>
          </div>
        )}
      </div>

      <Modal isOpen={previewOpen} onClose={() => setPreviewOpen(false)} title="Preview & Send" size="lg">
        {effectiveTemplate && previewContext && (
          <div className="space-y-4">
            {isListMode && (
              <p className="text-xs text-gray-500">
                Template: <span className="font-medium text-gray-700">{effectiveTemplate.name || 'Untitled'}</span> (this list's default)
              </p>
            )}
            {selectedRecipients.length > 1 && (
              <div>
                <label className="label">Preview as</label>
                <select
                  className="input-field"
                  value={previewRecipientId ?? ''}
                  onChange={(e) => setPreviewRecipientId(Number(e.target.value))}
                >
                  {selectedRecipients.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.email})
                    </option>
                  ))}
                </select>
              </div>
            )}
            <EmailPreview
              subject={renderTemplate(effectiveTemplate.subject, previewContext)}
              recipientName={previewContext.Name}
              body={renderTemplate(effectiveTemplate.body, previewContext)}
              closing={effectiveTemplate.closing}
              cta={effectiveTemplate.cta}
              type={effectiveTemplate.type}
            />
            {!isListMode && templates.length > 1 && (
              <p className="text-xs text-gray-400">
                Showing the primary template — prospects tagged to a different template will receive that one instead.
              </p>
            )}
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
              Sending to {activeSelectedIds.length} prospect{activeSelectedIds.length !== 1 ? 's' : ''}
            </div>
            <div>
              <label className="label">When</label>
              <div className="flex items-center gap-4 mb-2">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="radio"
                    checked={!scheduleAt}
                    onChange={() => setScheduleAt('')}
                  />
                  Send now
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="radio"
                    checked={!!scheduleAt}
                    onChange={() => setScheduleAt((prev) => prev || defaultScheduleValue())}
                  />
                  Schedule for later
                </label>
              </div>
              {scheduleAt && (
                <input
                  type="datetime-local"
                  className="input-field"
                  value={scheduleAt}
                  min={defaultScheduleValue()}
                  onChange={(e) => setScheduleAt(e.target.value)}
                />
              )}
              <label className="flex items-start gap-2 text-sm text-gray-700 mt-3">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={useRecipientTz}
                  onChange={(e) => setUseRecipientTz(e.target.checked)}
                />
                <span>
                  Only send within each prospect's local business hours (9am–6pm)
                  <span className="block text-xs text-gray-400">
                    A send due at 3am their time waits for their next local 9am instead — useful for scheduling
                    ahead of a specific region's market open without staying up for it.
                  </span>
                </span>
              </label>
            </div>
            <div className="flex justify-end gap-3">
              <button
                className="btn-secondary"
                onClick={() => { setPreviewOpen(false); setScheduleAt(''); }}
                disabled={sending}
              >
                Cancel
              </button>
              <button className="btn-primary flex items-center gap-2" onClick={handleSend} disabled={sending}>
                {sending ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <>
                    <FiSend size={16} /> {scheduleAt ? 'Schedule Send' : 'Send Campaign'}
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        isOpen={!!deletingStageId}
        onClose={() => setDeletingStageId(null)}
        onConfirm={handleDeleteStage}
        title="Remove Engagement Studio Stage"
        message="Remove this stage? Prospects already scheduled for it will no longer receive it."
        confirmText="Remove"
      />

      <Modal
        isOpen={templateModalOpen}
        onClose={() => { setTemplateModalOpen(false); setEditingTemplateId(null); }}
        title={editingTemplateId ? 'Edit Template' : 'Add New Template'}
        size="lg"
      >
        <div className="space-y-6">
          <div>
            <label className="label">Template Name</label>
            <input
              className="input-field"
              value={newTemplateName}
              onChange={(e) => setNewTemplateName(e.target.value)}
              placeholder={`Template ${templates.length + 1}`}
              autoFocus
            />
          </div>

          <div className="flex items-center gap-2">
            <select
              className="input-field w-auto text-sm"
              value=""
              onChange={(e) => e.target.value && handleSelectMailer(e.target.value)}
            >
              <option value="">From Saved Mailer...</option>
              {mailers.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            <button
              onClick={() => setSaveMailerModalOpen(true)}
              disabled={!emailContent.subject.trim() || isTemplateBodyEmpty(emailContent.body, templateType)}
              className="btn-secondary text-sm flex items-center gap-1"
            >
              <FiSave size={14} /> Save as Mailer
            </button>
          </div>

          <TemplateEditor
            templateType={templateType}
            onTemplateTypeChange={handleTemplateTypeChange}
            emailContent={emailContent}
            onEmailContentChange={setEmailContent}
            placeholderTemplates={placeholderTemplates}
            selectedTemplate={selectedPlaceholderTemplate}
            onSelectPlaceholderTemplate={handleSelectPlaceholderTemplate}
            placeholderValues={placeholderValues}
            onPlaceholderValueChange={(key, value) => setPlaceholderValues((p) => ({ ...p, [key]: value }))}
            aiPrompt={aiPrompt}
            onAiPromptChange={setAiPrompt}
            onGenerateAI={handleGenerateAI}
            aiLoading={aiLoading}
            previewContext={templatePreviewContext}
          />

          <div className="flex justify-end gap-3 pt-2 border-t border-gray-100">
            <button onClick={() => setTemplateModalOpen(false)} className="btn-secondary" disabled={savingTemplate}>
              Cancel
            </button>
            <button onClick={handleSaveTemplate} disabled={savingTemplate} className="btn-primary flex items-center gap-2">
              {savingTemplate ? <LoadingSpinner size="sm" /> : <FiPlus size={16} />} {editingTemplateId ? 'Save Changes' : 'Save Template'}
            </button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={saveMailerModalOpen} onClose={() => setSaveMailerModalOpen(false)} title="Save as Mailer" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Save this template to the reusable Mailer library so it can be found and loaded into future campaigns.
          </p>
          <div>
            <label className="label">Mailer Name *</label>
            <input
              className="input-field"
              value={newMailerName}
              onChange={(e) => setNewMailerName(e.target.value)}
              placeholder="e.g. Cold Outreach - Tech Decision Makers"
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setSaveMailerModalOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleConfirmSaveMailer} disabled={savingMailer} className="btn-primary flex items-center gap-2">
              {savingMailer ? <LoadingSpinner size="sm" /> : <><FiBookOpen size={16} /> Save Mailer</>}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!deletingTemplateId}
        onClose={() => setDeletingTemplateId(null)}
        onConfirm={handleDeleteTemplate}
        title="Remove Template"
        message="Remove this template? Prospects currently tagged to it will fall back to the campaign's primary template."
        confirmText="Remove"
      />

      <ConfirmDialog
        isOpen={!!unknownFields}
        onClose={() => setUnknownFields(null)}
        onConfirm={handleProceedWithUnknownFields}
        variant="primary"
        title="Unrecognized Field"
        message={
          unknownFields
            ? `This template uses ${unknownFields.map((f) => `{{${f}}}`).join(', ')} — not one of the standard prospect fields. You can go back and fix it, or proceed anyway: it'll render blank until prospect data exists for it, and won't be flagged again.`
            : ''
        }
        confirmText="Proceed Anyway"
        cancelText="Go Back & Edit"
      />

      <Modal isOpen={addProspectModalOpen} onClose={() => setAddProspectModalOpen(false)} title="Add Prospect Manually" size="md">
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Adding to list: <span className="font-medium text-gray-700">{addRecipientGroupName || '—'}</span>
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Name *</label>
              <input
                className="input-field"
                value={recipientForm.name}
                onChange={(e) => setRecipientForm((p) => ({ ...p, name: e.target.value }))}
                autoFocus
              />
            </div>
            <div>
              <label className="label">Email *</label>
              <input
                type="email"
                className="input-field"
                value={recipientForm.email}
                onChange={(e) => setRecipientForm((p) => ({ ...p, email: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Company</label>
              <input
                className="input-field"
                value={recipientForm.company}
                onChange={(e) => setRecipientForm((p) => ({ ...p, company: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Designation</label>
              <input
                className="input-field"
                value={recipientForm.designation}
                onChange={(e) => setRecipientForm((p) => ({ ...p, designation: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Industry</label>
              <input
                className="input-field"
                value={recipientForm.industry}
                onChange={(e) => setRecipientForm((p) => ({ ...p, industry: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Tag to template</label>
              <select
                className="input-field"
                value={recipientTemplateId}
                onChange={(e) => setRecipientTemplateId(e.target.value)}
                disabled={templates.length === 0}
              >
                <option value="">{templates.length === 0 ? 'No templates yet' : 'Primary template'}</option>
                {templates.slice(1).map((t, i) => (
                  <option key={t.id} value={t.id}>{t.name || `Template ${i + 2}`}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setAddProspectModalOpen(false)} className="btn-secondary" disabled={savingRecipient}>
              Cancel
            </button>
            <button onClick={handleAddRecipient} disabled={savingRecipient} className="btn-primary flex items-center gap-2">
              {savingRecipient ? <LoadingSpinner size="sm" /> : <FiUserPlus size={16} />} Add Prospect
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={!!scheduleModalList}
        onClose={closeScheduleList}
        title={`Schedule "${scheduleModalList?.name ?? ''}"`}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Every unsent prospect in this list will be queued and sent automatically starting at the time below,
            staggered to protect deliverability.
          </p>
          <div className="flex gap-2">
            {[
              { label: 'Tomorrow', days: 1 },
              { label: 'In 3 days', days: 3 },
              { label: 'In 1 week', days: 7 },
            ].map(({ label, days }) => (
              <button
                key={days}
                onClick={() => setScheduleListValue(toDateTimeLocalValue(new Date(Date.now() + days * 24 * 60 * 60 * 1000)))}
                className="btn-secondary text-xs px-2 py-1"
              >
                {label}
              </button>
            ))}
          </div>
          <div>
            <label className="label">Send at</label>
            <input
              type="datetime-local"
              className="input-field"
              value={scheduleListValue}
              min={defaultScheduleValue()}
              onChange={(e) => setScheduleListValue(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={closeScheduleList} className="btn-secondary" disabled={schedulingList}>
              Cancel
            </button>
            <button
              onClick={handleScheduleList}
              disabled={schedulingList || !scheduleListValue}
              className="btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              {schedulingList ? <LoadingSpinner size="sm" /> : <FiCalendar size={16} />} Schedule
            </button>
          </div>
        </div>
      </Modal>

      <UploadErrorModal
        isOpen={!!uploadMissingColumns}
        onClose={() => setUploadMissingColumns(null)}
        missingColumns={uploadMissingColumns || []}
      />
      <ConfirmDialog
        isOpen={!!pendingProspectsUpload}
        onClose={() => setPendingProspectsUpload(null)}
        onConfirm={handleConfirmProspectsUpload}
        variant="primary"
        title="Duplicate Prospects Detected"
        message={
          pendingProspectsUpload
            ? buildDuplicateUploadMessage(pendingProspectsUpload.total, pendingProspectsUpload.duplicateCount)
            : ''
        }
        confirmText="Import Anyway"
      />
      <ConfirmDialog
        isOpen={!!pendingListUpload}
        onClose={() => setPendingListUpload(null)}
        onConfirm={handleConfirmListUpload}
        variant="primary"
        title="Duplicate Prospects Detected"
        message={
          pendingListUpload
            ? buildDuplicateUploadMessage(pendingListUpload.total, pendingListUpload.duplicateCount)
            : ''
        }
        confirmText="Import Anyway"
      />
      <ConfirmDialog
        isOpen={!!deletingList}
        onClose={() => setDeletingList(null)}
        onConfirm={handleDeleteList}
        title="Delete Prospect List"
        message={`Delete "${deletingList?.name}"? Prospects stay in the system — this only removes the list.`}
        confirmText="Delete"
      />
    </div>
  );
}
