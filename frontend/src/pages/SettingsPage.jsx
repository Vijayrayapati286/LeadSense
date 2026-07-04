import { FiUser, FiMail, FiBriefcase, FiShield } from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';

export default function SettingsPage() {
  const { user } = useAuth();

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
