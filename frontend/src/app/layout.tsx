import './globals.css'
import { Inter } from 'next/font/google'
import PersistentBanner from '@/components/PersistentBanner'
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext'

const inter = Inter({ subsets: ['latin'] })

export const metadata = {
  title: 'Kahani - Interactive Storytelling',
  description: 'Create and explore AI-powered interactive stories',
}

import { getApiBaseUrl } from '@/lib/apiUrl';

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