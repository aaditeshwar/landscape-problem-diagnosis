import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchFeedbackContext, fetchSavedFeedback, saveFeedback } from '../api/feedback'
import { FeedbackComparisonGrid } from '../components/feedback/FeedbackComparisonGrid'
import { FeedbackFollowUpPanel } from '../components/feedback/FeedbackFollowUpPanel'
import { FeedbackReferencePanel } from '../components/feedback/FeedbackReferencePanel'
import { FeedbackSavePanel } from '../components/feedback/FeedbackSavePanel'
import type { FeedbackContext, FeedbackDocument, FeedbackSectionDraft } from '../types'
import { focusParamToDomId, mergeSectionDraft } from '../utils/feedbackSections'

export function FeedbackPage() {
  const [params] = useSearchParams()
  const snapshotId = params.get('snapshot_id')
  const focus = params.get('focus')
  const pathwayId = params.get('pathway_id')

  const returnUrl = useMemo(() => {
    const query = params.toString()
    return query ? `/feedback?${query}` : '/feedback'
  }, [params])

  const [context, setContext] = useState<FeedbackContext | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [sections, setSections] = useState<Record<string, FeedbackSectionDraft>>({})
  const sectionsRef = useRef(sections)
  sectionsRef.current = sections

  const [savedDoc, setSavedDoc] = useState<FeedbackDocument | null>(null)
  const [loadedEmail, setLoadedEmail] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!snapshotId) {
      setContext(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchFeedbackContext(snapshotId)
      .then((data) => {
        if (!cancelled) setContext(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Failed to load feedback context')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [snapshotId])

  const loadSaved = useCallback(
    async (emailToLoad: string, replaceDraft = true) => {
      if (!snapshotId || !emailToLoad.trim()) return
      setLoadError(null)
      try {
        const doc = await fetchSavedFeedback(snapshotId, emailToLoad.trim())
        setSavedDoc(doc)
        setLoadedEmail(emailToLoad.trim().toLowerCase())
        setName(doc.reviewer.name)
        setEmail(doc.reviewer.email)
        if (replaceDraft) {
          setSections(doc.sections ?? {})
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load saved feedback'
        if (message.includes('404') || message.toLowerCase().includes('no saved feedback')) {
          setSavedDoc(null)
          setLoadedEmail(emailToLoad.trim().toLowerCase())
          return
        }
        setLoadError(message)
      }
    },
    [snapshotId],
  )

  useEffect(() => {
    const normalized = email.trim().toLowerCase()
    if (!normalized || !snapshotId || normalized === loadedEmail) return
    const timer = window.setTimeout(() => {
      void loadSaved(normalized)
    }, 400)
    return () => window.clearTimeout(timer)
  }, [email, loadedEmail, loadSaved, snapshotId])

  useEffect(() => {
    if (!focus || !context) return
    const targetId = focusParamToDomId(focus, pathwayId)
    if (!targetId) return
    const node = document.getElementById(targetId)
    node?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [context, focus, pathwayId])

  function handleSectionChange(sectionKey: string, patch: Partial<FeedbackSectionDraft>) {
    setSections((prev) => mergeSectionDraft(prev, sectionKey, patch))
  }

  async function handleSave() {
    if (!snapshotId || !context) return
    const draftSections = sectionsRef.current
    setSaving(true)
    setSaveError(null)
    try {
      const doc = await saveFeedback(snapshotId, {
        reviewer: { name: name.trim(), email: email.trim() },
        sections: draftSections,
        session_id: context.session_id,
        follow_up_count: context.follow_up_count,
        turn_no: context.turn_no,
        log_index: context.log_index,
        mws_uid: context.mws_uid,
      })
      setSavedDoc(doc)
      setLoadedEmail(email.trim().toLowerCase())
      setSections(doc.sections ?? draftSections)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-full bg-[#faf7f2] p-6 text-stone-800">
      <header className="mb-6 border-b border-stone-300 pb-4">
        <h1 className="text-xl font-semibold">Diagnosis feedback</h1>
        <p className="mt-1 text-sm text-stone-600">
          Review context, record agreement with server and LLM outputs, and save your notes.
        </p>
      </header>

      {!snapshotId ? (
        <p className="text-sm text-stone-600">Open this page from a diagnosis “Give feedback” button.</p>
      ) : loading ? (
        <p className="text-sm text-stone-500">Loading diagnosis context…</p>
      ) : error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      ) : context ? (
        <div className="space-y-4">
          <p className="text-xs text-stone-500">
            Snapshot <code className="rounded bg-stone-200 px-1">{context.diagnosis_snapshot_id}</code>
            {context.follow_up_count > 0 ? ` · after ${context.follow_up_count} follow-up(s)` : ' · initial diagnosis'}
            {context.want_llm_opinion && !context.llm_skipped ? ' · LLM enabled' : ' · server-only diagnosis'}
          </p>

          <FeedbackReferencePanel mws={context.mws_doc} />
          <FeedbackFollowUpPanel history={context.follow_up_history} />

          <FeedbackComparisonGrid
            context={context}
            snapshotId={snapshotId}
            returnUrl={returnUrl}
            sections={sections}
            onSectionChange={handleSectionChange}
          />

          <FeedbackSavePanel
            name={name}
            email={email}
            onNameChange={setName}
            onEmailChange={setEmail}
            onSave={handleSave}
            saving={saving}
            saveError={saveError}
            lastSavedAt={savedDoc?.updated_at ?? null}
            loadError={loadError}
          />
        </div>
      ) : null}
    </div>
  )
}
