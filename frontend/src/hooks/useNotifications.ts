import { useState, useEffect } from 'react';

interface ToastNotification {
  id: string;
  message: string;
  type: 'success' | 'info' | 'warning' | 'error';
  duration?: number;
}

export type { ToastNotification };

export const useNotifications = () => {
  const [notifications, setNotifications] = useState<ToastNotification[]>([]);
  const [showNotifications, setShowNotifications] = useState(true);

  useEffect(() => {
    // Check if notifications should be shown
    const checkSettings = () => {
      setShowNotifications(window.kahaniUISettings?.notifications !== false);
    };

    checkSettings();

    // Listen for settings changes
    const handleSettingsChange = () => {
      checkSettings();
    };

    window.addEventListener('kahaniUISettingsChanged', handleSettingsChange);
    return () => window.removeEventListener('kahaniUISettingsChanged', handleSettingsChange);
  }, []);

  const addNotification = (message: string, type: ToastNotification['type'] = 'info', duration = 3000) => {
    if (!showNotifications) return;

    const id = Math.random().toString(36).substr(2, 9);
    const newNotification: ToastNotification = { id, message, type, duration };
    
    setNotifications(prev => [...prev, newNotification]);

    if (duration > 0) {
      setTimeout(() => {
        removeNotification(id);
      }, duration);
    }
  };

  const removeNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  return { notifications, addNotification, removeNotification };
};