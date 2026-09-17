import { Routes, Route, Navigate } from 'react-router-dom';
import ProtectedRoute from './components/ProtectedRoute';
import MainLayout from './layouts/MainLayout';
import LoginPage from './pages/LoginPage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import DashboardPage from './pages/DashboardPage';
import AdminDashboardPage from './pages/AdminDashboardPage';
import UsersPage from './pages/UsersPage';
import InvitesPage from './pages/InvitesPage';
import CampaignsPage from './pages/CampaignsPage';
import CreateCampaignPage from './pages/CreateCampaignPage';
import CampaignDetailPage from './pages/CampaignDetailPage';
import RecipientsPage from './pages/RecipientsPage';
import TemplatesPage from './pages/TemplatesPage';
import EmailLogsPage from './pages/EmailLogsPage';
import SettingsPage from './pages/SettingsPage';
import BlacklistPage from './pages/BlacklistPage';
import AccountsPage from './pages/AccountsPage';
import ContactsPage from './pages/ContactsPage';
import LinkedInProfileExtractorPage from './pages/LinkedInProfileExtractorPage';
import BulkHistoryPage from './pages/BulkHistoryPage';
import BulkJobDetailPage from './pages/BulkJobDetailPage';
import BulkNeedsReviewPage from './pages/BulkNeedsReviewPage';
import BulkBackupsPage from './pages/BulkBackupsPage';
import OfferingsPage from './pages/OfferingsPage';
import OfferingCreatePage from './pages/OfferingCreatePage';
import OfferingDetailPage from './pages/OfferingDetailPage';
import OrganizationsPage from './pages/OrganizationsPage';
import { useAuth } from './hooks/useAuth';

function DashboardEntry() {
  const { user } = useAuth();
  if (user?.role === 'ADMIN') {
    return <AdminDashboardPage />;
  }
  return <DashboardPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<DashboardEntry />} />
          <Route path="/admin-dashboard" element={<AdminDashboardPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/invites" element={<InvitesPage />} />
          <Route path="/organizations" element={<OrganizationsPage />} />
          <Route path="/campaigns" element={<CampaignsPage />} />
          <Route path="/campaigns/create" element={<CreateCampaignPage />} />
          <Route path="/campaigns/:id" element={<CampaignDetailPage />} />
          <Route path="/campaigns/:id/edit" element={<CreateCampaignPage />} />
          <Route path="/recipients" element={<RecipientsPage />} />
          <Route path="/recipient-groups" element={<Navigate to="/recipients" replace />} />
          <Route path="/prospects/search" element={<Navigate to="/recipients" replace />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/logs" element={<EmailLogsPage />} />
          <Route path="/blacklist" element={<BlacklistPage />} />
          <Route path="/icp-accounts" element={<AccountsPage />} />
          <Route path="/icp-contacts" element={<ContactsPage />} />
          <Route path="/icp-database" element={<Navigate to="/icp-contacts" replace />} />
          <Route path="/salesnav" element={<Navigate to="/linkedin-extractor" replace />} />
          <Route path="/linkedin-extractor" element={<LinkedInProfileExtractorPage />} />
          <Route path="/linkedin-history" element={<BulkHistoryPage />} />
          <Route path="/linkedin-history/:jobId" element={<BulkJobDetailPage />} />
          <Route path="/linkedin-needs-review" element={<BulkNeedsReviewPage />} />
          <Route path="/linkedin-backups" element={<BulkBackupsPage />} />
          <Route path="/offerings" element={<OfferingsPage />} />
          <Route path="/offerings/new" element={<OfferingCreatePage />} />
          <Route path="/offerings/:id/edit" element={<OfferingCreatePage />} />
          <Route path="/offerings/:id" element={<OfferingDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
