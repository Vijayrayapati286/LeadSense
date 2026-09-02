import { useEffect, useState } from 'react';
import { FiUser, FiMail, FiBriefcase, FiShield, FiSliders, FiSave } from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { appSettingsService, authService } from '../services/services';
import { RESPONSE_TAGS } from '../components/FilterBuilder';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';

export default function SettingsPage() {
  const { user, loadUser } = useAuth();
  const toast = useToast();
  const [profile, setProfile] = useState({ name: '', email: '', department: '' });
  const [savingProfile, setSavingProfile] = useState(false);
  const [appSettings, setAppSettings] = useState(null);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  useEffect(() => {
    if (user) {
      setProfile({
        name: user.name || '',
        email: user.email || '',
        department: user.department || 'Sales',
      });
    }
  }, [user]);

  useEffect(() => {
    appSettingsService.get()
      .then(({ data }) => setAppSettings(data))
      .catch(() => toast.error('Failed to load application settings'))
      .finally(() => setLoadingSettings(false));
  }, [toast]);

  const handleSaveProfile = async () => {
    const name = profile.name.trim();
    const email = profile.email.trim();
    const department = profile.department.trim();

    if (!name || !email || !department) {
      toast.error('Name, email, and department are required');
      return;
    }

    setSavingProfile(true);
    try {
      await authService.updateMe({ name, email, department });
      await loadUser();
      toast.success('Profile updated');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update profile');
    } finally {
      setSavingProfile(false);
    }
  };

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
    <PageShell maxWidth="max-w-[1100px]">
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        subtitle="Manage your account and application preferences."
      />

      <div className="card">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Profile Information</h2>
            <p className="text-sm text-gray-500 mt-0.5">Click any field below to update your details.</p>
          </div>
          <button
            type="button"
            onClick={handleSaveProfile}
            disabled={savingProfile}
            className="btn-primary flex items-center gap-2"
          >
            {savingProfile ? <LoadingSpinner size="sm" /> : <><FiSave size={16} /> Save Profile</>}
          </button>
        </div>

        <div className="space-y-4">
          <label className="flex items-start gap-4 p-4 bg-gray-50 rounded-lg cursor-text">
            <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center shrink-0">
              <FiUser className="text-primary-600" size={24} />
            </div>
            <div className="min-w-0 flex-1">
              <span className="text-xs text-gray-500">Display name</span>
              <input
                type="text"
                className="input-field mt-1 bg-white"
                value={profile.name}
                onChange={(e) => setProfile((p) => ({ ...p, name: e.target.value }))}
                placeholder="Your name"
              />
            </div>
          </label>

          <label className="flex items-start gap-3 p-3 border border-gray-100 rounded-lg cursor-text">
            <FiMail className="text-gray-400 mt-2 shrink-0" size={18} />
            <div className="min-w-0 flex-1">
              <span className="text-xs text-gray-500">Email</span>
              <input
                type="email"
                className="input-field mt-1"
                value={profile.email}
                onChange={(e) => setProfile((p) => ({ ...p, email: e.target.value }))}
                placeholder="you@company.com"
              />
            </div>
          </label>

          <label className="flex items-start gap-3 p-3 border border-gray-100 rounded-lg cursor-text">
            <FiBriefcase className="text-gray-400 mt-2 shrink-0" size={18} />
            <div className="min-w-0 flex-1">
              <span className="text-xs text-gray-500">Department</span>
              <input
                type="text"
                className="input-field mt-1"
                value={profile.department}
                onChange={(e) => setProfile((p) => ({ ...p, department: e.target.value }))}
                placeholder="Sales"
              />
            </div>
          </label>
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
    </PageShell>
  );
}
