'use client'

interface SuggestedQuestionsProps {
  onSelect: (question: string) => void
}

const SUGGESTED_QUESTIONS = [
  {
    category: '📊 Financial',
    questions: [
      'What is the bear case revenue forecast for FY2026?',
      'Which client had the highest revenue growth in FY2025?',
      'What is the EBITDA margin for FY2025?',
      'Show quarterly revenue for FY2025 as a bar chart',
    ],
  },
  {
    category: '🎯 Strategic',
    questions: [
      'What are the strategic initiatives for FY2026?',
      'What products does ACL Digital have in the pipeline?',
      'Summarize the ACL Digital Annual Report 2025',
      'What are the key highlights from the Investor Presentation?',
    ],
  },
  {
    category: '👥 Meetings',
    questions: [
      'What was discussed in the Jan 13 2026 weekly sync meeting?',
      'What action items came out of the Jan 13 2026 meeting?',
      'What are the recurring topics in the weekly sync meetings?',
      'Who attended the weekly sync meetings?',
    ],
  },
]

export function SuggestedQuestions({ onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="flex flex-col gap-4 px-4 py-6 flex-1 justify-center">
      <div className="text-center mb-2">
        <h3 className="text-sm font-semibold text-slate-700">Try asking something</h3>
        <p className="text-xs text-slate-400 mt-1">
          Select a question below or type your own
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {SUGGESTED_QUESTIONS.map((group) => (
          <div key={group.category}>
            <p className="text-xs font-semibold text-slate-400 mb-1.5 px-1">
              {group.category}
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {group.questions.map((q) => (
                <button
                  key={q}
                  onClick={() => onSelect(q)}
                  className="text-left text-xs text-slate-600 bg-white border border-slate-200 rounded-xl px-3 py-2.5 hover:border-slate-400 hover:bg-slate-50 hover:text-slate-800 transition-all cursor-pointer leading-relaxed"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
