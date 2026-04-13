'use client';

import Link from 'next/link';
import { CSSProperties, useEffect } from 'react';

type PromoSection = {
  eyebrow: string;
  title: string;
  subtitle: string;
  tone: 'dark' | 'light';
  backgroundImage?: string;
  backgroundPosition?: string;
  backgroundSize?: string;
  primary: { label: string; href: string };
  secondary: { label: string; href: string };
};

const sections: PromoSection[] = [
  {
    eyebrow: 'Horizon Radar',
    title: 'Intelligence platform.',
    subtitle: 'Scouting, valutazione e pipeline operativa per bandi Horizon Europe, in un unico workspace.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_008_BtCLqTNyl7f5ludR7pe3t.jpg',
    backgroundPosition: 'center 10%',
    backgroundSize: '92% auto',
    primary: { label: 'Apri Overview', href: '/' },
    secondary: { label: 'Vai ai Cluster', href: '/cluster/CL1' },
  },
  {
    eyebrow: 'Pipeline',
    title: 'Opportunità in movimento.',
    subtitle: 'Segui ogni topic dalla discovery al draft, con priorità, owner e next action sempre visibili.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_011_k5pzoP5SGaN9MWA0ZHZVD.jpg',
    backgroundPosition: 'center 12%',
    backgroundSize: '92% auto',
    primary: { label: 'Apri Pipeline', href: '/cluster/CL1' },
    secondary: { label: 'Vedi CL2', href: '/cluster/CL2' },
  },
  {
    eyebrow: 'Profiles',
    title: 'Profili aziendali più utili.',
    subtitle: 'Capacità, evidenze e storico in una vista unica per decidere rapidamente il fit sui bandi.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_007_small_m6bTwZYsSE-dbxorMYt3U.jpg',
    backgroundPosition: 'center 14%',
    backgroundSize: '92% auto',
    primary: { label: 'Apri Profiles', href: '/profiles' },
    secondary: { label: 'Vai a CRM', href: '/profiles/company/gbionics' },
  },
  {
    eyebrow: 'Call Viewer',
    title: 'Call intelligence immediata.',
    subtitle: 'Naviga i dettagli di call e topic con una lettura guidata orientata alle decisioni operative.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_001_fpOwfzELkQljrc5M8ALeP.jpg',
    backgroundPosition: 'center 14%',
    backgroundSize: '92% auto',
    primary: { label: 'Apri Call Viewer', href: '/call-viewer' },
    secondary: { label: 'Apri Topic', href: '/topics/1' },
  },
  {
    eyebrow: 'Workspace',
    title: 'Dal segnale all’azione.',
    subtitle: 'Una base coerente per team, cluster e workflow: meno attrito, più execution.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_010_RQOqoU9Qnpo8UG3RSUBAa.jpg',
    backgroundPosition: 'center 14%',
    backgroundSize: '92% auto',
    primary: { label: 'Vai al Cluster', href: '/cluster/CL3' },
    secondary: { label: 'Apri Overview', href: '/' },
  },
];

export default function DashboardPage() {
  useEffect(() => {
    const panels = Array.from(document.querySelectorAll<HTMLElement>('.apple-home-panel'));
    if (!panels.length) return;
    const engageTimers = new Map<HTMLElement, number>();
    const engaged = new WeakSet<HTMLElement>();
    const IN_VIEW_THRESHOLD = 0.68;
    const TIME_TO_ENGAGE_MS = 260;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const panel = entry.target as HTMLElement;
          if (engaged.has(panel)) continue;

          if (entry.intersectionRatio >= IN_VIEW_THRESHOLD) {
            if (!engageTimers.has(panel)) {
              const timer = window.setTimeout(() => {
                panel.classList.add('is-visible');
                engaged.add(panel);
                engageTimers.delete(panel);
              }, TIME_TO_ENGAGE_MS);
              engageTimers.set(panel, timer);
            }
          } else if (engageTimers.has(panel)) {
            window.clearTimeout(engageTimers.get(panel));
            engageTimers.delete(panel);
          }
        }
      },
      {
        threshold: [0, IN_VIEW_THRESHOLD, 1],
        rootMargin: '0px 0px -2% 0px',
      },
    );

    for (const panel of panels) {
      observer.observe(panel);
    }

    return () => {
      observer.disconnect();
      for (const timer of engageTimers.values()) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  return (
    <div className="apple-homepage" aria-label="Horizon Radar home">
      {sections.map((section, idx) => (
        <section
          key={section.title}
          className={`apple-home-panel ${section.tone === 'dark' ? 'tone-dark' : 'tone-light'} ${section.backgroundImage ? 'has-bg-image' : ''}`}
          style={{
            ...(section.backgroundImage
              ? {
                  backgroundImage: `linear-gradient(180deg, rgba(0, 0, 0, 0.18) 0%, rgba(0, 0, 0, 0.38) 100%), url(${section.backgroundImage})`,
                  backgroundPosition: section.backgroundPosition || 'center 14%',
                  backgroundSize: section.backgroundSize || '92% auto',
                }
              : {}),
            '--section-index': idx,
          } as CSSProperties}
        >
          <div className="apple-home-panel-inner">
            <p className="apple-home-eyebrow">{section.eyebrow}</p>
            <h2>{section.title}</h2>
            <p className="apple-home-subtitle">{section.subtitle}</p>
            <div className="apple-home-actions">
              <Link href={section.primary.href} className="apple-home-link primary">
                {section.primary.label}
              </Link>
              <Link href={section.secondary.href} className="apple-home-link">
                {section.secondary.label}
              </Link>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
