import Link from 'next/link';

const footerColumns = [
  {
    title: 'Workspace',
    links: [
      { label: 'Overview', href: '/' },
      { label: 'Fit CL1', href: '/cluster/CL1' },
      { label: 'Fit CL2', href: '/cluster/CL2' },
      { label: 'Fit CL3', href: '/cluster/CL3' },
    ],
  },
  {
    title: 'Flusso',
    links: [
      { label: '1. Upload PDF', href: '/cluster/CL1' },
      { label: '2. Profilo Azienda', href: '/cluster/CL1#fit-workbench' },
      { label: '3. Avvia Fit', href: '/cluster/CL1#fit-workbench' },
      { label: '4. Ranking Call', href: '/cluster/CL1' },
    ],
  },
  {
    title: 'Supporto',
    links: [
      { label: 'Centro assistenza', href: '/' },
      { label: 'Documentazione', href: '/' },
      { label: 'Contatti team', href: '/' },
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
          Flusso consigliato: apri <Link href="/">Overview</Link> e poi vai direttamente a <Link href="/cluster/CL1">Fit</Link>.
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
