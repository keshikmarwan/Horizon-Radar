'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { signOut } from 'next-auth/react';
import { useEffect, useState } from 'react';

export function Header() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const links = [
    { href: '/', label: 'Overview' },
    { href: '/fit/CL1', label: 'Fit' },
  ];

  const logout = async () => {
    await signOut({ redirect: false });
    window.location.reload();
  };

  return (
    <>
      <header className={`apple-shell-header${scrolled ? ' is-scrolled' : ''}`}>
        <nav className="apple-shell-nav" aria-label="Main navigation">
          <Link className="apple-shell-brand" href="/" aria-label="Horizon Radar Home">
            <Image src="/images/logo.png" alt="Horizon Radar Logo" width={28} height={28} />
          </Link>
          <div className="apple-shell-links">
            {links.map((link) => {
              const isHome = link.href === '/';
              const isActive = isHome ? pathname === '/' : pathname === link.href || pathname.startsWith(`${link.href}/`);
              return (
                <Link key={link.href} className={isActive ? 'apple-shell-link active' : 'apple-shell-link'} href={link.href}>
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
