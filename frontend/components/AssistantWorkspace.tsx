'use client';

import { useState } from 'react';
import { apiPost } from '@/lib/api';
import type { ReportAssistantResponse } from '@/lib/types';

type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sources?: Array<Record<string, unknown>>;
};

const SUGGESTIONS = [
  'Dimmi le deadline delle prossime call Horizon',
  'Trova i brokerage events nei prossimi 5 mesi',
  'Ci sono nuovi draft work programme?',
];

function makeId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}-${Date.now()}`;
}

export function AssistantWorkspace() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Scrivi una domanda su deadline Horizon, brokerage events o draft work programme. Puoi anche usare i suggerimenti qui sotto.',
    },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const runQuery = async (nextQuery?: string) => {
    const finalQuery = (nextQuery ?? query).trim();
    if (!finalQuery) return;

    const userMessage: Message = {
      id: makeId('user'),
      role: 'user',
      text: finalQuery,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuery('');
    setError(null);
    setLoading(true);

    try {
      const result = await apiPost<ReportAssistantResponse>('/api/reports/assistant/query', { query: finalQuery });
      setMessages((prev) => [
        ...prev,
        {
          id: makeId('assistant'),
          role: 'assistant',
          text: result.answer,
          sources: result.sources || [],
        },
      ]);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <div className="hero">
        <h1>Assistant</h1>
        <p className="lead">
          Chat operativa per Horizon Europe. Fai una domanda, usa i prompt suggeriti e lavora da qui senza aprire la
          vecchia sezione report.
        </p>
      </div>

      <div className="card">
        <div className="row">
          {SUGGESTIONS.map((item) => (
            <button className="btn-soft" key={item} onClick={() => { void runQuery(item); }}>
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="assistant-shell">
        <div className="assistant-thread card">
          {messages.map((message) => (
            <article
              key={message.id}
              className={message.role === 'user' ? 'assistant-bubble assistant-user' : 'assistant-bubble assistant-ai'}
            >
              <div className="small" style={{ marginBottom: '0.35rem' }}>
                {message.role === 'user' ? 'Tu' : 'Assistant'}
              </div>
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{message.text}</div>

              {message.sources && message.sources.length > 0 ? (
                <div className="assistant-sources">
                  {message.sources.map((source, index) => {
                    const title = String(source.title || source.topic_id || `Item ${index + 1}`);
                    const link = typeof source.link === 'string'
                      ? source.link
                      : (typeof source.file_url === 'string' ? source.file_url : '');
                    const sourceLabel = typeof source.source === 'string' ? source.source : '';
                    const explanation = typeof source.explanation === 'string' ? source.explanation : '';
                    const date = typeof source.deadline === 'string'
                      ? new Date(source.deadline).toLocaleDateString()
                      : (typeof source.date === 'string' ? source.date : '');

                    return (
                      <div className="assistant-source-card" key={`${title}-${index}`}>
                        <strong>{title}</strong>
                        {date ? <p className="small">Data: {date}</p> : null}
                        {sourceLabel ? <p className="small">Fonte: {sourceLabel}</p> : null}
                        {explanation ? <p className="small">{explanation}</p> : null}
                        {link ? <a className="link-btn" href={link} target="_blank">Apri link</a> : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </article>
          ))}

          {loading ? (
            <article className="assistant-bubble assistant-ai">
              <div className="small" style={{ marginBottom: '0.35rem' }}>Assistant</div>
              <div>Sto cercando nelle fonti monitorate...</div>
            </article>
          ) : null}
        </div>

        <div className="card">
          <textarea
            rows={5}
            style={{ width: '100%' }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Per esempio: dimmi le prossime deadline Horizon 2026, trova brokerage nei prossimi 5 mesi, ci sono nuovi draft?"
          />
          <div className="row" style={{ marginTop: '0.8rem' }}>
            <button onClick={() => { void runQuery(); }} disabled={loading}>
              {loading ? 'Ricerca in corso...' : 'Invia'}
            </button>
          </div>
          {error ? <p className="small" style={{ marginTop: '0.8rem' }}>{error}</p> : null}
        </div>
      </div>
    </section>
  );
}
