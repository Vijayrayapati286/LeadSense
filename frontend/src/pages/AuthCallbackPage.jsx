import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';

export default function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const { login } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    const token = searchParams.get('token');
    const error = searchParams.get('error');

    if (error) {
      toast.error('Authentication failed');
      navigate('/login');
      return;
    }

    if (token) {
      login(token).then(() => {
        toast.success('Logged in successfully');
        navigate('/dashboard');
      });
    } else {
      navigate('/login');
    }
  }, [searchParams, login, navigate, toast]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <LoadingSpinner size="lg" />
        <p className="mt-4 text-gray-500">Completing authentication...</p>
      </div>
    </div>
  );
}
