import type { ReactElement } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { apiUrl } from '../api/base'
import { api } from '../api/client'
import type { ClaimVerification, Verdict } from '../api/types'
import { PageHeader } from '../components/ui/PageHeader'
import { Button } from '../components/ui/Button'
import { Skeleton } from '../components/ui/Skeleton'

const VERDICT_META: Record<
  Verdict,
  { label: string; icon: string; text: string; bg: string; border: string; borderL: string }
> = {
  true: {
    label: 'True', icon: '✓',
    text: 'text-emerald-400', bg: 'bg-emerald-950', border: 'border-emerald-800', borderL: 'border-l-emerald-500',
  },
  false: {
    label: 'False', icon: '✗',
    text: 'text-red-400', bg: 'bg-red-950', border: 'border-red-800', borderL: 'border-l-red-500',
  },
  misleading: {
    label: 'Misleading', icon: '⚠',
    text: 'text-orange-400', bg: 'bg-orange-950', border: 'border-orange-800', borderL: 'border-l-orange-500',
  },
  'partially true': {
    label: 'Partially True', icon: '◐',
    text: 'text-yellow-400', bg: 'bg-yellow-950', border: 'border-yellow-800', borderL: 'border-l-yellow-500',
  },
  unverifiable: {
    label: 'Unverifiable', icon: '?',
    text: 'text-neutral-400', bg: 'bg-neutral-800', border: 'border-neutral-700', borderL: 'border-l-neutral-500',
  },
}

const VERDICT_ORDER: Verdict[] = ['true', 'false', 'misleading', 'partially true', 'unverifiable']

const STATUS_LABEL: Record<string, string> = {
  downloading: 'Downloading clip…',
  transcribing: 'Transcribing audio…',
  extracting_claims: 'Reading through the manuscript for claims…',
  verifying_claims: 'Fact-checking claims…',
  concluding: 'Writing overall conclusion…',
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function paragraphsOf(text: string): string[] {
  return text
    .split(/\n+/)
    .map((p) => p.trim())
    .filter(Boolean)
}

const MARKDOWN_LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g

// The fact-check models cite sources as inline markdown links within the
// analysis prose; rendering it as plain text left literal "[text](url)"
// clutter on the page, so this turns those into real clickable links.
function renderWithLinks(text: string): (string | ReactElement)[] {
  const parts: (string | ReactElement)[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  MARKDOWN_LINK_RE.lastIndex = 0
  while ((match = MARKDOWN_LINK_RE.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index))
    parts.push(
      <a
        key={match.index}
        href={match[2]}
        target="_blank"
        rel="noreferrer"
        className="text-neutral-300 underline decoration-neutral-600 underline-offset-2 hover:text-white"
      >
        {match[1]}
      </a>,
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex))
  return parts
}

function ConclusionSection({ conclusion }: { conclusion: string }) {
  return (
    <div className="mb-6 animate-slide-up border-2 border-neutral-700 bg-neutral-950/90 p-5 shadow-[6px_6px_0_0_#000]">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-lg">🔎</span>
        <h2 className="font-display text-lg uppercase tracking-widest text-neutral-200">Conclusion</h2>
      </div>
      <p className="text-[16px] leading-relaxed text-neutral-100">{renderWithLinks(conclusion)}</p>
    </div>
  )
}

function VerdictSummaryBar({ claims }: { claims: ClaimVerification[] }) {
  const counts: Partial<Record<Verdict, number>> = {}
  for (const c of claims) counts[c.verdict] = (counts[c.verdict] ?? 0) + 1

  return (
    <div className="mb-6 flex flex-wrap items-center gap-2 animate-slide-up">
      <span className="font-mono text-sm text-neutral-500">
        {claims.length} claim{claims.length === 1 ? '' : 's'} checked:
      </span>
      {VERDICT_ORDER.filter((v) => counts[v]).map((v) => {
        const meta = VERDICT_META[v]
        return (
          <span
            key={v}
            className={`inline-flex items-center gap-1.5 border-2 bg-black px-3 py-1 font-mono text-sm font-bold ${meta.border} ${meta.text}`}
          >
            <span>{meta.icon}</span>
            {counts[v]} {meta.label}
          </span>
        )
      })}
    </div>
  )
}

function ClaimCard({ claim, index, checkId }: { claim: ClaimVerification; index: number; checkId: string }) {
  const verdict = VERDICT_META[claim.verdict] ?? VERDICT_META.unverifiable

  return (
    <div
      style={{ animationDelay: `${Math.min(index, 10) * 40}ms` }}
      className={`animate-slide-up border-2 border-neutral-800 border-l-[6px] ${verdict.borderL} bg-neutral-950/90 p-5 shadow-[4px_4px_0_0_#000] transition-shadow hover:shadow-[6px_6px_0_0_#000]`}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 shrink-0 border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 font-mono text-xs font-semibold text-neutral-500">
            #{index + 1}
          </span>
          <h3 className="text-base font-semibold leading-snug text-neutral-100">{claim.claim}</h3>
        </div>
        <span
          className={`flex shrink-0 items-center gap-1.5 border-2 bg-black px-3 py-1 font-mono text-sm font-bold ${verdict.border} ${verdict.text}`}
        >
          <span>{verdict.icon}</span>
          {verdict.label}
        </span>
      </div>

      <div className="relative mb-4 border-2 border-neutral-800 bg-black py-3 pl-9 pr-4">
        <span className="absolute left-2.5 top-0.5 select-none font-serif text-4xl leading-none text-neutral-700">
          &ldquo;
        </span>
        <p className="text-[15px] italic leading-relaxed text-neutral-300">{claim.quote}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {claim.timestamp && (
            <span className="inline-block border border-neutral-800 bg-neutral-900 px-2 py-0.5 font-mono text-xs text-neutral-500">
              {claim.timestamp}
            </span>
          )}
          <a
            href={apiUrl(`/api/verify/${checkId}/claims/${index}/clip`)}
            download
            className="inline-flex items-center gap-1 border border-neutral-700 bg-neutral-900 px-2 py-0.5 font-mono text-xs text-neutral-400 transition hover:border-brand-500 hover:text-brand-300"
          >
            ⬇ Download exact clip
          </a>
        </div>
      </div>

      {!claim.grounded && (
        <div className="hazard-stripes mb-3 flex items-start gap-2 border-2 border-black px-3 py-2 text-xs font-bold text-black">
          <span>⚠</span>
          <span>Not web-verified — the live fact-check search was unavailable when this claim was checked.</span>
        </div>
      )}

      <div className="mb-2 flex items-center gap-3">
        <span className="font-display text-sm uppercase tracking-widest text-neutral-600">
          Fact-check analysis
        </span>
        <span className="h-px flex-1 bg-neutral-800" />
      </div>
      <div className="space-y-2.5">
        {paragraphsOf(claim.analysis).map((p, i) => (
          <p key={i} className="text-[15px] leading-relaxed text-neutral-300">
            {renderWithLinks(p)}
          </p>
        ))}
      </div>

      {claim.sources.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t-2 border-neutral-800 pt-3">
          <span className="mr-1 font-display text-sm uppercase tracking-widest text-neutral-600">Sources</span>
          {claim.sources.map((src, i) =>
            src.startsWith('http') ? (
              <a
                key={i}
                href={src}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 border border-neutral-800 bg-black px-2.5 py-1 font-mono text-xs text-neutral-400 transition hover:border-brand-600 hover:text-brand-300"
              >
                <span className="text-neutral-600">🔗</span>
                {domainOf(src)}
              </a>
            ) : (
              <span
                key={i}
                className="border border-neutral-800 bg-black px-2.5 py-1 font-mono text-xs text-neutral-500"
              >
                {src}
              </span>
            ),
          )}
        </div>
      )}
    </div>
  )
}

function DebunkScriptSection({ checkId }: { checkId: string }) {
  const createScript = useMutation({
    mutationFn: () => api.createDebunkScript(checkId),
  })

  const { data: script } = useQuery({
    queryKey: ['debunk-script', checkId, createScript.data?.id],
    queryFn: () => api.getDebunkScript(checkId, createScript.data!.id),
    enabled: !!createScript.data,
    refetchInterval: (query) => (query.state.data?.status === 'generating' ? 1500 : false),
  })

  return (
    <div className="mt-8 animate-slide-up border-2 border-neutral-700 bg-neutral-950/90 p-5 shadow-[6px_6px_0_0_#000]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-display text-lg uppercase tracking-widest text-neutral-200">
          🎭 Debunk Reel Script
        </h2>
        <Button
          size="sm"
          disabled={createScript.isPending || script?.status === 'generating'}
          onClick={() => createScript.mutate()}
        >
          {script?.status === 'generating'
            ? 'Writing…'
            : script?.status === 'done'
              ? 'Regenerate'
              : 'Generate Script'}
        </Button>
      </div>

      <p className="mb-3 font-mono text-xs text-neutral-600">
        For each claim: play the original clip, then cut to your own reaction fact-checking it —
        humor cues marked separately from the facts, so verdicts stay accurate while the delivery
        stays fun. Download as a PDF to shoot from.
      </p>

      {createScript.isError && (
        <p className="font-mono text-sm text-brand-400">
          Failed to start: {(createScript.error as Error).message}
        </p>
      )}
      {script?.status === 'error' && (
        <p className="font-mono text-sm text-brand-400">Failed: {script.error_message}</p>
      )}

      {script?.status === 'done' && (
        <div className="animate-slide-up space-y-4">
          <div className="flex items-center justify-between gap-3 border-b-2 border-neutral-800 pb-3">
            <div>
              <h3 className="text-lg font-bold text-neutral-100">{script.title}</h3>
              <p className="mt-1 font-mono text-sm italic text-brand-300">
                &ldquo;{script.intro_hook}&rdquo;
              </p>
            </div>
            <a
              href={apiUrl(`/api/verify/${checkId}/debunk-script/${script.id}/pdf`)}
              download="debunk_reel_script.pdf"
              className="shrink-0 border-2 border-emerald-600 bg-black px-3 py-1.5 font-mono text-xs uppercase text-emerald-400 shadow-[3px_3px_0_0_#000] transition hover:bg-emerald-950"
            >
              ⬇ Download PDF
            </a>
          </div>

          <div className="space-y-4">
            {script.beats.map((beat) => {
              const verdict = VERDICT_META[beat.verdict] ?? VERDICT_META.unverifiable
              return (
                <div key={beat.claim_index} className="space-y-2">
                  <div className="border-2 border-neutral-700 bg-neutral-900 p-3">
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-semibold uppercase tracking-widest text-neutral-500">
                        Original clip — Claim {beat.claim_index + 1}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 border bg-black px-2 py-0.5 font-mono text-xs font-bold ${verdict.border} ${verdict.text}`}
                      >
                        <span>{verdict.icon}</span>
                        {verdict.label}
                      </span>
                    </div>
                    <p className="mb-2 text-sm italic leading-relaxed text-neutral-300">
                      &ldquo;{beat.claim_quote}&rdquo;
                    </p>
                    <a
                      href={apiUrl(`/api/verify/${checkId}/claims/${beat.claim_index}/clip`)}
                      download
                      className="inline-flex items-center gap-1 border border-neutral-700 bg-black px-2 py-0.5 font-mono text-xs text-neutral-400 transition hover:border-brand-500 hover:text-brand-300"
                    >
                      ⬇ Download this clip
                    </a>
                  </div>

                  <div className="border-2 border-neutral-800 bg-black p-3">
                    <span className="mb-1.5 inline-block border border-brand-800 bg-neutral-900 px-1.5 py-0.5 font-mono text-xs font-semibold text-brand-400">
                      YOUR REACTION VIDEO
                    </span>
                    <p className="text-sm leading-relaxed text-neutral-200">
                      {beat.reaction_narration}
                    </p>
                    {beat.humor_cue && (
                      <p className="mt-2 border-l-4 border-yellow-600 bg-yellow-950/30 py-1 pl-2 text-sm text-yellow-400">
                        😂 HUMOR CUE: {beat.humor_cue}
                      </p>
                    )}
                    {beat.question_cue && (
                      <p className="mt-2 border-l-4 border-sky-600 bg-sky-950/30 py-1 pl-2 text-sm text-sky-400">
                        ❓ ASK THE AUDIENCE: {beat.question_cue}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          <p className="border-t-2 border-neutral-800 pt-3 font-semibold text-emerald-400">
            {script.outro_cta}
          </p>
        </div>
      )}
    </div>
  )
}

export function VerifyResultPage() {
  const { checkId } = useParams<{ checkId: string }>()
  const navigate = useNavigate()
  if (!checkId) return null

  const { data: check } = useQuery({
    queryKey: ['reel-check', checkId],
    queryFn: () => api.getReelCheck(checkId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'error' ? false : 1500
    },
  })

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <PageHeader
        backTo="/verify"
        backLabel="All checks"
        title={check?.url ?? <Skeleton className="h-6 w-64" />}
        subtitle={check && `Submitted ${check.created_at}`}
        actions={
          check &&
          check.claims.length > 0 && (
            <Button size="sm" onClick={() => navigate(`/verify/${checkId}/editor`)}>
              🎬 Open Editor
            </Button>
          )
        }
      />

      {check && check.status !== 'done' && check.status !== 'error' && (
        <div className="mb-6 flex animate-slide-up items-center gap-3 border-2 border-neutral-800 bg-neutral-950/90 p-4 shadow-[4px_4px_0_0_#000]">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-500 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-brand-500" />
          </span>
          <p className="font-mono text-sm text-neutral-300">
            {STATUS_LABEL[check.status] ?? check.status}
            {check.progress && <span className="text-neutral-500"> ({check.progress})</span>}
          </p>
        </div>
      )}

      {!check && (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-none" />
          <Skeleton className="h-40 w-full rounded-none" />
        </div>
      )}

      {check?.status === 'error' && (
        <div className="hazard-stripes mb-6 animate-slide-up border-2 border-black p-4 text-sm font-bold text-black">
          Failed: {check.error_message}
        </div>
      )}

      {check?.conclusion && <ConclusionSection conclusion={check.conclusion} />}

      {check?.manuscript && (
        <details className="mb-6 border-2 border-neutral-800 bg-black p-3">
          <summary className="cursor-pointer font-display text-sm uppercase tracking-widest text-neutral-500">
            Manuscript
          </summary>
          <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap font-mono text-sm text-neutral-400">
            {check.manuscript}
          </pre>
        </details>
      )}

      {check && check.claims.length > 0 && (
        <div>
          <VerdictSummaryBar claims={check.claims} />
          <div className="space-y-4">
            {check.claims.map((claim, i) => (
              <ClaimCard key={i} claim={claim} index={i} checkId={check.id} />
            ))}
          </div>
        </div>
      )}

      {check?.status === 'done' && check.claims.length === 0 && (
        <p className="text-neutral-600">No checkable factual claims were found in this clip.</p>
      )}

      {check?.status === 'done' && check.claims.length > 0 && (
        <DebunkScriptSection checkId={check.id} />
      )}
    </div>
  )
}
