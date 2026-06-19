import { AGREEMENT_OPTIONS, type AgreementValue } from '../../utils/feedbackSections'

interface Props {
  label: string
  name: string
  value?: AgreementValue | string | null
  onChange: (value: AgreementValue | null) => void
}

export function AgreementControl({ label, name, value, onChange }: Props) {
  return (
    <fieldset className="space-y-1">
      <legend className="text-xs font-medium text-stone-600">{label}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {AGREEMENT_OPTIONS.map((option) => (
          <label key={option.value} className="inline-flex items-center gap-1.5 text-sm text-stone-700">
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="border-stone-400 text-amber-700 focus:ring-amber-300"
            />
            {option.label}
          </label>
        ))}
        <label className="inline-flex items-center gap-1.5 text-sm text-stone-500">
          <input
            type="radio"
            name={name}
            checked={!value}
            onChange={() => onChange(null)}
            className="border-stone-400 text-amber-700 focus:ring-amber-300"
          />
          No rating
        </label>
      </div>
    </fieldset>
  )
}
