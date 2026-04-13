import Link from 'next/link';

const footerColumns = [
  {
    title: 'Piattaforma',
    links: [
      { label: 'Overview', href: '/' },
      { label: 'Pipeline', href: '/cluster/CL1' },
      { label: 'Profiles', href: '/profiles' },
      { label: 'Call Viewer', href: '/call-viewer' },
    ],
  },
  {
    title: 'Cluster',
    links: [
      { label: 'CL1', href: '/cluster/CL1' },
      { label: 'CL2', href: '/cluster/CL2' },
      { label: 'CL3', href: '/cluster/CL3' },
      { label: 'Topic Detail', href: '/topics/1' },
    ],
  },
  {
    title: 'Workspace',
    links: [
      { label: 'Dashboard CRM', href: '/profiles' },
      { label: 'Opportunity Pipeline', href: '/cluster/CL1' },
      { label: 'Call Intelligence', href: '/call-viewer' },
      { label: 'Home', href: '/' },
    ],
  },
  {
    title: 'Supporto',
    links: [
      { label: 'Centro assistenza', href: '/call-viewer' },
      { label: 'Documentazione', href: '/profiles' },
      { label: 'Contatti team', href: '/profiles' },
      { label: 'Status workspace', href: '/' },
    ],
  },
];

const legalLinks = [
  { label: 'Privacy', href: '#' },
  { label: 'Cookie', href: '#' },
  { label: 'Condizioni d’uso', href: '#' },
  { label: 'Note legali', href: '#' },
  { label: 'Mappa del sito', href: '/' },
];

export function GlobalFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="apple-global-footer">
      <div className="apple-global-footer-inner">
        <div className="apple-global-footer-shop">
          Altri modi per esplorare Horizon Radar: entra in una vista <Link href="/">Overview</Link> o apri{' '}
          <Link href="/profiles">Profiles</Link>.
        </div>
        <nav className="apple-global-footer-directory" aria-label="Footer">
          {footerColumns.map((column) => (
            <section key={column.title} className="apple-global-footer-column">
              <h4>{column.title}</h4>
              <ul>
                {column.links.map((link) => (
                  <li key={`${column.title}-${link.label}`}>
                    <Link href={link.href}>{link.label}</Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </nav>
        <div className="apple-global-footer-legal-wrap">
          <div className="apple-global-footer-copyright">Copyright © {year} Horizon Radar. Tutti i diritti riservati.</div>
          <ul className="apple-global-footer-legal-links" role="list">
            {legalLinks.map((link) => (
              <li key={link.label}>
                <Link href={link.href}>{link.label}</Link>
              </li>
            ))}
          </ul>
          <div className="apple-global-footer-locale">Italia</div>
        </div>
      </div>
    </footer>
  );
}
