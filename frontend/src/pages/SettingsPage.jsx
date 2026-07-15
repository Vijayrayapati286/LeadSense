import { useEffect, useState } from 'react';
import { FiUser, FiMail, FiBriefcase, FiShield, FiSliders, FiSave } from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { appSettingsService } from '../services/services';
import { RESPONSE_TAGS } from '../components/FilterBuilder';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function SettingsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [appSettings, setAppSettings] = useState(null);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  useEffect(() => {
    appSettingsService.get()
      .then(({ data }) => setAppSettings(data))
      .catch(() => toast.error('Failed to load deliverability settings'))
      .finally(() => setLoadingSettings(false));
  }, [toast]);

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      const { data } = await appSettingsService.update({
        soft_bounce_threshold: Number(appSettings.soft_bounce_threshold),
        send_interval_seconds: Number(appSettings.send_interval_seconds),
        suppress_on_tags: appSettings.suppress_on_tags,
      });
      setAppSettings(data);
      toast.success('Deliverability settings saved');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  const toggleSuppressOnTag = (tag) => {
    setAppSettings((p) => ({
      ...p,
      suppress_on_tags: p.suppress_on_tags.includes(tag)
        ? p.suppress_on_tags.filter((t) => t !== tag)
        : [...p.suppress_on_tags, tag],
    }));
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Manage your account and application preferences</p>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-4">Profile Information</h2>
        <div className="space-y-4">
          <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
            <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center">
              <FiUser className="text-primary-600" size={24} />
            </div>
            <div>
              <p className="font-medium text-gray-900">{user?.name}</p>
              <p className="text-sm text-gray-500">Authenticated via Microsoft SSO</p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4">
            <div className="flex items-center gap-3 p-3 border border-gray-100 rounded-lg">
              <FiMail className="text-gray-400" size={18} />
              <div>
                <p className="text-xs text-gray-500">Email</p>
                <p className="text-sm font-medium">{user?.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 border border-gray-100 rounded-lg">
              <FiBriefcase className="text-gray-400" size={18} />
              <div>
                <p className="text-xs text-gray-500">Department</p>
                <p className="text-sm font-medium">{user?.department || 'Sales'}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
          <FiSliders size={20} /> Deliverability
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          Controls how aggressively bounces get suppressed and how fast campaigns send.
        </p>
        {loadingSettings ? (
          <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
        ) : appSettings && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="label">Soft Bounce Threshold</label>
                <input
                  type="number"
                  min={1}
                  className="input-field"
                  value={appSettings.soft_bounce_threshold}
                  onChange={(e) => setAppSettings((p) => ({ ...p, soft_bounce_threshold: e.target.value }))}
                />
                <p className="text-xs text-gray-400 mt-1">Retries before a repeatedly soft-bouncing address is suppressed.</p>
              </div>
              <div>
                <label className="label">Send Interval (seconds)</label>
                <input
                  type="number"
                  min={1}
                  className="input-field"
                  value={appSettings.send_interval_seconds}
                  onChange={(e) => setAppSettings((p) => ({ ...p, send_interval_seconds: e.target.value }))}
                />
                <p className="text-xs text-gray-400 mt-1">Minimum gap enforced between each outgoing campaign email.</p>
              </div>
            </div>

            <div>
              <label className="label">Auto-Suppress On Response Tag</label>
              <p className="text-xs text-gray-400 mb-2">
                Prospects manually tagged with a checked response are blacklisted immediately.
              </p>
              <div className="flex flex-wrap gap-3">
                {RESPONSE_TAGS.map((tag) => (
                  <label key={tag} className="flex items-center gap-2 text-sm px-3 py-2 border border-gray-200 rounded-lg cursor-pointer">
                    <input
                      type="checkbox"
                      checked={appSettings.suppress_on_tags.includes(tag)}
                      onChange={() => toggleSuppressOnTag(tag)}
                      className="rounded border-gray-300"
                    />
                    {tag}
                  </label>
                ))}
              </div>
            </div>

            <button onClick={handleSaveSettings} disabled={savingSettings} className="btn-primary flex items-center gap-2">
              {savingSettings ? <LoadingSpinner size="sm" /> : <><FiSave size={16} /> Save Settings</>}
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FiShield size={20} /> Integration Status
        </h2>
        <div className="space-y-3">
          {[
            { name: 'Microsoft SSO', status: 'Dev Mode', color: 'amber' },
            { name: 'AWS SES', status: 'Mock Mode', color: 'amber' },
            { name: 'OpenAI API', status: 'Mock Mode', color: 'amber' },
            { name: 'PostgreSQL', status: 'SQLite Fallback', color: 'blue' },
          ].map((item) => (
            <div key={item.name} className="flex items-center justify-between p-3 border border-gray-100 rounded-lg">
              <span className="text-sm font-medium text-gray-700">{item.name}</span>
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                item.color === 'amber' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'
              }`}>
                {item.status}
              </span>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-4">
          Configure credentials in backend .env to enable live integrations.
        </p>
      </div>
    </div>
  );
}
