import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FiArrowLeft, FiEdit2, FiMail } from 'react-icons/fi';
import { campaignService } from '../services/services';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import { formatDate, formatDateTime } from '../utils/helpers';

export default function CampaignDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [campaign, setCampaign] = useState(null);
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadCampaign = async () => {
      try {
        const [campaignRes, templateRes] = await Promise.all([
          campaignService.getById(id),
          campaignService.getTemplate(id).catch(() => null),
        ]);
        setCampaign(campaignRes.data);
        setTemplate(templateRes?.data ?? null);
      } catch {
        toast.error('Failed to load campaign details');
      } finally {
        setLoading(false);
      }
    };

    loadCampaign();
  }, [id, toast]);

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
            <h1 className="text-2xl font-bold text-gray-900">{campaign.campaign_name}</h1>
            <p className="text-gray-500 mt-1">{campaign.campaign_id}</p>
          </div>
        </div>
        <button onClick={() => navigate(`/campaigns/${id}/edit`)} className="btn-primary flex items-center gap-2">
          <FiEdit2 size={16} /> Edit Campaign
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
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
            </div>
            {campaign.description && (
              <div className="mt-4">
                <p className="text-gray-500">Description</p>
                <p className="text-gray-700 mt-1">{campaign.description}</p>
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold">Email Template</h2>
            {template ? (
              <div className="mt-4 space-y-3 text-sm">
                <div>
                  <p className="text-gray-500">Type</p>
                  <p className="font-medium text-gray-900 capitalize">{template.type}</p>
                </div>
                <div>
                  <p className="text-gray-500">Subject</p>
                  <p className="font-medium text-gray-900">{template.subject}</p>
                </div>
                <div>
                  <p className="text-gray-500">Body</p>
                  <p className="text-gray-700 whitespace-pre-wrap">{template.body}</p>
                </div>
                {template.closing && (
                  <div>
                    <p className="text-gray-500">Closing</p>
                    <p className="text-gray-700 whitespace-pre-wrap">{template.closing}</p>
                  </div>
                )}
                {template.cta && (
                  <div>
                    <p className="text-gray-500">CTA</p>
                    <p className="text-gray-700">{template.cta}</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-500 mt-4">No template has been saved for this campaign yet.</p>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="card">
            <h2 className="text-lg font-semibold">Quick Stats</h2>
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
              <li>• Review the campaign details before sending.</li>
              <li>• Ensure recipients are uploaded and selected.</li>
              <li>• Send the campaign from the create flow when ready.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
