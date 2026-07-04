import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function MainLayout() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Sidebar />
      <main className="ml-64 min-h-screen transition-all duration-300 p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  );
}
