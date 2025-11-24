import './globals.css'
import { Inter } from 'next/font/google'
import PersistentBanner from '@/components/PersistentBanner'
import { ConfigProvider } from '@/contexts/ConfigContext'
import { GlobalTTSProvider } from '@/contexts/GlobalTTSContext'
import { StoryProvider } from '@/contexts/StoryContext'
import { ServiceWorkerRegistration } from '@/components/ServiceWorkerRegistration'
import BrowserExtensionFix from '@/components/BrowserExtensionFix'

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

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // NEXT_PUBLIC_API_URL must be set via environment variable for SSR
  // No hardcoded default - must be configured
  // GlobalTTSProvider will handle client-side URL detection to prevent hydration mismatches
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || '';
  if (!process.env.NEXT_PUBLIC_API_URL) {
    // For SSR, we need an API URL. Client-side will load from config API.
    // Use empty string - ClientGlobalTTSProvider will load from config API
    console.warn('NEXT_PUBLIC_API_URL not set. Client-side will load from config API.');
  }
  
  return (
    <html lang="en">
      <body className={inter.className}>
        <BrowserExtensionFix />
        <ServiceWorkerRegistration />
        <ConfigProvider>
          <GlobalTTSProvider apiBaseUrl={apiBaseUrl}>
            <StoryProvider>
              <PersistentBanner />
              {children}
            </StoryProvider>
          </GlobalTTSProvider>
        </ConfigProvider>
      </body>
    </html>
  )
}