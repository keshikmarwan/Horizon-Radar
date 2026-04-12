'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';

export function Header() {
  const pathname = usePathname();
  const links = [
    { href: '/', label: 'Overview' },
    { href: '/cluster/CL1', label: 'Pipeline' },
    { href: '/profiles', label: 'Profiles' },
    { href: '/reports', label: 'Reports' },
    { href: '/call-viewer', label: 'Call Viewer' },
  ];

  const logout = () => {
    if (typeof window === 'undefined') return;
    window.localStorage.removeItem('horizon-radar-auth-v1');
    window.location.reload();
  };

  return (
    <header className="header">
      <Link className="brand" href="/">
        <Image src="/images/logo.png" alt="Horizon Radar Logo" width={42} height={42} />
      </Link>
      <nav aria-label="Main navigation">
        {links.map((link) => {
          const isHome = link.href === '/';
          const isActive = isHome ? pathname === '/' : pathname === link.href || pathname.startsWith(`${link.href}/`);
          const activeClass = isActive ? 'header-link active' : 'header-link';
          return (
            <Link key={link.href} className={activeClass} href={link.href}>
              {link.label}
            </Link>
          );
        })}
        <button className="header-link" type="button" onClick={logout} aria-label="Logout">
          Logout
        </button>
      </nav>
    </header>
  );
}
