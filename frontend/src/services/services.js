import api from './api';

export const authService = {
  getLoginUrl: () => api.get('/auth/login'),
  devLogin: (data) => api.post('/auth/dev-login', data),
  passwordLogin: (email, password) => api.post('/auth/login', { email, password }),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
};

export const dashboardService = {
  getStats: () => api.get('/dashboard/stats'),
  exportReport: () => api.get('/dashboard/export-report', { responseType: 'blob' }),
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
  getRecipients: (id) => api.get(`/campaign/${id}/recipients`),
  getLists: (id) => api.get(`/campaign/${id}/lists`),
  getListMembers: (id, groupId) => api.get(`/campaign/${id}/lists/${groupId}/recipients`),
  retagList: (id, groupId, templateId) => api.put(`/campaign/${id}/lists/${groupId}/template`, { template_id: templateId }),
  scheduleList: (id, groupId, scheduledAt) => api.post(`/campaign/${id}/lists/${groupId}/schedule`, { scheduled_at: scheduledAt }),
};

export const sequenceService = {
  getAll: (campaignId) => api.get(`/campaign/${campaignId}/sequence`),
  create: (campaignId, data) => api.post(`/campaign/${campaignId}/sequence`, data),
  update: (stageId, data) => api.put(`/campaign/sequence/${stageId}`, data),
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
  selectRecipients: (data) => api.post('/recipients/select-recipients', data),
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
  getById: (id) => api.get(`/recipient-groups/${id}`),
  create: (data) => api.post('/recipient-groups', data),
  update: (id, data) => api.put(`/recipient-groups/${id}`, data),
  delete: (id) => api.delete(`/recipient-groups/${id}`),
  getMembers: (id, params) => api.get(`/recipient-groups/${id}/members`, { params }),
  addMembers: (id, recipientIds) => api.post(`/recipient-groups/${id}/members`, { recipient_ids: recipientIds }),
  removeMember: (id, recipientId) => api.delete(`/recipient-groups/${id}/members/${recipientId}`),
};

export const templateService = {
  getPlaceholderTemplates: () => api.get('/templates/placeholder-templates'),
  generateAI: (data) => api.post('/templates/generate-ai-template', data),
  preview: (data) => api.post('/templates/preview-template', data),
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
  getById: (id) => api.get(`/mailers/${id}`),
  create: (data) => api.post('/mailers', data),
  update: (id, data) => api.put(`/mailers/${id}`, data),
  delete: (id) => api.delete(`/mailers/${id}`),
};
