import api from './api';

async function downloadViaMeta(metaEndpoint, fallbackFilename) {
  const meta = await api.get(metaEndpoint, { timeout: 120_000 }).then((r) => r.data);
  const filename = meta.filename || fallbackFilename;
  if (meta.file_id && String(meta.download_url || '').includes('/api/files/')) {
    const { data: blob } = await api.get(`/files/${meta.file_id}/content`, {
      responseType: 'blob',
      timeout: 120_000,
    });
    return { blob, filename, ...meta };
  }
  const resp = await fetch(meta.download_url);
  if (!resp.ok) {
    throw new Error('Download failed');
  }
  const blob = await resp.blob();
  return { blob, filename, ...meta };
}

export const authService = {
  getLoginUrl: () => api.get('/auth/login'),
  devLogin: (data) => api.post('/auth/dev-login', data),
  passwordLogin: (email, password) => api.post('/auth/login', { email, password }),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
};

export const dashboardService = {
  getStats: (params) => api.get('/dashboard/stats', { params }),
  exportReport: (params) => api.get('/dashboard/export-report', { params, responseType: 'blob' }),
};

export const userService = {
  getAll: () => api.get('/users'),
};

export const campaignService = {
  create: (data) => api.post('/campaign', data),
  getAll: () => api.get('/campaigns'),
  getById: (id) => api.get(`/campaign/${id}`),
  getTemplate: (id) => api.get(`/campaign/${id}/template`),
  getTemplates: (id) => api.get(`/campaign/${id}/templates`),
  deleteTemplate: (templateId) => api.delete(`/campaign/template/${templateId}`),
  updateTemplate: (templateId, data) => api.put(`/campaign/template/${templateId}`, data),
  update: (id, data) => api.put(`/campaign/${id}`, data),
  delete: (id) => api.delete(`/campaign/${id}`),
  saveTemplate: (id, data) => api.post(`/campaign/${id}/template`, data),
  getLists: (id) => api.get(`/campaign/${id}/lists`),
  getListMembers: (id, groupId) => api.get(`/campaign/${id}/lists/${groupId}/recipients`),
  retagList: (id, groupId, templateId) => api.put(`/campaign/${id}/lists/${groupId}/template`, { template_id: templateId }),
  scheduleList: (id, groupId, scheduledAt) => api.post(`/campaign/${id}/lists/${groupId}/schedule`, { scheduled_at: scheduledAt }),
};

export const sequenceService = {
  getAll: (campaignId) => api.get(`/campaign/${campaignId}/sequence`),
  create: (campaignId, data) => api.post(`/campaign/${campaignId}/sequence`, data),
  delete: (stageId) => api.delete(`/campaign/sequence/${stageId}`),
};

export const recipientService = {
  uploadExcel: (file, groupName, campaignId, templateId, confirm = false) => {
    const formData = new FormData();
    formData.append('file', file);
    if (groupName) formData.append('group_name', groupName);
    if (campaignId) formData.append('campaign_id', campaignId);
    if (templateId) formData.append('template_id', templateId);
    if (confirm) formData.append('confirm', 'true');
    return api.post('/recipients/upload-excel', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  create: (data) => api.post('/recipients', data),
  getAll: (params) => api.get('/recipients', { params }),
  search: (params) => api.get('/recipients/search', { params }),
  searchIds: (params) => api.get('/recipients/search-ids', { params }),
  export: (params) => api.get('/recipients/export', { params, responseType: 'blob' }),
  distinctValues: (fieldName) => api.get('/recipients/distinct-values', { params: { field: fieldName } }),
  tagResponse: (recipientIds, tag) => api.post('/recipients/response-tag', { recipient_ids: recipientIds, tag }),
};

export const savedSearchService = {
  getAll: () => api.get('/recipients/saved-searches'),
  create: (data) => api.post('/recipients/saved-searches', data),
  delete: (id) => api.delete(`/recipients/saved-searches/${id}`),
};

export const recipientGroupService = {
  getAll: (params) => api.get('/recipient-groups', { params }),
  create: (data) => api.post('/recipient-groups', data),
  update: (id, data) => api.put(`/recipient-groups/${id}`, data),
  delete: (id) => api.delete(`/recipient-groups/${id}`),
  addMembers: (id, recipientIds) => api.post(`/recipient-groups/${id}/members`, { recipient_ids: recipientIds }),
};

export const templateService = {
  getPlaceholderTemplates: () => api.get('/templates/placeholder-templates'),
  generateAI: (data) => api.post('/templates/generate-ai-template', data),
};

export const emailService = {
  send: (data) => api.post('/email/send', data),
};

export const logService = {
  getAll: (params) => api.get('/logs', { params }),
};

export const blacklistService = {
  getAll: (params) => api.get('/blacklist', { params }),
  override: (id) => api.post(`/blacklist/${id}/override`),
};

export const tagService = {
  getAll: (params) => api.get('/tags', { params }),
  create: (data) => api.post('/tags', data),
  delete: (id) => api.delete(`/tags/${id}`),
  assign: (id, recipientIds) => api.post(`/tags/${id}/members`, { recipient_ids: recipientIds }),
  unassign: (id, recipientId) => api.delete(`/tags/${id}/members/${recipientId}`),
};

export const customFieldService = {
  getAll: () => api.get('/custom-fields'),
  create: (name) => api.post('/custom-fields', { name }),
};

export const appSettingsService = {
  get: () => api.get('/settings/app'),
  update: (data) => api.put('/settings/app', data),
};

export const mailerService = {
  getAll: (params) => api.get('/mailers', { params }),
  create: (data) => api.post('/mailers', data),
  update: (id, data) => api.put(`/mailers/${id}`, data),
  delete: (id) => api.delete(`/mailers/${id}`),
};

export const linkedinProfileService = {
  extract: (url) =>
    api.post('/linkedin/extract', { url }, { timeout: 180_000 }).then((r) => r.data),
  bulkExtract: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/linkedin/bulk-extract', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    }).then((r) => r.data);
  },
  getBulkJob: (jobId) => api.get(`/linkedin/bulk-jobs/${jobId}`).then((r) => r.data),
  downloadBulkJob: (jobId) => downloadViaMeta(`/linkedin/bulk-jobs/${jobId}/download`, `bulk_${jobId}.xlsx`),
  listBulkJobs: (params = {}) =>
    api.get('/linkedin/bulk-jobs', { params }).then((r) => r.data),
  listBulkJobItems: (jobId, params = {}) =>
    api.get(`/linkedin/bulk-jobs/${jobId}/items`, { params }).then((r) => r.data),
  getBulkConflicts: (jobId, params = {}) =>
    api.get(`/linkedin/bulk-jobs/${jobId}/conflicts`, { params }).then((r) => r.data),
  getBulkJobAudit: (jobId) =>
    api.get(`/linkedin/bulk-jobs/${jobId}/audit`).then((r) => r.data),
  resolveConflict: (jobId, itemId, decisions) =>
    api
      .post(`/linkedin/bulk-jobs/${jobId}/conflicts/${itemId}/resolve`, { decisions })
      .then((r) => r.data),
  bulkResolveConflicts: (jobId, payload) =>
    api.post(`/linkedin/bulk-jobs/${jobId}/conflicts/bulk-resolve`, payload).then((r) => r.data),
  createBulkBackup: (jobId) =>
    api.post(`/linkedin/bulk-jobs/${jobId}/backup`).then((r) => r.data),
  downloadBulkJobBackup: (jobId) =>
    api.get(`/linkedin/bulk-jobs/${jobId}/backup/download`, {
      responseType: 'blob',
      timeout: 120_000,
    }),
  listBulkBackups: () => api.get('/linkedin/bulk-backups').then((r) => r.data),
  downloadBackup: (backupId) =>
    api.get(`/linkedin/bulk-backups/${backupId}/download`, {
      responseType: 'blob',
      timeout: 120_000,
    }),
  restoreBulkBackup: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api
      .post('/linkedin/bulk-backups/restore', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      })
      .then((r) => r.data);
  },
};

export const icpService = {
  list: (params = {}) => api.get('/icp', { params }).then((r) => r.data),
  get: (id) => api.get(`/icp/${id}`).then((r) => r.data),
  create: (payload) => api.post('/icp', payload).then((r) => r.data),
  update: (id, payload) => api.put(`/icp/${id}`, payload).then((r) => r.data),
  remove: (id) => api.delete(`/icp/${id}`).then((r) => r.data),
};

export const offeringsService = {
  list: (params = {}) => api.get('/offerings', { params }).then((r) => r.data),
  get: (id) => api.get(`/offerings/${id}`).then((r) => r.data),
  create: (payload) => api.post('/offerings', payload).then((r) => r.data),
  update: (id, payload) => api.put(`/offerings/${id}`, payload).then((r) => r.data),
  remove: (id) => api.delete(`/offerings/${id}`).then((r) => r.data),
  generateIcp: (description) =>
    api.post('/offerings/generate-icp', { description }, { timeout: 120_000 }).then((r) => r.data),
  stats: (id) => api.get(`/offerings/${id}/stats`).then((r) => r.data),
  startMatch: (id, force = false, verifiedOnly = true) =>
    api.post(`/offerings/${id}/match`, null, { params: { force, verified_only: verifiedOnly } }).then((r) => r.data),
  matchingStatus: (id) => api.get(`/offerings/${id}/matching-status`).then((r) => r.data),
  listMatches: (id, params = {}) =>
    api.get(`/offerings/${id}/matches`, { params }).then((r) => r.data),
  approveMatch: (id, matchId) =>
    api.post(`/offerings/${id}/matches/${matchId}/approve`).then((r) => r.data),
  rejectMatch: (id, matchId) =>
    api.post(`/offerings/${id}/matches/${matchId}/reject`).then((r) => r.data),
  matchesForIcp: (icpRecordId, params = {}) =>
    api.get(`/offerings/by-icp/${icpRecordId}`, { params }).then((r) => r.data),
  feedback: (matchId, action) =>
    api.post(`/offerings/matches/${matchId}/feedback`, { action }).then((r) => r.data),
  prepareCampaignRecipients: (id, payload) =>
    api.post(`/offerings/${id}/prepare-campaign-recipients`, payload).then((r) => r.data),
};
