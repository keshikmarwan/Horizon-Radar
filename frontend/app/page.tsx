'use client';

import Link from 'next/link';
import { CSSProperties, useEffect, useMemo, useState } from 'react';
import { ExportPDFButton } from '@/components/ExportPDFButton';
import { FitConstellationLoader } from '@/components/FitConstellationLoader';
import { CLUSTERS, readClusterStore } from '@/lib/cluster-store';
import type { HorizonMatcherProfilePayload } from '@/lib/types';

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
    eyebrow: 'Overview',
    title: 'Intelligence platform.',
    subtitle: 'Un punto di ingresso unico: visione strategica e accesso diretto al motore di fit.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_008_BtCLqTNyl7f5ludR7pe3t.jpg',
    backgroundPosition: 'center 18%',
    backgroundSize: 'cover',
    primary: { label: 'Apri Overview', href: '/' },
    secondary: { label: 'Vai al Fit', href: '/fit/CL1' },
  },
  {
    eyebrow: 'Fit',
    title: 'Reliability score integrato.',
    subtitle: 'Upload del Work Programme, profiling azienda e ranking call nello stesso workspace operativo.',
    tone: 'dark',
    backgroundImage: '/images/IDG_GBionics_render_021_rK-sZdFO9s-rgTKZOlOl6.jpg',
    backgroundPosition: 'center 22%',
    backgroundSize: 'cover',
    primary: { label: 'Apri Fit', href: '/fit/CL1' },
    secondary: { label: 'Esplora CL2', href: '/fit/CL2' },
  },
];

export default function DashboardPage() {
  const [exportLoading, setExportLoading] = useState(false);
  const [exportMessage, setExportMessage] = useState('');

  const portfolioProfile = useMemo<HorizonMatcherProfilePayload>(() => {
    const store = readClusterStore();
    const entries = CLUSTERS
      .map((id) => store.clusterData[id])
      .filter(Boolean);

    const descriptions = entries
      .map((item) => item?.companyDescription?.trim() || '')
      .filter((txt) => txt.length > 0);
    const interests = entries
      .map((item) => item?.clusterInterests?.trim() || '')
      .filter((txt) => txt.length > 0);
    const tags = Array.from(
      new Set(
        interests
          .join('\n')
          .toLowerCase()
          .split(/[\n,;|]+/)
          .map((s) => s.trim())
          .filter((s) => s.length >= 3),
      ),
    ).slice(0, 30);

    const latest = entries[0];
    return {
      description: descriptions.join('\n\n').slice(0, 8000) || 'Profilo portfolio Generative Bionics',
      mission: descriptions.join('\n\n').slice(0, 6000) || 'Profilo portfolio Generative Bionics',
      technical_knowhow: interests.join('\n').slice(0, 8000) || 'Physical AI, embodied AI, robotics',
      keywords: tags,
      trl_current: latest?.trlCurrent ?? 5,
      budget_company_available: latest?.budgetCompanyAvailable ?? 0,
      budget_max: latest?.budgetMax ?? null,
      is_sme: latest?.isSme ?? false,
      ssh_capacity: latest?.sshCapacity ?? false,
      fair_compliant: latest?.fairCompliant ?? false,
      gender_dimension_active: latest?.genderDimensionActive ?? false,
      gender_balance_required: latest?.genderBalanceRequired ?? false,
      clusters_interest: ['Health', 'Digital', 'Security', 'Manufacturing', 'Climate', 'Food'],
    };
  }, []);

  useEffect(() => {
    const panels = Array.from(document.querySelectorAll<HTMLElement>('.apple-home-panel'));
    if (!panels.length) return;
    const engageTimers = new Map<HTMLElement, number>();
    const engaged = new WeakSet<HTMLElement>();
    const IN_VIEW_THRESHOLD = 0.42;
    const TIME_TO_ENGAGE_MS = 120;
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
      <section className="apple-home-panel tone-dark" style={{ minHeight: '34vh' }}>
        <div className="apple-home-panel-inner">
          <p className="apple-home-eyebrow">Portfolio Export</p>
          <h2>Genera Report Completo Portfolio Horizon</h2>
          <p className="apple-home-subtitle">PDF professionale pronto per invio email ai founder (Executive + dettaglio call).</p>
          <div className="apple-home-actions">
            <ExportPDFButton
              clusterId="PORTFOLIO"
              profile={portfolioProfile}
              includeAllCallsDefault={true}
              topNDefault={15}
              onLoadingChange={setExportLoading}
              onMessage={(msg) => setExportMessage(msg)}
              className="apple-home-link primary"
              label="Esporta Report PDF"
            />
          </div>
          {exportMessage && <p className="apple-home-subtitle" style={{ marginTop: '0.7rem' }}>{exportMessage}</p>}
        </div>
      </section>
      {sections.map((section, idx) => (
        <section
          key={section.title}
          className={`apple-home-panel ${section.tone === 'dark' ? 'tone-dark' : 'tone-light'} ${section.backgroundImage ? 'has-bg-image' : ''}`}
          style={{
            ...(section.backgroundImage
              ? {
                  backgroundImage: [
                    'linear-gradient(160deg, rgba(0,0,0,0.62) 0%, rgba(0,0,0,0.24) 42%, rgba(0,0,0,0.72) 100%)',
                    `url(${section.backgroundImage})`,
                  ].join(', '),
                  backgroundPosition: section.backgroundPosition || 'center 18%',
                  backgroundSize: section.backgroundSize || 'cover',
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
      {exportLoading && (
        <div className="fit-loading-overlay" aria-live="polite">
          <FitConstellationLoader phase="running" />
          <div className="fit-loading-label">Generazione report portfolio in corso…</div>
        </div>
      )}
    </div>
  );
}
