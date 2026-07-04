import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiMail, FiShield } from 'react-icons/fi';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { authService } from '../services/services';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const { devLogin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const handleMicrosoftLogin = async () => {
    setLoading(true);
    try {
      const { data } = await authService.getLoginUrl();
      if (data.dev_mode || !data.login_url) {
        await handleDevLogin();
      } else {
        window.location.href = data.login_url;
      }
    } catch {
      toast.error('Failed to initiate login. Trying dev mode...');
      await handleDevLogin();
    }
  };

  const handleDevLogin = async () => {
    setLoading(true);
    try {
      await devLogin();
      toast.success('Logged in successfully');
      navigate('/dashboard');
    } catch {
      toast.error('Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-primary-700 via-primary-800 to-primary-900 items-center justify-center p-12">
        <div className="max-w-md text-white">
          <div className="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center mb-8">
            <FiMail size={32} />
          </div>
          <h1 className="text-4xl font-bold mb-4">Bulk Email Campaign Manager</h1>
          <p className="text-primary-200 text-lg leading-relaxed">
            Streamline your sales outreach with powerful bulk email campaigns,
            AI-generated templates, and comprehensive analytics.
          </p>
          <div className="mt-8 space-y-3">
            {['Microsoft SSO Authentication', 'AI-Powered Email Generation', 'AWS SES Integration', 'Real-time Analytics'].map(
              (feature) => (
                <div key={feature} className="flex items-center gap-3 text-primary-100">
                  <div className="w-1.5 h-1.5 bg-primary-300 rounded-full" />
                  <span className="text-sm">{feature}</span>
                </div>
              )
            )}
          </div>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <div className="w-12 h-12 bg-primary-100 rounded-xl flex items-center justify-center mx-auto mb-4 lg:hidden">
              <FiMail className="text-primary-600" size={24} />
            </div>
            <h2 className="text-2xl font-bold text-gray-900">Welcome back</h2>
            <p className="text-gray-500 mt-2">Sign in to manage your email campaigns</p>
          </div>

          <div className="card">
            <button
              onClick={handleMicrosoftLogin}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 bg-[#2F2F2F] text-white px-4 py-3 rounded-lg font-medium hover:bg-[#1F1F1F] transition-colors disabled:opacity-50"
            >
              {loading ? (
                <LoadingSpinner size="sm" />
              ) : (
                <>
                  <svg width="20" height="20" viewBox="0 0 21 21" fill="none">
                    <rect x="1" y="1" width="9" height="9" fill="#F25022" />
                    <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
                    <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
                    <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
                  </svg>
                  Sign in with Microsoft
                </>
              )}
            </button>

            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-3 bg-white text-gray-500">or</span>
              </div>
            </div>

            <button
              onClick={handleDevLogin}
              disabled={loading}
              className="w-full btn-secondary flex items-center justify-center gap-2"
            >
              <FiShield size={18} />
              Dev Login (Demo)
            </button>

            <p className="text-xs text-gray-400 text-center mt-4">
              Dev login uses mock authentication when Azure AD is not configured.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
