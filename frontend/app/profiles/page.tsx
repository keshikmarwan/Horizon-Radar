'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { companyKey, CrmContact, CrmStore, CrmTag, makeId, readCrmStore, writeCrmStore } from '@/lib/crm-store';
import { apiPost } from '@/lib/api';
import type { ReportAssistantResponse } from '@/lib/types';

type ContactForm = {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  role: string;
  notes: string;
  company: string;
  companyTagIds: string[];
  personalSubTagIds: string[];
};

const defaultContactForm: ContactForm = {
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  role: '',
  notes: '',
  company: '',
  companyTagIds: [],
  personalSubTagIds: [],
};

const TAG_COLORS = [
  '#2a2a2a',
  '#3a3a3a',
  '#4a4a4a',
  '#5a5a5a',
  '#6a6a6a',
  '#7a7a7a',
  '#8a8a8a',
  '#1f3a8a',
  '#1d4ed8',
  '#0f766e',
  '#0e7490',
  '#166534',
  '#3f6212',
  '#92400e',
  '#b45309',
  '#9f1239',
  '#be123c',
  '#6d28d9',
  '#7c3aed',
  '#334155',
  '#155e75',
  '#065f46',
  '#7f1d1d',
  '#854d0e',
];

type CompanyCard = {
  key: string;
  name: string;
  contacts: CrmContact[];
  tags: CrmTag[];
  scores: {
    technicalFit: number;
    consortiumValue: number;
    readiness: number;
    geoRelevance: number;
    overall: number;
  };
  readinessBand: 'High' | 'Medium' | 'Low';
  callsCount: number;
};

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function computeRoleStrength(contacts: CrmContact[]): number {
  const boostWords = ['head', 'director', 'manager', 'lead', 'principal', 'cto', 'ceo', 'founder', 'pi'];
  const boosted = contacts.filter((c) => {
    const role = (c.role || '').toLowerCase();
    return boostWords.some((token) => role.includes(token));
  }).length;
  const ratio = contacts.length > 0 ? boosted / contacts.length : 0;
  return clampScore(45 + ratio * 40);
}

function computeReadinessFromCalls(statuses: string[]): number {
  const weights: Record<string, number> = {
    DI_INTERESSE_CONTATTO: 38,
    NEL_CONSORZIO: 68,
    PRESENTATA: 84,
    FINANZIATA: 100,
  };
  if (statuses.length === 0) return 42;
  const avg = statuses.reduce((sum, status) => sum + (weights[status] ?? 40), 0) / statuses.length;
  return clampScore(avg);
}

function RadarMini({
  technicalFit,
  consortiumValue,
  readiness,
  geoRelevance,
}: {
  technicalFit: number;
  consortiumValue: number;
  readiness: number;
  geoRelevance: number;
}) {
  const values = [technicalFit, consortiumValue, readiness, geoRelevance].map((value) => Math.max(0, Math.min(100, value)) / 100);
  const size = 136;
  const cx = size / 2;
  const cy = size / 2;
  const r = 48;
  const angles = [-90, 0, 90, 180];

  const axisPoints = angles.map((deg) => {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + Math.cos(rad) * r, y: cy + Math.sin(rad) * r };
  });

  const polygon = values
    .map((v, i) => {
      const rad = (angles[i] * Math.PI) / 180;
      return `${cx + Math.cos(rad) * r * v},${cy + Math.sin(rad) * r * v}`;
    })
    .join(' ');

  return (
    <div className="profiles-radar-wrap" aria-hidden="true">
      <svg className="profiles-radar" viewBox={`0 0 ${size} ${size}`} role="img">
        <polygon points={`${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}`} className="profiles-radar-grid-outer" />
        <polygon points={`${cx},${cy - r * 0.66} ${cx + r * 0.66},${cy} ${cx},${cy + r * 0.66} ${cx - r * 0.66},${cy}`} className="profiles-radar-grid-mid" />
        <polygon points={`${cx},${cy - r * 0.33} ${cx + r * 0.33},${cy} ${cx},${cy + r * 0.33} ${cx - r * 0.33},${cy}`} className="profiles-radar-grid-inner" />
        {axisPoints.map((p, idx) => (
          <line key={`axis-${idx}`} x1={cx} y1={cy} x2={p.x} y2={p.y} className="profiles-radar-axis" />
        ))}
        <polygon points={polygon} className="profiles-radar-shape" />
      </svg>
      <div className="profiles-radar-legend">
        <span>T</span>
        <span>C</span>
        <span>R</span>
        <span>G</span>
      </div>
    </div>
  );
}

export default function ProfilesPage() {
  const [store, setStore] = useState<CrmStore>({ tags: [], contacts: [], companyTagIds: {}, companyCalls: {} });
  const [isHydrated, setIsHydrated] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<ContactForm>(defaultContactForm);
  const [newTagLabel, setNewTagLabel] = useState('');
  const [newTagColor, setNewTagColor] = useState(TAG_COLORS[0]);
  const [newTagScope, setNewTagScope] = useState<'company' | 'personal'>('company');
  const [companyFilter, setCompanyFilter] = useState('');
  const [tagFilterIds, setTagFilterIds] = useState<string[]>([]);
  const [roleFilter, setRoleFilter] = useState('');
  const [notesFilter, setNotesFilter] = useState('');
  const [minScoreFilter, setMinScoreFilter] = useState(0);
  const [readinessFilter, setReadinessFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all');
  const [copilotPrompt, setCopilotPrompt] = useState('');
  const [copilotAnswer, setCopilotAnswer] = useState('');
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotError, setCopilotError] = useState('');
  const companyTags = useMemo(() => store.tags.filter((t) => t.scope === 'company'), [store.tags]);
  const personalTags = useMemo(() => store.tags.filter((t) => t.scope === 'personal'), [store.tags]);

  useEffect(() => {
    setStore(readCrmStore());
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    writeCrmStore(store);
  }, [store, isHydrated]);

  const addTag = () => {
    const label = newTagLabel.trim();
    if (!label) return;
    const existing = store.tags.find((t) => t.label.toLowerCase() === label.toLowerCase() && t.scope === newTagScope);
    if (existing) { setNewTagLabel(''); return; }
    const tag: CrmTag = { id: makeId('tag'), label, color: newTagColor, scope: newTagScope };
    setStore((prev) => ({ ...prev, tags: [...prev.tags, tag] }));
    setNewTagLabel('');
  };

  const toggleCompanyFormTag = (id: string) => {
    setForm((prev) => ({
      ...prev,
      companyTagIds: prev.companyTagIds.includes(id)
        ? prev.companyTagIds.filter((x) => x !== id)
        : [...prev.companyTagIds, id],
    }));
  };

  const togglePersonalFormTag = (id: string) => {
    setForm((prev) => ({
      ...prev,
      personalSubTagIds: prev.personalSubTagIds.includes(id)
        ? prev.personalSubTagIds.filter((x) => x !== id)
        : [...prev.personalSubTagIds, id],
    }));
  };

  const toggleFilterTag = (id: string) => {
    setTagFilterIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const companyHasTag = (companyCard: CompanyCard, tagId: string): boolean =>
    (store.companyTagIds[companyCard.key] || []).includes(tagId);

  const toggleCompanyTag = (companyCard: CompanyCard, tagId: string) => {
    setStore((prev) => ({
      ...prev,
      companyTagIds: {
        ...prev.companyTagIds,
        [companyCard.key]: (prev.companyTagIds[companyCard.key] || []).includes(tagId)
          ? (prev.companyTagIds[companyCard.key] || []).filter((x) => x !== tagId)
          : [...(prev.companyTagIds[companyCard.key] || []), tagId],
      },
    }));
  };

  const saveContact = () => {
    const firstName = form.firstName.trim();
    const lastName = form.lastName.trim();
    const company = form.company.trim();
    if (!firstName || !lastName || !company) return;

    const contact: CrmContact = {
      id: makeId('person'),
      firstName,
      lastName,
      email: form.email.trim(),
      phone: form.phone.trim(),
      role: form.role.trim(),
      notes: form.notes.trim(),
      company,
      subTagIds: [...new Set(form.personalSubTagIds)],
      createdAt: new Date().toISOString(),
    };

    const key = companyKey(company);
    setStore((prev) => ({
      ...prev,
      contacts: [contact, ...prev.contacts],
      companyTagIds: {
        ...prev.companyTagIds,
        [key]: [...new Set([...(prev.companyTagIds[key] || []), ...form.companyTagIds])],
      },
    }));
    setForm(defaultContactForm);
    setShowForm(false);
  };

  const cards = useMemo<CompanyCard[]>(() => {
    const grouped = new Map<string, CompanyCard>();

    for (const c of store.contacts) {
      const key = companyKey(c.company);
      if (!key) continue;

      if (!grouped.has(key)) {
        grouped.set(key, {
          key,
          name: c.company,
          contacts: [],
          tags: [],
          scores: {
            technicalFit: 0,
            consortiumValue: 0,
            readiness: 0,
            geoRelevance: 0,
            overall: 0,
          },
          readinessBand: 'Low',
          callsCount: 0,
        });
      }
      const target = grouped.get(key)!;
      target.contacts.push(c);
    }

    for (const card of grouped.values()) {
      const ids = store.companyTagIds[card.key] || [];
      card.tags = ids.map((id) => store.tags.find((x) => x.id === id)).filter(Boolean) as CrmTag[];
      const calls = store.companyCalls[card.key] || [];
      const callStatuses = calls.map((call) => call.status);

      const technicalFit = clampScore(42 + card.tags.length * 7 + Math.min(4, card.contacts.length) * 6);
      const consortiumValue = clampScore((computeRoleStrength(card.contacts) + clampScore(40 + card.contacts.length * 8)) / 2);
      const readiness = computeReadinessFromCalls(callStatuses);
      const geoRelevance = clampScore(48 + Math.min(5, card.tags.length) * 6);
      const overall = clampScore(technicalFit * 0.33 + consortiumValue * 0.27 + readiness * 0.25 + geoRelevance * 0.15);

      card.scores = { technicalFit, consortiumValue, readiness, geoRelevance, overall };
      card.callsCount = calls.length;
      card.readinessBand = readiness >= 75 ? 'High' : readiness >= 55 ? 'Medium' : 'Low';
    }

    const companyNeedle = companyFilter.trim().toLowerCase();
    const roleNeedle = roleFilter.trim().toLowerCase();
    const notesNeedle = notesFilter.trim().toLowerCase();
    let out = [...grouped.values()];
    if (companyNeedle) {
      out = out.filter((x) => x.name.toLowerCase().includes(companyNeedle));
    }
    if (roleNeedle) {
      out = out.filter((x) => x.contacts.some((c) => (c.role || '').toLowerCase().includes(roleNeedle)));
    }
    if (notesNeedle) {
      out = out.filter((x) => x.contacts.some((c) => (c.notes || '').toLowerCase().includes(notesNeedle)));
    }
    if (tagFilterIds.length > 0) {
      out = out.filter((x) => tagFilterIds.every((id) => x.tags.some((t) => t.id === id)));
    }
    if (minScoreFilter > 0) {
      out = out.filter((x) => x.scores.overall >= minScoreFilter);
    }
    if (readinessFilter !== 'all') {
      out = out.filter((x) => x.readinessBand.toLowerCase() === readinessFilter);
    }

    return out.sort((a, b) => b.scores.overall - a.scores.overall || a.name.localeCompare(b.name));
  }, [
    store.contacts,
    store.tags,
    store.companyTagIds,
    store.companyCalls,
    companyFilter,
    roleFilter,
    notesFilter,
    tagFilterIds,
    minScoreFilter,
    readinessFilter,
  ]);

  const crmMetrics = useMemo(() => {
    const uniqueCompanies = new Set(store.contacts.map((c) => companyKey(c.company)).filter(Boolean));
    return {
      contacts: store.contacts.length,
      companies: uniqueCompanies.size,
      companyTags: companyTags.length,
      personalTags: personalTags.length,
    };
  }, [store.contacts, companyTags.length, personalTags.length]);

  const runCopilot = async () => {
    const prompt = copilotPrompt.trim();
    if (!prompt || copilotLoading) return;
    setCopilotLoading(true);
    setCopilotError('');

    const portfolioPreview = cards
      .slice(0, 8)
      .map((card) => `${card.name} | score ${card.scores.overall} | readiness ${card.readinessBand} | tags ${card.tags.map((t) => t.label).join(', ')}`)
      .join('\n');

    try {
      const result = await apiPost<ReportAssistantResponse>('/api/reports/assistant/query', {
        query: `Contesto CRM Horizon Europe:\n${portfolioPreview || 'Nessun partner nel CRM'}\n\nRichiesta: ${prompt}`,
      });
      setCopilotAnswer(result.answer || 'Nessuna risposta disponibile.');
    } catch (err) {
      setCopilotError(String(err));
      const fallback = cards.slice(0, 3).map((card) => `${card.name}: score ${card.scores.overall}, readiness ${card.readinessBand}`).join(' • ');
      setCopilotAnswer(`Copilot fallback: i partner piu pronti al momento sono ${fallback || 'non disponibili'}.`);
    } finally {
      setCopilotLoading(false);
    }
  };

  return (
    <section className="profiles-page">
      <header className="profiles-hero card">
        <p className="landing-eyebrow">Horizon Europe Partner CRM</p>
        <h1>Profiles Intelligence Workspace</h1>
        <p className="landing-subtitle">
          Mappa partner, stakeholder e capability di consorzio con una vista unica orientata a call Horizon Europe.
        </p>
      </header>

      <section className="profiles-kpi-grid">
        <article className="profiles-kpi-card">
          <p className="profiles-kpi-label">Contatti</p>
          <p className="profiles-kpi-value">{crmMetrics.contacts}</p>
        </article>
        <article className="profiles-kpi-card">
          <p className="profiles-kpi-label">Aziende</p>
          <p className="profiles-kpi-value">{crmMetrics.companies}</p>
        </article>
        <article className="profiles-kpi-card">
          <p className="profiles-kpi-label">Tag Azienda</p>
          <p className="profiles-kpi-value">{crmMetrics.companyTags}</p>
        </article>
        <article className="profiles-kpi-card">
          <p className="profiles-kpi-label">Sub-tag Persona</p>
          <p className="profiles-kpi-value">{crmMetrics.personalTags}</p>
        </article>
      </section>

      <section className="profiles-control-grid">
        <article className="card profiles-form-card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h3>Nuovo Contatto</h3>
            <button onClick={() => setShowForm((v) => !v)}>{showForm ? 'Chiudi' : 'Nuova persona'}</button>
          </div>

          {showForm ? (
            <div className="profiles-form-fields">
              <div className="profiles-input-grid">
                <input
                  placeholder="Nome"
                  value={form.firstName}
                  onChange={(e) => setForm((prev) => ({ ...prev, firstName: e.target.value }))}
                />
                <input
                  placeholder="Cognome"
                  value={form.lastName}
                  onChange={(e) => setForm((prev) => ({ ...prev, lastName: e.target.value }))}
                />
                <input
                  placeholder="Telefono"
                  value={form.phone}
                  onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
                />
                <input
                  placeholder="Email"
                  value={form.email}
                  onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                />
                <input
                  placeholder="Azienda"
                  value={form.company}
                  onChange={(e) => setForm((prev) => ({ ...prev, company: e.target.value }))}
                />
                <input
                  placeholder="Posizione"
                  value={form.role}
                  onChange={(e) => setForm((prev) => ({ ...prev, role: e.target.value }))}
                />
              </div>
              <textarea
                placeholder="Note strategiche (es. interesse call, ruolo in consorzio, readiness)"
                value={form.notes}
                onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
                rows={3}
              />

              <div className="profiles-tag-box">
                <h4>Taxonomy Builder</h4>
                <div className="row">
                  <input
                    placeholder="Nuovo tag"
                    value={newTagLabel}
                    onChange={(e) => setNewTagLabel(e.target.value)}
                  />
                  <select value={newTagScope} onChange={(e) => setNewTagScope(e.target.value as 'company' | 'personal')}>
                    <option value="company">Tag azienda</option>
                    <option value="personal">Sottotag persona</option>
                  </select>
                  <div className="profiles-color-palette" role="group" aria-label="Selezione colore tag">
                    {TAG_COLORS.map((color) => {
                      const isActive = newTagColor === color;
                      return (
                        <button
                          key={color}
                          type="button"
                          className={isActive ? 'profiles-color-dot active' : 'profiles-color-dot'}
                          style={{ backgroundColor: color }}
                          aria-label={`Seleziona colore ${color}`}
                          onClick={() => setNewTagColor(color)}
                        />
                      );
                    })}
                  </div>
                  <span className="profiles-color-preview" style={{ backgroundColor: newTagColor }} />
                  <button onClick={addTag}>Crea tag</button>
                </div>

                <div className="profiles-chip-row">
                  <span className="small"><strong>Tag Azienda:</strong></span>
                  {companyTags.length === 0 ? <span className="small">Nessun tag azienda creato.</span> : null}
                  {companyTags.map((t) => {
                    const selected = form.companyTagIds.includes(t.id);
                    return (
                      <button
                        key={t.id}
                        className="profiles-tag-chip"
                        onClick={() => toggleCompanyFormTag(t.id)}
                        style={{
                          background: selected ? t.color : '#111111',
                          color: '#f5f5f5',
                          border: `1px solid ${t.color}`,
                        }}
                      >
                        {t.label}
                      </button>
                    );
                  })}
                </div>

                <div className="profiles-chip-row">
                  <span className="small"><strong>Sottotag Persona:</strong></span>
                  {personalTags.length === 0 ? <span className="small">Nessun sottotag personale creato.</span> : null}
                  {personalTags.map((t) => {
                    const selected = form.personalSubTagIds.includes(t.id);
                    return (
                      <button
                        key={`${t.id}-personal`}
                        className="profiles-tag-chip"
                        onClick={() => togglePersonalFormTag(t.id)}
                        style={{
                          background: selected ? t.color : '#111111',
                          color: '#f5f5f5',
                          border: `1px solid ${t.color}`,
                        }}
                      >
                        {t.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="row">
                <button onClick={saveContact}>Salva persona</button>
              </div>
            </div>
          ) : (
            <p className="small">Clicca "Nuova persona" per inserire un contatto CRM con tag Horizon-oriented.</p>
          )}
        </article>

        <article className="card profiles-filter-card">
          <h3>Filtri Portfolio</h3>
          <p className="small">Ricerca avanzata su nome, ruolo, note, tag, score e readiness.</p>
          <input
            placeholder="Cerca azienda"
            value={companyFilter}
            onChange={(e) => setCompanyFilter(e.target.value)}
          />
          <div className="profiles-input-grid">
            <input
              placeholder="Filtro ruolo (es. CTO, PM)"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            />
            <input
              placeholder="Filtro note (keyword)"
              value={notesFilter}
              onChange={(e) => setNotesFilter(e.target.value)}
            />
          </div>
          <div className="profiles-filter-range">
            <label className="small">Score minimo: {minScoreFilter}</label>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minScoreFilter}
              onChange={(e) => setMinScoreFilter(Number(e.target.value))}
            />
          </div>
          <select value={readinessFilter} onChange={(e) => setReadinessFilter(e.target.value as 'all' | 'high' | 'medium' | 'low')}>
            <option value="all">Readiness: Tutte</option>
            <option value="high">Readiness: High</option>
            <option value="medium">Readiness: Medium</option>
            <option value="low">Readiness: Low</option>
          </select>
          <div className="profiles-chip-row">
            {companyTags.length === 0 ? <span className="small">Nessun tag azienda disponibile.</span> : null}
            {companyTags.map((t) => {
              const selected = tagFilterIds.includes(t.id);
              return (
                <button
                  key={t.id}
                  className="profiles-tag-chip"
                  onClick={() => toggleFilterTag(t.id)}
                  style={{
                    background: selected ? t.color : '#111111',
                    color: '#f5f5f5',
                    border: `1px solid ${t.color}`,
                  }}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          <div className="profiles-copilot card-premium">
            <h4>CRM Copilot</h4>
            <p className="small">Analisi assistita su partner, gap di consorzio e next action.</p>
            <textarea
              rows={3}
              placeholder="Es: Suggerisci i 3 partner migliori per una call CL4 con TRL 6-7."
              value={copilotPrompt}
              onChange={(e) => setCopilotPrompt(e.target.value)}
            />
            <div className="row">
              <button onClick={() => { void runCopilot(); }} disabled={copilotLoading}>
                {copilotLoading ? 'Analisi in corso...' : 'Esegui analisi'}
              </button>
            </div>
            {copilotError ? <p className="small">{copilotError}</p> : null}
            {copilotAnswer ? <p className="small">{copilotAnswer}</p> : null}
          </div>
        </article>
      </section>

      <section className="profiles-company-board">
        {cards.length === 0 ? (
          <div className="card"><p className="small">Nessuna scheda azienda trovata.</p></div>
        ) : (
          cards.map((card) => (
            <article className="card profiles-company-card" key={card.key}>
              <div className="profiles-company-head">
                <div>
                  <h3>{card.name}</h3>
                  <p className="small">Contatti: {card.contacts.length}</p>
                </div>
                <span className="score">Score {card.scores.overall}</span>
              </div>

              <div className="profiles-score-grid">
                <div className="profiles-score-item">
                  <span className="small">Technical Fit</span>
                  <strong>{card.scores.technicalFit}</strong>
                </div>
                <div className="profiles-score-item">
                  <span className="small">Consortium Value</span>
                  <strong>{card.scores.consortiumValue}</strong>
                </div>
                <div className="profiles-score-item">
                  <span className="small">Readiness</span>
                  <strong>{card.scores.readiness} ({card.readinessBand})</strong>
                </div>
                <div className="profiles-score-item">
                  <span className="small">Geo Relevance</span>
                  <strong>{card.scores.geoRelevance}</strong>
                </div>
              </div>
              <RadarMini
                technicalFit={card.scores.technicalFit}
                consortiumValue={card.scores.consortiumValue}
                readiness={card.scores.readiness}
                geoRelevance={card.scores.geoRelevance}
              />
              <p className="small">Call correlate: {card.callsCount}</p>

              <div className="profiles-people-list">
                {card.contacts.slice(0, 4).map((c) => (
                  <div key={c.id} className="profiles-person-pill">
                    <span>{c.firstName[0]}{c.lastName[0]}</span>
                    <div>
                      <strong>{c.firstName} {c.lastName}</strong>
                      <p className="small">{c.role || 'Role not set'}</p>
                    </div>
                  </div>
                ))}
              </div>

              <p className="small"><strong>Tag azienda</strong></p>
              <div className="profiles-chip-row">
                {companyTags.length === 0 ? <span className="small">Nessun tag.</span> : null}
                {companyTags.map((t) => {
                  const selected = companyHasTag(card, t.id);
                  return (
                    <button
                      key={t.id}
                      className="profiles-tag-chip"
                      onClick={() => toggleCompanyTag(card, t.id)}
                      style={{
                        background: selected ? t.color : '#111111',
                        color: '#f5f5f5',
                        border: `1px solid ${t.color}`,
                      }}
                    >
                      {t.label}
                    </button>
                  );
                })}
              </div>

              <Link className="link-btn" href={`/profiles/company/${card.key}`} target="_blank">Apri scheda completa</Link>
            </article>
          ))
        )}
      </section>
    </section>
  );
}
