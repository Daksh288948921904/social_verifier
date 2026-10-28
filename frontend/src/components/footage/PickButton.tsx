import type { FootagePick } from '../../api/types'

export function PickButton({
  pick,
  onPush,
  onRemove,
  compact,
  audioChoice,
}: {
  pick: FootagePick | undefined
  onPush: (clipAudio: boolean) => void
  onRemove: (pick: FootagePick) => void
  compact?: boolean
  /** Push with the clip's own sound, or muted -- two buttons instead of one. */
  audioChoice?: boolean
}) {
  const base = `group inline-flex items-center gap-1.5 border-2 font-mono font-bold uppercase tracking-wider transition ${
    compact ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1.5 text-xs'
  }`
  const push = (clipAudio: boolean) => (e: React.MouseEvent) => {
    e.stopPropagation()
    onPush(clipAudio)
  }

  if (pick) {
    const sound = pick.clip_audio ? '🔊 with sound' : '🔇 muted'
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove(pick)
          }}
          title="This clip is in the edit plan's shortlist — click to take it out"
          className={`${base} border-brand-500 bg-brand-500 text-black hover:bg-black hover:text-brand-400`}
        >
          <span className="group-hover:hidden">✓ In plan{audioChoice && ` · ${sound}`}</span>
          <span className="hidden group-hover:inline">✕ Remove from plan</span>
        </button>
        {audioChoice && (
          <button
            type="button"
            onClick={push(!pick.clip_audio)}
            title="Change whether the clip's own audio is used in the edit"
            className={`${base} border-neutral-700 text-neutral-300 hover:border-neutral-400 hover:text-white`}
          >
            {pick.clip_audio ? '🔇 Switch to muted' : '🔊 Switch to clip sound'}
          </button>
        )}
      </span>
    )
  }
  if (audioChoice) {
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={push(true)}
          title="Add to the plan's shortlist, keeping the clip's original audio"
          className={`${base} border-brand-600 text-brand-400 hover:bg-brand-950`}
        >
          📌 Push with sound 🔊
        </button>
        <button
          type="button"
          onClick={push(false)}
          title="Add to the plan's shortlist with the clip muted — only the anchor is heard"
          className={`${base} border-brand-600 text-brand-400 hover:bg-brand-950`}
        >
          📌 Push muted 🔇
        </button>
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={push(false)}
      title="Add this clip to the shortlist the edit plan is built from"
      className={`${base} border-brand-600 text-brand-400 hover:bg-brand-950`}
    >
      📌 Push to plan
    </button>
  )
}
