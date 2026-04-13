'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { apiGet, apiPost } from '@/lib/api';
import type { HorizonMatcherResponse, Profile } from '@/lib/types';

type MatcherPayload = {
  profile: {
    description: string;
    mission: string;
    technical_knowhow: string;
    keywords: string[];
    trl_current: number;
    is_sme: boolean;
    ssh_capacity: boolean;
    fair_compliant: boolean;
    gender_dimension_active: boolean;
    clusters_interest: string[];
  };
  top_n: number;
};

export default function MatcherPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [description, setDescription] = useState('');
  const [mission, setMission] = useState('');
  const [knowhow, setKnowhow] = useState('');
  const [keywords, setKeywords] = useState('');
  const [clusters, setClusters] = useState('Health, Digital');
  const [topN, setTopN] = useState(10);
  const [trl, setTrl] = useState(5);
  const [isSME, setIsSME] = useState(true);
  const [ssh, setSsh] = useState(false);
  const [fair, setFair] = useState(true);
  const [gender, setGender] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<HorizonMatcherResponse | null>(null);

  function hydrateFromProfile(profile: Profile) {
    const constraints = (profile.constraints || {}) as Record<string, unknown>;
    const pickString = (...keys: string[]): string => {
      for (const key of keys) {
        const value = constraints[key];
        if (typeof value === 'string' && value.trim().length) return value.trim();
      }
      return '';
    };
    const pickBool = (...keys: string[]): boolean => {
      for (const key of keys) {
        const value = constraints[key];
        if (typeof value === 'boolean') return value;
      }
      return false;
    };
    const pickNumber = (...keys: string[]): number | null => {
      for (const key of keys) {
        const value = constraints[key];
        if (typeof value === 'number' && Number.isFinite(value)) return value;
      }
      return null;
    };
    const pickStringArray = (...keys: string[]): string[] => {
      for (const key of keys) {
        const value = constraints[key];
        if (Array.isArray(value)) {
          const arr = value.map((x) => String(x).trim()).filter(Boolean);
          if (arr.length) return arr;
        }
      }
      return [];
    };

    const profileKeywords = pickStringArray('keywords');
    const profileClusters = pickStringArray('clusters_interest', 'clusters').length
      ? pickStringArray('clusters_interest', 'clusters')
      : profile.tags || [];

    const profileDescription = profile.description || '';
    const missionValue = pickString('mission', 'company_mission', 'summary', 'value_proposition');
    const knowhowValue = pickString('technical_knowhow', 'technicalKnowhow', 'know_how', 'capabilities');
    setDescription(profileDescription);
    setMission(missionValue || profileDescription.slice(0, 280));
    setKnowhow(knowhowValue || [profile.tags?.join(', '), profileDescription.slice(0, 280)].filter(Boolean).join(' '));
    setKeywords(profileKeywords.join(', '));
    setClusters(profileClusters.join(', '));
    setTrl(pickNumber('trl_current', 'trl') || 5);
    setIsSME(pickBool('is_sme', 'sme'));
    setSsh(pickBool('ssh_capacity', 'ssh'));
    setFair(pickBool('fair_compliant', 'fair'));
    setGender(pickBool('gender_dimension_active', 'gender'));
  }

  useEffect(() => {
    let mounted = true;
    async function loadProfiles() {
      try {
        const data = await apiGet<Profile[]>('/profiles');
        if (!mounted) return;
        setProfiles(data);
        if (data.length > 0) {
          setSelectedProfileId(String(data[0].id));
          hydrateFromProfile(data[0]);
        }
      } catch {
        if (!mounted) return;
        setProfiles([]);
      }
    }
    void loadProfiles();
    return () => {
      mounted = false;
    };
  }, []);

  const canSubmit = useMemo(
    () => description.trim().length > 24 && mission.trim().length > 12 && knowhow.trim().length > 12,
    [description, mission, knowhow],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setError('');
    try {
      const payload: MatcherPayload = {
        profile: {
          description: description.trim(),
          mission: mission.trim(),
          technical_knowhow: knowhow.trim(),
          keywords: keywords
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean),
          trl_current: trl,
          is_sme: isSME,
          ssh_capacity: ssh,
          fair_compliant: fair,
          gender_dimension_active: gender,
          clusters_interest: clusters
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean),
        },
        top_n: topN,
      };
      const data = await apiPost<HorizonMatcherResponse>('/horizon-matcher/score', payload);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="matcher-page">
      <header className="matcher-hero">
        <p className="matcher-kicker">Horizon Europe Matcher</p>
        <h1>Reliability fit in stile Apple.</h1>
        <p>
          Motore semantico locale con BM25, TRL constraints e audit log integrato nella piattaforma.
        </p>
      </header>

      <form className="matcher-form" onSubmit={onSubmit}>
        <label>
          Profilo esistente
          <select
            value={selectedProfileId}
            onChange={(e) => {
              const value = e.target.value;
              setSelectedProfileId(value);
              const profile = profiles.find((p) => String(p.id) === value);
              if (profile) hydrateFromProfile(profile);
            }}
          >
            {profiles.length === 0 ? <option value="">Nessun profilo trovato</option> : null}
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Descrizione aziendale
          <textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label>
          Mission
          <textarea rows={3} value={mission} onChange={(e) => setMission(e.target.value)} />
        </label>
        <label>
          Know-how tecnico
          <textarea rows={3} value={knowhow} onChange={(e) => setKnowhow(e.target.value)} />
        </label>
        <div className="matcher-grid">
          <label>
            Keywords (comma-separated)
            <input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="digital twin, federated learning" />
          </label>
          <label>
            Cluster interesse (comma-separated)
            <input value={clusters} onChange={(e) => setClusters(e.target.value)} placeholder="Health, Digital" />
          </label>
        </div>
        <div className="matcher-grid matcher-grid--compact">
          <label>
            TRL corrente
            <input type="number" min={1} max={9} value={trl} onChange={(e) => setTrl(Number(e.target.value) || 5)} />
          </label>
          <label>
            Top N
            <input type="number" min={1} max={30} value={topN} onChange={(e) => setTopN(Number(e.target.value) || 10)} />
          </label>
        </div>
        <div className="matcher-toggles">
          <label><input type="checkbox" checked={isSME} onChange={(e) => setIsSME(e.target.checked)} /> SME</label>
          <label><input type="checkbox" checked={ssh} onChange={(e) => setSsh(e.target.checked)} /> SSH capacity</label>
          <label><input type="checkbox" checked={fair} onChange={(e) => setFair(e.target.checked)} /> FAIR compliance</label>
          <label><input type="checkbox" checked={gender} onChange={(e) => setGender(e.target.checked)} /> Gender dimension</label>
        </div>
        <button type="submit" disabled={!canSubmit || loading}>
          {loading ? 'Calcolo in corso...' : 'Calcola fit'}
        </button>
        {error ? <p className="small" style={{ color: '#ff8b8b' }}>{error}</p> : null}
      </form>

      {result ? (
        <section className="matcher-results">
          <h3>Top {result.results.length} su {result.total_calls} call</h3>
          <p className="small">Generato: {new Date(result.generated_at).toLocaleString()}</p>
          <div className="matcher-card-list">
            {result.results.map((item) => (
              <article key={item.call_id} className="matcher-card">
                <p className="matcher-score">{Math.round(item.reliability_score * 100)}%</p>
                <h4>{item.call_id}</h4>
                <p>{item.title}</p>
                <p className="small">
                  {item.cluster || 'Unknown'} · {item.type_of_action || 'N/A'}
                </p>
                <p className="small">
                  Semantic {item.score_breakdown.semantic_score.toFixed(2)} · BM25 {item.score_breakdown.bm25_score.toFixed(2)} · Constraints {item.score_breakdown.constraints_score.toFixed(2)}
                </p>
                <p className="small">{item.justification}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
