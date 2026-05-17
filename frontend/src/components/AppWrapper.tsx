'use client';

import { useNotifications, type ToastNotification } from '@/hooks/useNotifications';

interface NotificationContainerProps {
  notifications: ToastNotification[];
  removeNotification: (id: string) => void;
}

const NotificationContainer: React.FC<NotificationContainerProps> = ({ 
  notifications, 
  removeNotification 
}) => {
  if (notifications.length === 0) return null;

  const getTypeStyles = (type: ToastNotification['type']) => {
    switch (type) {
      case 'success':
        return 'bg-green-600 border-green-500';
      case 'warning':
        return 'bg-yellow-600 border-yellow-500';
      case 'error':
        return 'bg-red-600 border-red-500';
      default:
        return 'bg-blue-600 border-blue-500';
    }
  };

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={`${getTypeStyles(notification.type)} border rounded-lg shadow-lg p-4 max-w-sm animate-in slide-in-from-right`}
        >
          <div className="flex items-center justify-between">
            <p className="text-white text-sm">{notification.message}</p>
            <button
              onClick={() => removeNotification(notification.id)}
              className="text-white/80 hover:text-white ml-2 text-lg leading-none"
            >
              ×
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default function AppWrapper({ children }: { children: React.ReactNode }) {
  const { notifications, removeNotification } = useNotifications();

  return (
    <>
      {children}
      <NotificationContainer 
        notifications={notifications} 
        removeNotification={removeNotification} 
      />
    </>
  );
}