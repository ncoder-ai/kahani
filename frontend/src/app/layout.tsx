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
  title: 'Make My Saga - Interactive Storytelling',
  description: 'Create and explore AI-powered interactive stories',
  icons: {
    icon: '/kahani-logo.jpg',
    apple: '/kahani-logo.jpg',
  },
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
  return (
    <html lang="en">
      <body className={inter.className}>
        <BrowserExtensionFix />
        <ServiceWorkerRegistration />
        <ConfigProvider>
          <GlobalTTSProvider>
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