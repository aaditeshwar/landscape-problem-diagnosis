import { useState } from 'react'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

interface Props {
  name: string
  email: string
  onNameChange: (value: string) => void
  onEmailChange: (value: string) => void
  onSave: () => void
  saving: boolean
  saveError: string | null
  lastSavedAt: string | null
  loadError: string | null
  title?: string
  description?: string
  saveLabel?: string
}

export function FeedbackSavePanel({
  name,
  email,
  onNameChange,
  onEmailChange,
  onSave,
  saving,
  saveError,
  lastSavedAt,
  loadError,
  title = 'Save feedback',
  description = 'Your name and email identify your review. The latest draft for this snapshot is stored per email.',
  saveLabel = 'Save',
}: Props) {
  const [emailTouched, setEmailTouched] = useState(false)
  const emailValid = EMAIL_RE.test(email.trim())
  const canSave = name.trim().length > 0 && emailValid && !saving

  return (
    <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-stone-800">{title}</h2>
      <p className="mt-1 text-xs text-stone-500">{description}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-stone-700">Name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            className="rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
            placeholder="Your name"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-stone-700">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => {
              setEmailTouched(true)
              onEmailChange(e.target.value)
            }}
            className="rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
            placeholder="you@example.org"
          />
          {emailTouched && email.trim() && !emailValid ? (
            <span className="text-xs text-red-600">Enter a valid email address.</span>
          ) : null}
        </label>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={onSave}
          disabled={!canSave}
          className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-amber-800 disabled:cursor-not-allowed disabled:bg-stone-300"
        >
          {saving ? 'Saving…' : saveLabel}
        </button>
        {lastSavedAt ? (
          <span className="text-xs text-stone-500">Last saved at {new Date(lastSavedAt).toLocaleString()}</span>
        ) : null}
      </div>
      {loadError ? <p className="mt-2 text-sm text-amber-800">{loadError}</p> : null}
      {saveError ? <p className="mt-2 text-sm text-red-700">{saveError}</p> : null}
    </section>
  )
}
