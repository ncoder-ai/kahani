import './globals.css'
import { Inter } from 'next/font/google'
import PersistentBanner from '@/components/PersistentBanner'
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext'
import { StoryProvider } from '@/contexts/StoryContext'

// Optimized font loading with display swap for better performance
const inter = Inter({ 
  subsets: ['latin'],
  display: 'swap',
  preload: true,
  variable: '--font-inter'
})

export const metadata = {
  title: 'Kahani - Interactive Storytelling',
  description: 'Create and explore AI-powered interactive stories',
}

import { getApiBaseUrl } from '@/lib/api';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <GlobalTTSProvider apiBaseUrl={getApiBaseUrl()}>
          <StoryProvider>
            <PersistentBanner />
            {children}
          </StoryProvider>
        </GlobalTTSProvider>
      </body>
    </html>
  )
}