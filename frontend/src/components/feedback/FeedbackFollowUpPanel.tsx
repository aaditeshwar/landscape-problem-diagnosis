import type { FollowUpExchange, FollowUpMcqChoice } from '../../types'

function normalize(value: string): string {
  return value.trim().toLowerCase()
}

function isSelectedChoice(choice: FollowUpMcqChoice, answer: string): boolean {
  const normalizedAnswer = normalize(answer)
  return (
    normalize(choice.id) === normalizedAnswer ||
    normalize(choice.label) === normalizedAnswer ||
    normalizedAnswer.includes(normalize(choice.label)) ||
    normalize(choice.label).includes(normalizedAnswer)
  )
}

function FollowUpCard({ entry, index }: { entry: FollowUpExchange; index: number }) {
  const choices = entry.mcq?.choices ?? []
  const hasMcq = choices.length > 0

  return (
    <article className="flex h-full flex-col rounded-lg border border-stone-200 bg-stone-50/70 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-stone-500">Q{index + 1}</div>
      <p className="mt-1 text-sm font-medium leading-snug text-stone-800">{entry.question}</p>
      {hasMcq ? (
        <ul className="mt-2 space-y-1">
          {choices.map((choice) => {
            const selected = isSelectedChoice(choice, entry.answer)
            return (
              <li
                key={choice.id}
                className={`rounded px-2 py-1 text-xs ${
                  selected
                    ? 'border border-emerald-200 bg-emerald-50 font-medium text-emerald-900'
                    : 'text-stone-600'
                }`}
              >
                {choice.label}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-stone-700">{entry.answer || '—'}</p>
      )}
    </article>
  )
}

interface Props {
  history: FollowUpExchange[]
}

export function FeedbackFollowUpPanel({ history }: Props) {
  return (
    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-stone-800">Follow-up responses</h2>
      <p className="mt-1 text-xs leading-relaxed text-stone-500">
        These answers add local context beyond the landscape charts above. Review the diagnosis below in light of
        this additional information.
      </p>
      {history.length === 0 ? (
        <p className="mt-2 text-sm text-stone-500">No follow-up questions were asked for this diagnosis snapshot.</p>
      ) : (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {history.map((entry, index) => (
            <FollowUpCard key={`${index}-${entry.question.slice(0, 24)}`} entry={entry} index={index} />
          ))}
        </div>
      )}
    </section>
  )
}
