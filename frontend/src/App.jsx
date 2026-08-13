import { Routes, Route, Navigate } from 'react-router-dom';
import ProtectedRoute from './components/ProtectedRoute';
import MainLayout from './layouts/MainLayout';
import LoginPage from './pages/LoginPage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import DashboardPage from './pages/DashboardPage';
import CampaignsPage from './pages/CampaignsPage';
import CreateCampaignPage from './pages/CreateCampaignPage';
import CampaignDetailPage from './pages/CampaignDetailPage';
import RecipientsPage from './pages/RecipientsPage';
import TemplatesPage from './pages/TemplatesPage';
import EmailLogsPage from './pages/EmailLogsPage';
import SettingsPage from './pages/SettingsPage';
import BlacklistPage from './pages/BlacklistPage';
import SalesNavExtractPage from './pages/SalesNavExtractPage';
import LinkedInProfileExtractorPage from './pages/LinkedInProfileExtractorPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/campaigns" element={<CampaignsPage />} />
          <Route path="/campaigns/create" element={<CreateCampaignPage />} />
          <Route path="/campaigns/:id" element={<CampaignDetailPage />} />
          <Route path="/campaigns/:id/edit" element={<CreateCampaignPage />} />
          <Route path="/recipients" element={<RecipientsPage />} />
          <Route path="/blacklist" element={<BlacklistPage />} />
          <Route path="/recipient-groups" element={<Navigate to="/recipients" replace />} />
          <Route path="/prospects/search" element={<Navigate to="/recipients" replace />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/logs" element={<EmailLogsPage />} />
          <Route path="/salesnav" element={<SalesNavExtractPage />} />
          <Route path="/linkedin-extractor" element={<LinkedInProfileExtractorPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
