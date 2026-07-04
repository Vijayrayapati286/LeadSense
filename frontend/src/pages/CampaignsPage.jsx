import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiPlus, FiEdit2, FiTrash2, FiEye } from 'react-icons/fi';
import { campaignService } from '../services/services';
import { useToast } from '../hooks/useToast';
import StatusBadge from '../components/ui/StatusBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatDate } from '../utils/helpers';

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState(null);
  const toast = useToast();

  useEffect(() => {
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    try {
      const { data } = await campaignService.getAll();
      setCampaigns(data);
    } catch {
      toast.error('Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await campaignService.delete(id);
      setCampaigns((prev) => prev.filter((c) => c.id !== id));
      toast.success('Campaign deleted');
    } catch {
      toast.error('Failed to delete campaign');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
          <p className="text-gray-500 mt-1">Manage your email campaigns</p>
        </div>
        <Link to="/campaigns/create" className="btn-primary flex items-center gap-2">
          <FiPlus size={18} />
          Create Campaign
        </Link>
      </div>

      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr className="text-left text-gray-500">
                <th className="px-6 py-3 font-medium">Campaign Name</th>
                <th className="px-6 py-3 font-medium">Campaign ID</th>
                <th className="px-6 py-3 font-medium">Owner</th>
                <th className="px-6 py-3 font-medium">Created Date</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Emails Sent</th>
                <th className="px-6 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-6 py-4 font-medium text-gray-900">{c.campaign_name}</td>
                  <td className="px-6 py-4 text-gray-600 font-mono text-xs">{c.campaign_id}</td>
                  <td className="px-6 py-4 text-gray-600">{c.owner}</td>
                  <td className="px-6 py-4 text-gray-600">{formatDate(c.created_at)}</td>
                  <td className="px-6 py-4">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-6 py-4 text-gray-600">{c.emails_sent}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-1">
                      <Link
                        to={`/campaigns/${c.id}`}
                        className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-primary-600"
                        title="View"
                      >
                        <FiEye size={16} />
                      </Link>
                      <Link
                        to={`/campaigns/${c.id}/edit`}
                        className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-primary-600"
                        title="Edit"
                      >
                        <FiEdit2 size={16} />
                      </Link>
                      <button
                        onClick={() => setDeleteId(c.id)}
                        className="p-2 rounded-lg hover:bg-red-50 text-gray-500 hover:text-red-600"
                        title="Delete"
                      >
                        <FiTrash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {campaigns.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
                    No campaigns yet. Create your first campaign to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmDialog
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        onConfirm={() => handleDelete(deleteId)}
        title="Delete Campaign"
        message="Are you sure you want to delete this campaign? This action cannot be undone."
        confirmText="Delete"
      />
    </div>
  );
}
