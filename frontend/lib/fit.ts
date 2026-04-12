export type FitResult = {
  score: number;
  recommendation: 'GO' | 'WATCH' | 'NO-GO';
  explanation: string[];
  gaps: string[];
  matchedKeywords: string[];
  semanticMatchedKeywords: string[];
  keywordMatchedKeywords: string[];
  semanticScore: number;
  keywordScore: number;
};

export type TopicFitResult = FitResult & {
  topicTitle: string;
  topicText: string;
  summary: string;
  topicKeywords: string[];
};

const STOP_WORDS = new Set([
  'about', 'above', 'after', 'again', 'against', 'along', 'also', 'among', 'and', 'are', 'been', 'before', 'being',
  'below', 'between', 'both', 'but', 'can', 'could', 'does', 'during', 'each', 'few', 'for', 'from', 'have', 'having',
  'into', 'just', 'more', 'most', 'other', 'over', 'same', 'should', 'some', 'such', 'than', 'that', 'the', 'their',
  'them', 'then', 'there', 'these', 'they', 'this', 'those', 'through', 'under', 'until', 'very', 'what', 'when',
  'where', 'which', 'while', 'with', 'would', 'your', 'azienda', 'cluster', 'interessi', 'company', 'description',
  'della', 'delle', 'dallo', 'degli', 'dell', 'dalla', 'sulla', 'sulle', 'sugli', 'nelle', 'negli', 'dati',
]);
const SHORT_TECH_TERMS = new Set(['ai', 'ar', 'vr', 'xr', 'ml', 'nlp', 'iot', 'iiot', '5g', '6g']);

function tokenize(text: string): string[] {
  const base = text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .map((w) => stemWord(w.trim()))
    .filter((w) => (w.length >= 3 || SHORT_TECH_TERMS.has(w)) && !STOP_WORDS.has(w));
  return base;
}

function stemWord(w: string): string {
  return w
    .replace(/(ing|tion|ions|ment|ments|ness|ities|ity|ally|able|ible|ers|er|ed|ly|s)$/i, '')
    .trim();
}

function topKeywords(text: string, limit: number): string[] {
  const freq = new Map<string, number>();
  for (const tok of tokenize(text)) {
    freq.set(tok, (freq.get(tok) || 0) + 1);
  }
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([k]) => k);
}

function parseInterestKeywords(interests: string): string[] {
  const chunks = interests
    .toLowerCase()
    .split(/[\n,;|]/)
    .map((x) => x.trim())
    .filter(Boolean);

  const explicitTokens = chunks
    .flatMap((x) => x.split(/[^a-z0-9]+/))
    .map((x) => stemWord(x.trim()))
    .filter((x) => (x.length >= 3 || SHORT_TECH_TERMS.has(x)) && !STOP_WORDS.has(x));

  const explicitPhrases = chunks
    .map((x) => x.replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim())
    .filter((x) => x.length >= 5);

  const inferred = topKeywords(interests, 12);
  return [...new Set([...explicitTokens, ...explicitPhrases, ...inferred])];
}

function recommendationFromScore(score: number): 'GO' | 'WATCH' | 'NO-GO' {
  if (score >= 55) return 'GO';
  if (score >= 30) return 'WATCH';
  return 'NO-GO';
}

function vectorize(tokens: string[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const t of tokens) {
    m.set(t, (m.get(t) || 0) + 1);
  }
  return m;
}

function cosineSimilarity(a: Map<string, number>, b: Map<string, number>): number {
  if (a.size === 0 || b.size === 0) return 0;

  let dot = 0;
  let na = 0;
  let nb = 0;

  for (const [, av] of a) na += av * av;
  for (const [, bv] of b) nb += bv * bv;

  for (const [k, av] of a) {
    const bv = b.get(k) || 0;
    dot += av * bv;
  }

  const den = Math.sqrt(na) * Math.sqrt(nb);
  if (den <= 1e-8) return 0;
  return dot / den;
}

function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const x of a) {
    if (b.has(x)) inter += 1;
  }
  const union = a.size + b.size - inter;
  if (union <= 0) return 0;
  return inter / union;
}

function buildBigrams(tokens: string[]): Set<string> {
  const out = new Set<string>();
  for (let i = 0; i < tokens.length - 1; i++) {
    out.add(`${tokens[i]} ${tokens[i + 1]}`);
  }
  return out;
}

function normalizedScore(raw: number): number {
  const clamped = Math.max(0, Math.min(1, raw));
  return Math.round((1 - Math.exp(-4 * clamped)) * 100);
}

function fuzzyContains(topicKeywordSet: Set<string>, kw: string): boolean {
  if (topicKeywordSet.has(kw)) return true;
  for (const tk of topicKeywordSet) {
    if (tk.startsWith(kw) || kw.startsWith(tk)) return true;
    if (tk.includes(kw) || kw.includes(tk)) return true;
  }
  return false;
}

function phraseInText(text: string, phrase: string): boolean {
  const p = phrase.trim().toLowerCase();
  if (p.length < 3) return false;
  const normalized = text.toLowerCase().replace(/[^a-z0-9\s]/g, ' ');
  return normalized.includes(p);
}

function summarizeText(text: string): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  const sentences = clean.split(/(?<=[.!?])\s+/).filter((s) => s.length > 20);
  if (sentences.length === 0) {
    return clean.slice(0, 260);
  }
  return sentences.slice(0, 2).join(' ').slice(0, 320);
}

function evaluateSingle(companyDescription: string, clusterInterests: string, text: string): FitResult {
  const companyTokens = tokenize(companyDescription);
  const topicTokens = tokenize(text);

  const companyVec = vectorize(companyTokens);
  const topicVec = vectorize(topicTokens);

  // Semantic fit: blend cosine + token-set similarity + bigram overlap.
  const cosine = cosineSimilarity(companyVec, topicVec);
  const setA = new Set(companyTokens);
  const setB = new Set(topicTokens);
  const jac = jaccardSimilarity(setA, setB);
  const biA = buildBigrams(companyTokens);
  const biB = buildBigrams(topicTokens);
  const biJac = jaccardSimilarity(biA, biB);
  const semanticRaw = (cosine * 0.5) + (jac * 0.35) + (biJac * 0.15);
  const semanticScore = normalizedScore(semanticRaw);

  // Keyword fit uses explicit/inferred interest keywords.
  const interestKeywords = parseInterestKeywords(clusterInterests);
  const topicKeywordSet = new Set(topKeywords(text, 160));
  const matchedInterests = interestKeywords.filter((k) => fuzzyContains(topicKeywordSet, k) || phraseInText(text, k));
  let keywordScore = interestKeywords.length > 0
    ? Math.round((matchedInterests.length / interestKeywords.length) * 100)
    : 0;
  if (matchedInterests.length > 0) keywordScore = Math.min(100, keywordScore + 10);

  const matchedCompany = [...new Set(companyTokens.filter((k) => topicKeywordSet.has(k)))].slice(0, 20);
  const missingInterests = interestKeywords.filter((k) => !topicKeywordSet.has(k)).slice(0, 16);

  let score = Math.round((semanticScore * 0.2) + (keywordScore * 0.8));
  if (text && text.trim().length >= 120) {
    score = Math.max(score, 28);
  }
  if (!text || text.trim().length < 120) {
    score = Math.max(0, score - 18);
  }

  const recommendation = recommendationFromScore(score);
  const explanation = [
    `Semantic fit (descrizione azienda vs call): ${semanticScore}/100`,
    `Keyword fit (interessi cluster + termini simili vs call): ${keywordScore}/100`,
    `Final score = 20% semantic + 80% keyword`,
    text && text.trim().length >= 120
      ? 'Testo call disponibile per analisi.'
      : 'Testo call limitato: confidenza inferiore.',
  ];

  return {
    score,
    recommendation,
    explanation,
    gaps: missingInterests,
    matchedKeywords: [...new Set([...matchedCompany, ...matchedInterests])].slice(0, 20),
    semanticMatchedKeywords: matchedCompany.slice(0, 20),
    keywordMatchedKeywords: matchedInterests.slice(0, 20),
    semanticScore,
    keywordScore,
  };
}

function sanitizeTitle(title: string): string {
  return title.replace(/\s+/g, ' ').trim().slice(0, 180);
}

export function extractTopicBlocks(fileText: string): Array<{ topicTitle: string; topicText: string }> {
  const source = (fileText || '').replace(/\r/g, '').trim();
  if (!source) return [];

  const lines = source.split('\n').map((l) => l.trim()).filter(Boolean);
  const blocks: Array<{ topicTitle: string; topicText: string }> = [];
  let currentTitle: string | null = null;
  let currentLines: string[] = [];

  const isTopicStart = (line: string) => {
    if (/\bHORIZON-[A-Z0-9-]+\b/i.test(line)) return true;
    if (/^(topic|call|destination)\b[:\s-]/i.test(line)) return true;
    if (/\btopic\s*id\b/i.test(line)) return true;
    return false;
  };

  const pushCurrent = () => {
    if (!currentTitle || currentLines.length === 0) return;
    const topicText = currentLines.join(' ').slice(0, 50000);
    if (topicText.length < 80) return;
    blocks.push({ topicTitle: sanitizeTitle(currentTitle), topicText });
  };

  for (const line of lines) {
    if (isTopicStart(line)) {
      pushCurrent();
      currentTitle = line;
      currentLines = [line];
      continue;
    }

    if (!currentTitle) {
      currentTitle = line.slice(0, 120);
      currentLines = [line];
      continue;
    }

    currentLines.push(line);
  }

  pushCurrent();

  if (blocks.length === 0) {
    const marker = /\bHORIZON-[A-Z0-9-]+\b/gi;
    const matches = [...source.matchAll(marker)];
    if (matches.length > 0) {
      for (let i = 0; i < matches.length; i++) {
        const start = matches[i].index || 0;
        const end = i + 1 < matches.length ? (matches[i + 1].index || source.length) : source.length;
        const chunk = source.slice(start, end).trim();
        if (chunk.length < 80) continue;
        blocks.push({
          topicTitle: sanitizeTitle(chunk.slice(0, 140)),
          topicText: chunk.slice(0, 50000),
        });
        if (blocks.length >= 30) break;
      }
    }
  }

  if (blocks.length === 0) {
    const paras = source.split(/\n\n+/).map((p) => p.trim()).filter((p) => p.length > 120);
    for (let i = 0; i < paras.length && i < 30; i++) {
      blocks.push({
        topicTitle: `Topic block ${i + 1}`,
        topicText: paras[i].slice(0, 50000),
      });
    }
  }

  if (blocks.length === 0) {
    const chunkSize = 2800;
    for (let start = 0, idx = 1; start < source.length && idx <= 30; start += chunkSize, idx += 1) {
      const chunk = source.slice(start, start + chunkSize).trim();
      if (chunk.length < 60) continue;
      blocks.push({
        topicTitle: `Topic chunk ${idx}`,
        topicText: chunk,
      });
    }
  }

  const dedup = new Map<string, { topicTitle: string; topicText: string }>();
  for (const b of blocks) {
    const key = `${b.topicTitle}|${b.topicText.slice(0, 90)}`;
    dedup.set(key, b);
  }

  return [...dedup.values()].slice(0, 30);
}

export function evaluateTopicFits(
  companyDescription: string,
  clusterInterests: string,
  fileText: string,
): TopicFitResult[] {
  const topics = extractTopicBlocks(fileText);
  if (topics.length === 0) return [];

  return topics
    .map((topic) => {
      const fit = evaluateSingle(companyDescription, clusterInterests, topic.topicText);
      return {
        ...fit,
        topicTitle: topic.topicTitle,
        topicText: topic.topicText,
        summary: summarizeText(topic.topicText),
        topicKeywords: topKeywords(topic.topicText, 10),
      };
    })
    .sort((a, b) => b.score - a.score);
}

export function evaluateFit(companyDescription: string, clusterInterests: string, fileText: string): FitResult {
  const topicFits = evaluateTopicFits(companyDescription, clusterInterests, fileText);
  if (topicFits.length === 0) {
    return evaluateSingle(companyDescription, clusterInterests, fileText || '');
  }

  const top = topicFits.slice(0, 3);
  const score = Math.round(top.reduce((acc, x) => acc + x.score, 0) / top.length);
  const semanticScore = Math.round(top.reduce((acc, x) => acc + x.semanticScore, 0) / top.length);
  const keywordScore = Math.round(top.reduce((acc, x) => acc + x.keywordScore, 0) / top.length);
  const recommendation = recommendationFromScore(score);

  const matchedKeywords = [...new Set(top.flatMap((x) => x.matchedKeywords))].slice(0, 24);
  const semanticMatchedKeywords = [...new Set(top.flatMap((x) => x.semanticMatchedKeywords))].slice(0, 24);
  const keywordMatchedKeywords = [...new Set(top.flatMap((x) => x.keywordMatchedKeywords))].slice(0, 24);
  const gaps = [...new Set(top.flatMap((x) => x.gaps))].slice(0, 20);

  return {
    score,
    recommendation,
    semanticScore,
    keywordScore,
    explanation: [
      `Topics analizzati: ${topicFits.length}`,
      `Semantic medio (top-3): ${semanticScore}/100`,
      `Keyword medio (top-3): ${keywordScore}/100`,
      `Formula score finale: 20% semantic + 80% keyword`,
      `Best topic: ${topicFits[0].topicTitle}`,
    ],
    gaps,
    matchedKeywords,
    semanticMatchedKeywords,
    keywordMatchedKeywords,
  };
}
