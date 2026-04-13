'use client';

import { useSearchParams } from 'next/navigation';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { apiGet } from '@/lib/api';
import type { Topic, TopicDecisionCardV2 } from '@/lib/types';

export default function TopicDetailPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const profileId = search.get('profileId');
  const [topic, setTopic] = useState<Topic | null>(null);
  const [fit, setFit] = useState<TopicDecisionCardV2 | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const topicId = params.id;
    if (!topicId) return;
    apiGet<Topic>(`/api/topics/${topicId}`)
      .then((data) => {
        setTopic(data);
        setError(null);
      })
      .catch((err) => setError(String(err)));
    if (profileId) {
      apiGet<TopicDecisionCardV2>(`/api/v2/topics/${topicId}/decision-card?profile_id=${profileId}&model_version=v2-sprint1`)
        .then((data) => {
          setFit(data);
          setError(null);
        })
        .catch(() => setFit(null));
    }
  }, [params.id, profileId]);

  if (!topic) {
    if (error) return <p>API error: {error}</p>;
    return <p>Loading...</p>;
  }

  return (
    <section className="apple-detail-page topic-detail-page">
      <header className="apple-detail-hero">
        <p className="apple-detail-kicker">Topic</p>
        <h1>{topic.topic_id}</h1>
        <p className="small">{topic.title}</p>
      </header>

      <div className="card apple-detail-panel">
        <h3>Key requirements</h3>
        <p className="small">Cluster: {topic.cluster || 'N/A'} | Action type: {topic.action_type || 'N/A'}</p>
        <p className="small">TRL: {topic.trl_min ?? '?'}-{topic.trl_max ?? '?'}</p>
      </div>

      {fit ? (
        <div className="card apple-detail-panel">
          <h3>Decision Card V2</h3>
          <p><strong>Overall fit:</strong> {Math.round(fit.overall_fit)}/100</p>
          <p><strong>Gap:</strong> {Math.round(fit.gap_score)}/100 | <strong>Readiness:</strong> {Math.round(fit.readiness_score)}/100</p>
          <p><strong>Partner dependency:</strong> {Math.round(fit.partner_dependency_score)}/100</p>
          <p><strong>Submission priority:</strong> {Math.round(fit.submission_priority)}/100</p>
          <p><strong>Confidence:</strong> {Math.round(fit.confidence)}/100</p>
          <p><strong>Recommendation:</strong> {fit.recommendation} | <strong>Role:</strong> {fit.recommended_role}</p>
          <p><strong>Why fit:</strong></p>
          <ul>{fit.why_fit.map((e, i) => <li key={`wf-${i}`}>{e}</li>)}</ul>
          <p><strong>Why not fit:</strong></p>
          <ul>{fit.why_not_fit.map((e, i) => <li key={`wn-${i}`}>{e}</li>)}</ul>
          <p><strong>Must-have gaps:</strong></p>
          <ul>{fit.must_have_gaps.map((e, i) => <li key={`mg-${i}`}>{e}</li>)}</ul>
          <p><strong>Suggested partner types:</strong> {fit.suggested_partner_types.join(', ') || 'n/d'}</p>
          <p><strong>Suggested actions:</strong> {fit.suggested_actions.join(' | ') || 'n/d'}</p>
        </div>
      ) : (
        <p className="small">Run V2 matching to view decision card, gap analysis and recommendation.</p>
      )}
    </section>
  );
}
