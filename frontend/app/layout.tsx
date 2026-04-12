import type { Metadata } from 'next';
import './globals.css';
import { Header } from '@/components/Header';
import { FloatingAssistant } from '@/components/FloatingAssistant';
import { BackgroundVideoLoop } from '@/components/BackgroundVideoLoop';
import { LoginGate } from '@/components/LoginGate';

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
          <BackgroundVideoLoop />
          <div className="app-shell">
            <Header />
            <main className="container">{children}</main>
            <footer className="site-footer">
              <div className="container footer-grid">
                <section className="footer-col">
                  <h4>Workspace</h4>
                  <a href="/">Dashboard</a>
                  <a href="/profiles">Profiles</a>
                  <a href="/assistant">Assistant</a>
                </section>
                <section className="footer-col">
                  <h4>Cluster</h4>
                  <a href="/cluster/CL1">CL1</a>
                  <a href="/cluster/CL2">CL2</a>
                  <a href="/cluster/CL3">CL3</a>
                </section>
                <section className="footer-col">
                  <h4>Reports</h4>
                  <a href="/reports">Overview</a>
                  <a href="/reports/calls">Calls</a>
                  <a href="/reports/drafts">Drafts</a>
                </section>
                <section className="footer-col">
                  <h4>Support</h4>
                  <a href="/call-viewer">Call Viewer</a>
                  <a href="/topics/1">Topic Detail</a>
                  <a href="/profiles">CRM</a>
                </section>
              </div>
              <div className="container footer-bottom">© 2026 Horizon Radar. All rights reserved.</div>
            </footer>
          </div>
          <FloatingAssistant />
        </LoginGate>
      </body>
    </html>
  );
}
