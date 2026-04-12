'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

const CALL_VIEWER_KEY = 'horizon-radar-selected-call';

type Payload = {
  clusterId: string;
  rank: number;
  topic: {
    topicTitle: string;
    topicText: string;
    summary: string;
    score: number;
    recommendation: string;
    overallFit: number;
    gapScore: number;
    readinessScore: number;
    partnerDependencyScore: number;
    submissionPriority: number;
    confidence: number;
    recommendedRole: string;
    whyFit: string[];
    whyNotFit: string[];
    mustHaveGaps: string[];
    niceToHaveGaps: string[];
    suggestedPartnerTypes: string[];
    suggestedActions: string[];
  };
  generatedAt: string;
};

export default function CallViewerPage() {
  const [payload, setPayload] = useState<Payload | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(CALL_VIEWER_KEY);
      if (!raw) return;
      setPayload(JSON.parse(raw) as Payload);
    } catch {
      setPayload(null);
    }
  }, []);

  if (!payload) {
    return (
      <section>
        <h1>Nessuna call selezionata</h1>
        <p className="small">Apri una call dalla pagina cluster con "Apri testo completo (nuova scheda)".</p>
        <Link href="/">Torna alla home</Link>
      </section>
    );
  }

  const { topic } = payload;

  return (
    <section>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>Call #{payload.rank} - {payload.clusterId}</h1>
        <Link href={`/cluster/${payload.clusterId}`}>Torna al cluster</Link>
      </div>

      <div className="card">
        <h3>{topic.topicTitle}</h3>
        <p><strong>Overall fit:</strong> {Math.round(topic.overallFit)}/100</p>
        <p><strong>Gap:</strong> {Math.round(topic.gapScore)}/100 | <strong>Readiness:</strong> {Math.round(topic.readinessScore)}/100</p>
        <p><strong>Submission priority:</strong> {Math.round(topic.submissionPriority)}/100</p>
        <p><strong>Recommendation:</strong> <span className="score">{topic.recommendation}</span> | <strong>Role:</strong> {topic.recommendedRole}</p>
        <p><strong>Riassunto:</strong> <span className="small">{topic.summary}</span></p>
        <p><strong>Confidence:</strong> <span className="small">{Math.round(topic.confidence)}/100</span></p>
        <p><strong>Must-have gaps:</strong> <span className="small">{topic.mustHaveGaps.join(', ') || 'nessun gap critico'}</span></p>
        <p><strong>Partner suggeriti:</strong> <span className="small">{topic.suggestedPartnerTypes.join(', ') || 'n/d'}</span></p>
      </div>

      <div className="card">
        <h3>Evidenze e Gap</h3>
        <p><strong>Why fit:</strong></p>
        <ul>{topic.whyFit.map((line, idx) => <li key={`wf-${idx}`}>{line}</li>)}</ul>
        <p><strong>Why not fit:</strong></p>
        <ul>{topic.whyNotFit.map((line, idx) => <li key={`wn-${idx}`}>{line}</li>)}</ul>
        <p><strong>Nice-to-have gaps:</strong></p>
        <ul>{topic.niceToHaveGaps.map((line, idx) => <li key={`ng-${idx}`}>{line}</li>)}</ul>
        <p><strong>Suggested actions:</strong></p>
        <ul>{topic.suggestedActions.map((line, idx) => <li key={`sa-${idx}`}>{line}</li>)}</ul>
      </div>
    </section>
  );
}
