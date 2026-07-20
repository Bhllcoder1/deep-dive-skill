/**
 * Claude Code Deep Research Workflow
 * ===================================
 * 
 * Bu workflow Claude Code'un KENDİ built-in fonksiyonlarını kullanır:
 *   - agent()       → Claude Code'un built-in LLM çağrısı
 *   - parallel()    → Claude Code'un built-in paralel çalıştırma
 *   - pipeline()    → Claude Code'un built-in sıralı çalıştırma
 *   - WebSearch     → Claude Code'un built-in web arama
 *   - WebFetch      → Claude Code'un built-in URL fetch
 *   - phase()       → Claude Code'un built-in progress göstergesi
 *   - log()         → Claude Code'un built-in logging
 * 
 * Bu Python harness.py'den ÇOK DAHA HIZLIDIR çünkü:
 *   1. agent() direk Claude API'sini kullanır (curl yok)
 *   2. parallel() gerçek paralel çalıştırır (threading yok)
 *   3. WebSearch/WebFetch built-in tool'lar (requests yok)
 * 
 * Kullanım:
 *   Claude Code'da: Skill(deep-research)
 *   veya: Workflow({name: 'deep-research', args: 'soru'})
 *   veya: node claude-code-workflow.js "soru"
 * 
 * Kurulum:
 *   cp claude-code-workflow.js ~/.claude/workflows/scripts/deep-research.js
 *   → Skill(deep-research) ile çağrılabilir
 */

export const meta = {
  name: 'deep-research',
  description: 'Deep research harness — fan-out web searches, fetch sources, adversarially verify claims, synthesize a cited report. Uses Claude Code built-in functions.',
  whenToUse: 'When the user wants a deep, multi-source, fact-checked research report on any topic.',
  phases: [
    {title: 'Scope', detail: 'Decompose question into 5 search angles'},
    {title: 'Search', detail: '5 parallel WebSearch agents, one per angle'},
    {title: 'Fetch', detail: 'URL-dedup, fetch top 15 sources, extract falsifiable claims'},
    {title: 'Verify', detail: '2-vote adversarial verification per claim'},
    {title: 'Synthesize', detail: 'Merge semantic dupes, rank by confidence, cite sources'},
  ],
};

// ─── Constants ───
const VOTES_PER_CLAIM = 2;
const REFUTATIONS_REQUIRED = 2;
const MAX_FETCH = 15;
const MAX_VERIFY_CLAIMS = 12;

// ─── Schema ───
const SCOPE_SCHEMA = {
  type: 'object', required: ['question', 'angles', 'summary'],
  properties: {
    question: { type: 'string' },
    summary: { type: 'string' },
    angles: { type: 'array', minItems: 3, maxItems: 6, items: {
      type: 'object', required: ['label', 'query'],
      properties: { label: { type: 'string' }, query: { type: 'string' }, rationale: { type: 'string' } },
    }},
  },
};

const SEARCH_SCHEMA = {
  type: 'object', required: ['results'],
  properties: {
    results: { type: 'array', maxItems: 6, items: {
      type: 'object', required: ['url', 'title', 'relevance'],
      properties: { url: { type: 'string' }, title: { type: 'string' }, snippet: { type: 'string' }, relevance: { enum: ['high', 'medium', 'low'] } },
    }},
  },
};

const EXTRACT_SCHEMA = {
  type: 'object', required: ['claims', 'sourceQuality'],
  properties: {
    sourceQuality: { enum: ['primary', 'secondary', 'blog', 'forum', 'unreliable'] },
    publishDate: { type: 'string' },
    claims: { type: 'array', maxItems: 5, items: {
      type: 'object', required: ['claim', 'quote', 'importance'],
      properties: { claim: { type: 'string' }, quote: { type: 'string' }, importance: { enum: ['central', 'supporting', 'tangential'] } },
    }},
  },
};

const VERDICT_SCHEMA = {
  type: 'object', required: ['refuted', 'evidence', 'confidence'],
  properties: { refuted: { type: 'boolean' }, evidence: { type: 'string' }, confidence: { enum: ['high', 'medium', 'low'] }, counterSource: { type: 'string' } },
};

const REPORT_SCHEMA = {
  type: 'object', required: ['summary', 'findings', 'caveats'],
  properties: {
    summary: { type: 'string' },
    findings: { type: 'array', items: {
      type: 'object', required: ['claim', 'confidence', 'sources', 'evidence'],
      properties: { claim: { type: 'string' }, confidence: { enum: ['high', 'medium', 'low'] }, sources: { type: 'array', items: { type: 'string' } }, evidence: { type: 'string' }, vote: { type: 'string' } },
    }},
    caveats: { type: 'string' },
    openQuestions: { type: 'array', items: { type: 'string' } },
  },
};

// ─── Helpers ───
const normURL = u => {
  const m = String(u).match(/^[a-z][a-z0-9+.-]*:\/\/(?:[^/?#\\]*@)?(?:www\.)?([^/:?#@\\]+)(?::\d+)?([^?#]*)/i);
  return m ? (m[1] + m[2].replace(/\/$/, '')).toLowerCase() : String(u).toLowerCase();
};

const relRank = { high: 0, medium: 1, low: 2 };
const impRank = { central: 0, supporting: 1, tangential: 2 };
const qualRank = { primary: 0, secondary: 1, blog: 2, forum: 3, unreliable: 4 };

// ─── Prompts ───
const SCOPE_PROMPT = (q) =>
  `Decompose this research question into complementary search angles.\n\n## Question\n${q}\n\n## Task\nGenerate 5 distinct web search queries that together cover the question from different angles. Make queries specific, avoid redundancy.\n\nStructured output only.`;

const SEARCH_PROMPT = (angle, question) =>
  `## Web Searcher: ${angle.label}\n\nResearch question: "${question}"\nYour angle: ${angle.label} — ${angle.rationale || ''}\nQuery: ${angle.query}\n\nReturn the top 4-6 most relevant results. Rank by relevance to the ORIGINAL question. Skip SEO spam.\n\nStructured output only.`;

const FETCH_PROMPT = (source, question, angle) =>
  `## Source Extractor\n\nResearch question: "${question}"\nURL: ${source.url}\nTitle: ${source.title}\nFound via: ${angle}\n\nFetch and extract 2-5 FALSIFIABLE claims with quotes. Rate source quality: primary/secondary/blog/forum/unreliable.\n\nStructured output only.`;

const VERIFY_PROMPT = (claim, question, v, total) =>
  `## Adversarial Verifier (voter ${v+1}/${total})\n\nBe SKEPTICAL. Try to REFUTE this claim.\n\nResearch question: ${question}\nClaim: "${claim.claim}"\nSource: ${claim.sourceUrl} (${claim.sourceQuality})\nQuote: "${claim.quote}"\n\nRefute if: unsupported/contradicted/low-quality source/outdated. Default to refuted=true.\n\nStructured output only.`;

// ─── Main Pipeline ───
export async function deepResearch(question) {
  if (!question || !question.trim()) return { error: 'No research question provided.' };

  log(`Deep research: ${question.slice(0, 100)}...`);

  // ─── Phase 1: Scope ───
  phase('Scope');
  const scope = await agent(SCOPE_PROMPT(question), { label: 'scope', schema: SCOPE_SCHEMA });
  if (!scope) return { error: 'Scope agent returned no result.', question };

  const angles = scope.angles || [];
  log(`Decomposed into ${angles.length} angles: ${angles.map(a => a.label).join(', ')}`);

  // ─── Phase 2: Search ───
  phase('Search');
  const seen = new Map();
  const allSources = [];
  let fetchSlots = MAX_FETCH;

  const searchResults = await pipeline(angles, async (angle) => {
    const r = await agent(SEARCH_PROMPT(angle, question), { label: `search:${angle.label}`, phase: 'Search', schema: SEARCH_SCHEMA });
    if (!r) return null;

    const sorted = [...r.results].sort((a, b) => relRank[a.relevance] - relRank[b.relevance]);
    const novel = sorted.filter(s => {
      const key = normURL(s.url);
      if (seen.has(key)) return false;
      if (fetchSlots <= 0 && relRank[s.relevance] >= 1) return false;
      seen.set(key, { angle: angle.label, title: s.title });
      fetchSlots--;
      return true;
    });

    log(`${angle.label}: ${novel.length} novel results`);
    return novel.map(s => ({ ...s, angle: angle.label }));
  });

  const flatSources = searchResults.flat().filter(Boolean);
  log(`Search complete: ${flatSources.length} unique sources`);

  // ─── Phase 3: Fetch ───
  phase('Fetch');
  const fetchedSources = await pipeline(flatSources, async (source) => {
    const ext = await agent(FETCH_PROMPT(source, question, source.angle), {
      label: `fetch:${source.title?.slice(0, 30) || source.url.slice(0, 30)}`,
      phase: 'Fetch',
      schema: EXTRACT_SCHEMA,
    });
    if (!ext) return { url: source.url, title: source.title, angle: source.angle, sourceQuality: 'unreliable', claims: [] };

    return {
      url: source.url, title: source.title, angle: source.angle,
      sourceQuality: ext.sourceQuality, publishDate: ext.publishDate,
      claims: ext.claims.map(c => ({ ...c, sourceUrl: source.url, sourceQuality: ext.sourceQuality })),
    };
  });

  const allClaims = fetchedSources.flatMap(s => s.claims);
  const rankedClaims = [...allClaims]
    .sort((a, b) => (impRank[a.importance] - impRank[b.importance]) || (qualRank[a.sourceQuality] - qualRank[b.sourceQuality]))
    .slice(0, MAX_VERIFY_CLAIMS);

  log(`Fetched ${fetchedSources.length} sources → ${allClaims.length} claims → verifying top ${rankedClaims.length}`);

  if (rankedClaims.length === 0) {
    return { question, summary: 'No claims extracted.', findings: [], refuted: [], unverified: [],
      sources: fetchedSources.map(s => ({ url: s.url, quality: s.sourceQuality })) };
  }

  // ─── Phase 4: Verify (PARALEL — Claude Code's parallel() kullanır) ───
  phase('Verify');
  const voted = await parallel(rankedClaims.map(claim => async () => {
    const verdicts = await parallel(Array.from({ length: VOTES_PER_CLAIM }, (_, v) => async () =>
      agent(VERIFY_PROMPT(claim, question, v, VOTES_PER_CLAIM), {
        label: `v${v}:${claim.claim.slice(0, 40)}`, phase: 'Verify', schema: VERDICT_SCHEMA,
      })
    ));

    const valid = verdicts.filter(Boolean);
    const refutedCount = valid.filter(v => v.refuted).length;
    const survives = valid.length >= REFUTATIONS_REQUIRED && refutedCount < REFUTATIONS_REQUIRED;
    const isRefuted = refutedCount >= REFUTATIONS_REQUIRED;
    const mark = survives ? '✓' : isRefuted ? '✗' : '?';
    log(`"${claim.claim.slice(0, 50)}…": ${valid.length - refutedCount}-${refutedCount} ${mark}`);

    return { ...claim, verdicts: valid, survives, isRefuted };
  }));

  const confirmed = voted.filter(c => c.survives);
  const killed = voted.filter(c => c.isRefuted);
  const unverified = voted.filter(c => !c.survives && !c.isRefuted);
  log(`Verify done: ${confirmed.length} confirmed, ${killed.length} refuted, ${unverified.length} unverified`);

  // ─── Phase 5: Synthesize ───
  phase('Synthesize');

  if (confirmed.length === 0) {
    return { question, summary: `All ${killed.length} claims refuted.`, findings: [],
      refuted: killed.map(c => ({ claim: c.claim, source: c.sourceUrl })), unverified: unverified.map(c => ({ claim: c.claim })) };
  }

  const block = confirmed.map((c, i) =>
    `### [${i}] ${c.claim}\nVote: ${c.verdicts.filter(v => !v.refuted).length}-${c.verdicts.filter(v => v.refuted).length} · Source: ${c.sourceUrl}\nQuote: "${c.quote}"`
  ).join('\n');

  const report = await agent(
    `## Synthesis\n\n**Question:** ${question}\n\n${confirmed.length} claims survived.\n\n## Confirmed claims\n${block}\n\nMerge duplicates, group into findings, assign confidence, write summary.\n\nStructured output only.`,
    { label: 'synthesize', phase: 'Synthesize', schema: REPORT_SCHEMA }
  );

  return {
    question, ...report,
    refuted: killed.map(c => ({ claim: c.claim, source: c.sourceUrl })),
    unverified: unverified.map(c => ({ claim: c.claim })),
    sources: fetchedSources.map(s => ({ url: s.url, quality: s.sourceQuality, claimCount: s.claims.length })),
    stats: {
      angles: angles.length, sources: fetchedSources.length, claims: allClaims.length,
      verified: voted.length, confirmed: confirmed.length, killed: killed.length, unverified: unverified.length,
      afterSynthesis: report?.findings?.length || 0,
    },
  };
}

// ─── CLI entry point ───
const question = process.argv[2];
if (question) {
  deepResearch(question).then(result => {
    console.log(JSON.stringify(result, null, 2));
  }).catch(err => {
    console.error('Error:', err);
    process.exit(1);
  });
}
