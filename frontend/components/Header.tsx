'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { signOut } from 'next-auth/react';

export function Header() {
  const pathname = usePathname();
  const links = [
    { href: '/', label: 'Overview' },
    { href: '/cluster/CL1', label: 'Fit' },
  ];

  const logout = async () => {
    await signOut({ redirect: false });
    window.location.reload();
  };

  return (
    <>
      <div className="apple-info-strip">Horizon Radar Workspace</div>
      <header className="apple-shell-header">
        <nav className="apple-shell-nav" aria-label="Main navigation">
          <Link className="apple-shell-brand" href="/" aria-label="Horizon Radar Home">
            <Image src="/images/logo.png" alt="Horizon Radar Logo" width={28} height={28} />
          </Link>
          <div className="apple-shell-links">
            {links.map((link) => {
              const isHome = link.href === '/';
              const isActive = isHome ? pathname === '/' : pathname === link.href || pathname.startsWith(`${link.href}/`);
              const activeClass = isActive ? 'apple-shell-link active' : 'apple-shell-link';
              return (
                <Link key={link.href} className={activeClass} href={link.href}>
                  {link.label}
                </Link>
              );
            })}
          </div>
          <button className="apple-shell-link apple-shell-logout" type="button" onClick={logout} aria-label="Logout">
            Logout
          </button>
        </nav>
      </header>
    </>
  );
}
