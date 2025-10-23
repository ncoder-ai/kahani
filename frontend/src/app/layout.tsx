import './globals.css'
import { Inter } from 'next/font/google'
import PersistentBanner from '@/components/PersistentBanner'
import ClientGlobalTTSProvider from '@/components/ClientGlobalTTSProvider'

const inter = Inter({ subsets: ['latin'] })

export const metadata = {
  title: 'Kahani - Interactive Storytelling',
  description: 'Create and explore AI-powered interactive stories',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ClientGlobalTTSProvider>
          <PersistentBanner />
          {children}
        </ClientGlobalTTSProvider>
      </body>
    </html>
  )
}