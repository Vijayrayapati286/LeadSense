import { useEffect, useState } from 'react';
import {
  FiMail,
  FiSend,
  FiClock,
  FiAlertCircle,
  FiActivity,
  FiZap,
} from 'react-icons/fi';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { dashboardService } from '../services/services';
import { useToast } from '../hooks/useToast';
import StatCard from '../components/ui/StatCard';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatDate } from '../utils/helpers';

const PIE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'];

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const { data: stats } = await dashboardService.getStats();
      setData(stats);
    } catch {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!data) return null;

  const { stats, emails_per_day, campaign_status, recent_activity, recent_campaigns } = data;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Overview of your email campaign performance</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard title="Total Campaigns" value={stats.total_campaigns} icon={FiMail} color="primary" />
        <StatCard title="Emails Sent" value={stats.emails_sent} icon={FiSend} color="green" />
        <StatCard title="Pending Emails" value={stats.pending_emails} icon={FiClock} color="amber" />
        <StatCard title="Failed Emails" value={stats.failed_emails} icon={FiAlertCircle} color="red" />
        <StatCard title="Active Campaigns" value={stats.active_campaigns} icon={FiActivity} color="blue" />
        <StatCard title="AI Generated" value={stats.ai_generated_emails} icon={FiZap} color="purple" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Emails Sent Per Day</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={emails_per_day}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 12 }} stroke="#94a3b8" />
              <Tooltip
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0' }}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Campaign Status</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={campaign_status}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ status, count }) => `${status}: ${count}`}
              >
                {campaign_status.map((_, index) => (
                  <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent Activity & Campaigns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Activity</h3>
          <div className="space-y-3">
            {recent_activity.map((item) => (
              <div key={item.id} className="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50">
                <div className="w-2 h-2 mt-2 rounded-full bg-primary-500 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">{item.action}</p>
                  <p className="text-xs text-gray-500 truncate">{item.description}</p>
                </div>
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  {formatDate(item.timestamp)}
                </span>
              </div>
            ))}
            {recent_activity.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-4">No recent activity</p>
            )}
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Campaigns</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium text-right">Sent</th>
                </tr>
              </thead>
              <tbody>
                {recent_campaigns.map((c) => (
                  <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2.5 font-medium text-gray-900">{c.campaign_name}</td>
                    <td className="py-2.5">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="py-2.5 text-right text-gray-600">{c.emails_sent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
