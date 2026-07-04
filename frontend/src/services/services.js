import api from './api';

export const authService = {
  getLoginUrl: () => api.get('/auth/login'),
  devLogin: () => api.post('/auth/dev-login'),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
};

export const dashboardService = {
  getStats: () => api.get('/dashboard/stats'),
};

export const campaignService = {
  create: (data) => api.post('/campaign', data),
  getAll: () => api.get('/campaigns'),
  getById: (id) => api.get(`/campaign/${id}`),
  getTemplate: (id) => api.get(`/campaign/${id}/template`),
  update: (id, data) => api.put(`/campaign/${id}`, data),
  delete: (id) => api.delete(`/campaign/${id}`),
  saveTemplate: (id, data) => api.post(`/campaign/${id}/template`, data),
};

export const recipientService = {
  uploadExcel: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/recipients/upload-excel', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getAll: (params) => api.get('/recipients', { params }),
  selectRecipients: (data) => api.post('/recipients/select-recipients', data),
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
