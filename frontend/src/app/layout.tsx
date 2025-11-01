import './globals.css'
import { Inter } from 'next/font/google'
import PersistentBanner from '@/components/PersistentBanner'
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext'
import { StoryProvider } from '@/contexts/StoryContext'
import { ServiceWorkerRegistration } from '@/components/ServiceWorkerRegistration'

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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Use environment variable or safe default for SSR
  // GlobalTTSProvider will handle client-side URL detection to prevent hydration mismatches
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9876';
  
  return (
    <html lang="en">
      <body className={inter.className}>
        <ServiceWorkerRegistration />
        <GlobalTTSProvider apiBaseUrl={apiBaseUrl}>
          <StoryProvider>
            <PersistentBanner />
            {children}
          </StoryProvider>
        </GlobalTTSProvider>
      </body>
    </html>
  )
}