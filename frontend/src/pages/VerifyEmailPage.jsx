import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FiLock, FiMail } from 'react-icons/fi';
import { onboardService } from '../services/services';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function VerifyEmailPage({ kind = 'owner' }) {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const toast = useToast();
  const isInvite = kind === 'invite';

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!token) {
        setError('This link is missing a verification token.');
        setLoading(false);
        return;
      }
      try {
        const { data } = isInvite
          ? await onboardService.previewInvite(token)
          : await onboardService.previewVerify(token);
        if (cancelled) return;
        setPreview(data);
        setName(data?.name || '');
      } catch (err) {
        if (cancelled) return;
        setError(err?.response?.data?.detail || 'This link is invalid or expired.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [token, isInvite]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (password !== confirm) {
      toast.error('Passwords do not match');
      return;
    }
    setSaving(true);
    try {
      const payload = { password, name: name.trim() || undefined };
      if (isInvite) {
        await onboardService.completeInvite(token, payload);
      } else {
        await onboardService.completeVerify(token, payload);
      }
      setDone(true);
      toast.success('Email verified. Sign in with your new password.');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not set password');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-100 text-primary-700">
            <FiMail size={20} />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              {isInvite ? 'Accept invite' : 'Verify email'}
            </h1>
            <p className="text-sm text-slate-500">Set a password to finish setup</p>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-10">
            <LoadingSpinner size="lg" />
          </div>
        ) : error ? (
          <div className="space-y-4">
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</p>
            <Link to="/login" className="text-sm font-medium text-primary-700 hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : done ? (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              {preview?.email} is verified. Sign in with the password you just set.
            </p>
            <Link
              to="/login"
              className="inline-flex rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Go to sign in
            </Link>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={handleSubmit}>
            <p className="text-sm text-slate-600">
              {preview?.org_name ? (
                <>
                  Organization <span className="font-medium text-slate-900">{preview.org_name}</span>
                  {kind === 'owner' ? ' — you are the admin for this tenant only.' : null}
                </>
              ) : (
                'Confirm your email and choose a password.'
              )}
            </p>
            <div>
              <label className="label">Email</label>
              <input className="input-field" value={preview?.email || ''} readOnly />
            </div>
            <div>
              <label className="label">Name</label>
              <input
                className="input-field"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label className="label">New password</label>
              <div className="relative">
                <FiLock className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input
                  type="password"
                  required
                  minLength={8}
                  className="input-field pl-10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="label">Confirm password</label>
              <input
                type="password"
                required
                minLength={8}
                className="input-field"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={saving}
              className="w-full rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {saving ? 'Saving…' : 'Verify and set password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
