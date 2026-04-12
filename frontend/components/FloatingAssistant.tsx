'use client';

import Image from 'next/image';
import { KeyboardEvent, useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { apiPost } from '@/lib/api';
import type { ReportAssistantResponse } from '@/lib/types';

type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sources?: Array<Record<string, unknown>>;
  createdAt: string;
};

const SUGGESTIONS = [
  'Prossime deadline Horizon',
  'Brokerage events prossimi 5 mesi',
  'Nuovi draft work programme?',
];
const CHAT_SPHERE_PLANES = Array.from({ length: 6 }, (_, idx) => idx + 1);
const CHAT_SPHERE_SPOKES = Array.from({ length: 18 }, (_, idx) => idx + 1);
const FIT_STREAM_EVENT = 'horizon-fit-stream';

type FitStreamTopic = { id: number; score: number; recommendation: string };
type FitStreamState = {
  active: boolean;
  stage: string;
  title: string;
  lines: string[];
  topics: FitStreamTopic[];
};

function makeId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}-${Date.now()}`;
}

export function FloatingAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Assistant pronto. Posso analizzare call, draft e timeline per supportare decisioni R&D.',
      createdAt: new Date().toISOString(),
    },
  ]);
  const [fitStream, setFitStream] = useState<FitStreamState>({
    active: false,
    stage: 'idle',
    title: '',
    lines: [],
    topics: [],
  });

  useEffect(() => {
    const onFitStream = (event: Event) => {
      const custom = event as CustomEvent<{
        active?: boolean;
        stage?: string;
        title?: string;
        lines?: string[];
        topics?: FitStreamTopic[];
      }>;
      const detail = custom.detail || {};
      setFitStream({
        active: Boolean(detail.active),
        stage: String(detail.stage || 'idle'),
        title: String(detail.title || ''),
        lines: Array.isArray(detail.lines) ? detail.lines.map((x) => String(x)) : [],
        topics: Array.isArray(detail.topics) ? detail.topics : [],
      });
    };
    window.addEventListener(FIT_STREAM_EVENT, onFitStream as EventListener);
    return () => window.removeEventListener(FIT_STREAM_EVENT, onFitStream as EventListener);
  }, []);

  const canShowPanel = isOpen && !isMinimized;
  const lastAssistantMessage = useMemo(
    () => [...messages].reverse().find((m) => m.role === 'assistant') || null,
    [messages],
  );

  const openPanel = () => {
    setIsOpen(true);
    setIsMinimized(false);
  };

  const hidePanel = () => {
    setIsMinimized(true);
  };

  const closePanel = () => {
    setIsOpen(false);
    setIsMinimized(false);
  };

  const runQuery = async (nextQuery?: string) => {
    const finalQuery = (nextQuery ?? query).trim();
    if (!finalQuery || loading) return;

    const userMessage: Message = {
      id: makeId('user'),
      role: 'user',
      text: finalQuery,
      createdAt: new Date().toISOString(),
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
          createdAt: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void runQuery();
    }
  };

  const formatTime = (iso: string) =>
    new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });

  const clearDraft = () => setQuery('');

  return (
    <div className={`floating-chat-root${fitStream.active ? ' is-fit-live' : ''}`} aria-live="polite">
      {fitStream.active ? (
        <aside className="floating-fit-stream-panel" role="status" aria-live="polite" aria-label="Output fit da server">
          <div className="floating-fit-stream-head">
            <div className="floating-fit-stream-title">{fitStream.title || 'Fit in corso'}</div>
            <span className="floating-fit-stream-stage">{fitStream.stage}</span>
          </div>
          <div className="floating-fit-stream-body">
            {fitStream.lines.length > 0 ? (
              <ul>
                {fitStream.lines.map((line, idx) => <li key={`${fitStream.stage}-line-${idx}`}>{line}</li>)}
              </ul>
            ) : (
              <p className="small">Attendo output server...</p>
            )}
            {fitStream.topics.length > 0 ? (
              <div className="floating-fit-stream-topics">
                {fitStream.topics.slice(0, 4).map((topic, idx) => (
                  <div key={`${fitStream.stage}-topic-${idx}`} className="floating-fit-stream-topic">
                    <span>#{topic.id}</span>
                    <span>{topic.score}/100</span>
                    <span>{topic.recommendation}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </aside>
      ) : null}
      {canShowPanel ? (
        <aside className="floating-chat-panel" role="dialog" aria-label="Assistant chat">
          <div className="floating-chat-header">
            <div className="floating-chat-brand">
              <Image src="/images/logo.png" alt="Logo" width={24} height={24} />
              <div>
                <div className="floating-chat-title">Assistant</div>
                <div className="floating-chat-subtitle">R&D Decision Support</div>
              </div>
            </div>
            <div className="floating-chat-health">
              <span className="floating-chat-health-dot" />
              API ready
            </div>
            <div className="floating-chat-controls">
              <button className="btn-soft" type="button" aria-label="Model selector" disabled>
                Groq
              </button>
              <button className="btn-soft" onClick={hidePanel} type="button" aria-label="Nascondi chat">
                Nascondi
              </button>
              <button className="btn-danger" onClick={closePanel} type="button" aria-label="Chiudi chat">
                Chiudi
              </button>
            </div>
          </div>

          <div className="floating-chat-suggestions" aria-label="Suggerimenti rapidi">
            {SUGGESTIONS.map((item) => (
              <button key={item} className="floating-chat-chip" onClick={() => { void runQuery(item); }} type="button">
                {item}
              </button>
            ))}
          </div>

          <div className="floating-chat-thread">
            <p className="floating-chat-thread-label">Conversation</p>
            {messages.map((message) => (
              <article
                key={message.id}
                className={message.role === 'user' ? 'floating-chat-bubble user' : 'floating-chat-bubble assistant'}
              >
                <div className="floating-chat-bubble-meta">
                  <span>{message.role === 'user' ? 'You' : 'Assistant'}</span>
                  <span>{formatTime(message.createdAt)}</span>
                </div>
                <div>{message.text}</div>
                {message.sources && message.sources.length > 0 ? (
                  <div className="floating-chat-sources">
                    <span className="small">Fonti</span>
                    <div className="floating-chat-source-list">
                      {message.sources.slice(0, 5).map((_, idx) => (
                        <span key={`${message.id}-src-${idx}`} className="floating-chat-source-pill">
                          Source {idx + 1}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
            {loading ? (
              <article className="floating-chat-bubble assistant">
                <div className="floating-chat-bubble-meta">
                  <span>Assistant</span>
                  <span>now</span>
                </div>
                <div className="floating-chat-typing">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            ) : null}
          </div>

          {error ? <p className="small">{error}</p> : null}

          <div className="floating-chat-input-wrap">
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              maxLength={2000}
              rows={3}
              placeholder="Scrivi una richiesta per analisi call, fit, rischi o timeline..."
            />
            <div className="floating-chat-composer-footer">
              <span className="small">{query.trim().length}/2000</span>
              <div className="floating-chat-composer-actions">
                <button className="btn-soft" onClick={clearDraft} type="button" disabled={!query}>
                  Pulisci
                </button>
                <button onClick={() => { void runQuery(); }} type="button" disabled={loading}>
                  {loading ? 'Attendi...' : 'Invia'}
                </button>
              </div>
            </div>
          </div>
        </aside>
      ) : null}

      {!canShowPanel && !fitStream.active ? (
        <button className="floating-chat-fab" onClick={openPanel} type="button" aria-label="Apri chat assistant">
          <div className="chat-sphere-main-wrapper" aria-hidden="true">
            <div className="chat-sphere-wrapper">
              {CHAT_SPHERE_PLANES.map((plane) => (
                <div
                  key={`plane-${plane}`}
                  className="chat-sphere-plane"
                  style={{ '--plane-rotate': `${plane * 30}deg` } as CSSProperties}
                >
                  {CHAT_SPHERE_SPOKES.map((spoke) => {
                    return (
                      <div
                        key={`plane-${plane}-spoke-${spoke}`}
                        className="chat-sphere-spoke"
                        style={
                          {
                            '--spoke-rotate': `${spoke * 20}deg`,
                          } as CSSProperties
                        }
                      >
                        <div className="chat-sphere-dot" />
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          {isMinimized && lastAssistantMessage ? <span className="floating-chat-dot" /> : null}
        </button>
      ) : null}
    </div>
  );
}
