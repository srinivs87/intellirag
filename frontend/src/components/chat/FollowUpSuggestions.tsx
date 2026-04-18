'use client'

interface FollowUpSuggestionsProps {
  suggestions: string[]
  onSelect: (suggestion: string) => void
}

export function FollowUpSuggestions({ suggestions, onSelect }: FollowUpSuggestionsProps) {
  if (!suggestions.length) return null

  return (
    <div className="px-3 pt-1 pb-2 shrink-0">
      <p className="text-xs text-slate-400 mb-1.5">Suggested follow-ups:</p>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map((s, i) => (
          <button
            key={i}
            onClick={() => onSelect(s)}
            className="text-xs px-3 py-1.5 rounded-full border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:border-slate-300 transition-all text-left"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
