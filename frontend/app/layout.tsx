import type { Metadata } from 'next';
import './globals.css';
import { Header } from '@/components/Header';
import { LoginGate } from '@/components/LoginGate';
import { GlobalFooter } from '@/components/GlobalFooter';

export const metadata: Metadata = {
  title: 'Horizon Radar',
  description: 'SaaS radar for Horizon Europe calls and draft work programmes',
  manifest: '/site.webmanifest',
  icons: {
    icon: [
      { url: '/favicon.ico', type: 'image/x-icon' },
      { url: '/favicon-16x16.png', sizes: '16x16', type: 'image/png' },
      { url: '/favicon-32x32.png', sizes: '32x32', type: 'image/png' },
    ],
    apple: [{ url: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
    shortcut: ['/favicon.ico'],
  },
  themeColor: '#000000',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LoginGate>
          <div className="app-shell">
            <Header />
            <main className="apple-page-main">
              <div className="container apple-page-container">{children}</div>
            </main>
            <GlobalFooter />
          </div>
        </LoginGate>
      </body>
    </html>
  );
}
