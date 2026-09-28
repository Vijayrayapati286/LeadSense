import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { hasPermission } from '../utils/permissions';
import LoadingSpinner from './ui/LoadingSpinner';

export default function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

export function RequirePermission({ permission }) {
  const { user } = useAuth();
  if (!hasPermission(user, permission)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}
