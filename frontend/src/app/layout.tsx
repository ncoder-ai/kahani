import './globals.css'
import { Inter } from 'next/font/google'
import PersistentBanner from '@/components/PersistentBanner'
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext'

const inter = Inter({ subsets: ['latin'] })

export const metadata = {
  title: 'Kahani - Interactive Storytelling',
  description: 'Create and explore AI-powered interactive stories',
}

// For TTS: use the same dynamic API URL logic as the main API client
const getApiBaseUrl = () => {
  // Server-side: use environment variable or container name
  if (typeof window === 'undefined') {
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9876';
  }

  // Client-side: use window.location to build API URL
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;
  const port = window.location.port;

  // Check if we're using a reverse proxy (no port in URL or standard ports)
  // If accessing via domain without explicit port, assume reverse proxy handles backend routing
  const isReverseProxy = !port || port === '80' || port === '443';

  if (isReverseProxy) {
    // For reverse proxy: use /api on the same domain
    // Your nginx/reverse proxy should route /api/* to backend:9876
    return `${protocol}//${hostname}`;
  }

  // For direct access: use explicit backend port
  return `${protocol}//${hostname}:9876`;
};

const API_BASE_URL = getApiBaseUrl();

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <GlobalTTSProvider apiBaseUrl={API_BASE_URL}>
          <PersistentBanner />
          {children}
        </GlobalTTSProvider>
      </body>
    </html>
  )
}