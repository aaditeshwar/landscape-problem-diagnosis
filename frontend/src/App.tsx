import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchIngestedTehsils,
  fetchMws,
  fetchMwsBoundaries,
  fetchTehsils,
  fetchVillageBoundaries,
  locatePoint,
  runDiagnosisQuery,
  submitDiagnosisAnswer,
} from './api/client'
import { DiagnosisPanel } from './components/DiagnosisPanel'
import { InfoPanel } from './components/InfoPanel'
import { LocationSearch } from './components/LocationSearch'
import { MapView } from './components/MapView'
import type { DiagnosisResponse, FeatureCollection, FollowUpExchange, MwsDocument, MwsFeatureCollection, TehsilFeatureCollection, TehsilRef } from './types'
import {
  askedQuestionsFromHistory,
  askedVariablesFromHistory,
  resolveFollowUpTarget,
} from './utils/followUp'

function tehsilKey(ref: TehsilRef): string {
  return `${ref.state}__${ref.district}__${ref.tehsil}`
}

export default function App() {
  const [tehsils, setTehsils] = useState<TehsilFeatureCollection | null>(null)
  const [ingestedKeys, setIngestedKeys] = useState<Set<string>>(new Set())
  const [selectedTehsil, setSelectedTehsil] = useState<TehsilRef | null>(null)
  const [mwsBoundaries, setMwsBoundaries] = useState<MwsFeatureCollection | null>(null)
  const [villageBoundaries, setVillageBoundaries] = useState<FeatureCollection | null>(null)
  const [showVillages, setShowVillages] = useState(false)
  const [selectedMwsUid, setSelectedMwsUid] = useState<string | null>(null)
  const [mwsData, setMwsData] = useState<MwsDocument | null>(null)
  const [mwsLoading, setMwsLoading] = useState(false)
  const [mapError, setMapError] = useState<string | null>(null)
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lon: number; zoom?: number } | null>(null)

  const [problem, setProblem] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [diagnosis, setDiagnosis] = useState<DiagnosisResponse | null>(null)
  const [followUpHistory, setFollowUpHistory] = useState<FollowUpExchange[]>([])
  const [panelUpdates, setPanelUpdates] = useState<string[]>([])
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisError, setDiagnosisError] = useState<string | null>(null)
  const [followUpAnswer, setFollowUpAnswer] = useState('')

  const askedVariables = useMemo(() => askedVariablesFromHistory(followUpHistory), [followUpHistory])
  const askedQuestions = useMemo(() => askedQuestionsFromHistory(followUpHistory), [followUpHistory])
  const followUpTarget = useMemo(
    () => resolveFollowUpTarget(diagnosis, askedVariables, askedQuestions),
    [diagnosis, askedVariables, askedQuestions],
  )
  const tehsilLoadSeq = useRef(0)

  useEffect(() => {
    Promise.all([fetchTehsils(), fetchIngestedTehsils()])
      .then(([tehsilGeo, ingested]) => {
        setTehsils(tehsilGeo)
        setIngestedKeys(new Set(ingested.tehsils.map((t) => t.id)))
      })
      .catch((err) => setMapError(err instanceof Error ? err.message : 'Failed to load map'))
  }, [])

  const resetDiagnosisForNewMws = useCallback(() => {
    setDiagnosis(null)
    setFollowUpHistory([])
    setSessionId(null)
    setPanelUpdates([])
    setDiagnosisError(null)
    setFollowUpAnswer('')
  }, [])

  const loadTehsilLayers = useCallback(async (ref: TehsilRef) => {
    const seq = ++tehsilLoadSeq.current
    setMapError(null)
    setSelectedTehsil(ref)
    setSelectedMwsUid(null)
    setMwsData(null)
    setMwsBoundaries(null)
    if (showVillages) setVillageBoundaries(null)
    resetDiagnosisForNewMws()
    try {
      const mws = await fetchMwsBoundaries(ref)
      if (tehsilLoadSeq.current !== seq) return
      setMwsBoundaries(mws)
    } catch (err) {
      if (tehsilLoadSeq.current !== seq) return
      setMwsBoundaries(null)
      setMapError(err instanceof Error ? err.message : 'Failed to load tehsil layers')
    }
  }, [showVillages, resetDiagnosisForNewMws])

  const selectMws = useCallback(async (uid: string) => {
    setSelectedMwsUid(uid)
    resetDiagnosisForNewMws()
    setMwsLoading(true)
    setMapError(null)
    try {
      const doc = await fetchMws(uid)
      setMwsData(doc)
    } catch (err) {
      setMwsData(null)
      setMapError(err instanceof Error ? err.message : 'Failed to load MWS')
    } finally {
      setMwsLoading(false)
    }
  }, [resetDiagnosisForNewMws])

  const villageNames = useMemo(
    () => (mwsData?.intersect_village_names ?? []).map((v) => v.name).filter(Boolean) as string[],
    [mwsData],
  )

  useEffect(() => {
    if (!selectedTehsil || !showVillages) {
      if (!showVillages) setVillageBoundaries(null)
      return
    }
    const seq = tehsilLoadSeq.current
    fetchVillageBoundaries(selectedTehsil)
      .then((villages) => {
        if (tehsilLoadSeq.current !== seq) return
        setVillageBoundaries(villages)
      })
      .catch(() => {
        if (tehsilLoadSeq.current !== seq) return
        setVillageBoundaries(null)
      })
  }, [selectedTehsil, showVillages])

  async function handleLocationSelect(lat: number, lon: number) {
    setFlyTarget({ lat, lon, zoom: 12 })
    try {
      const located = await locatePoint(lat, lon)
      if (!located.found || !located.state || !located.district || !located.tehsil) {
        setMapError('Location is outside ingested tehsil boundaries.')
        return
      }
      const ref = { state: located.state, district: located.district, tehsil: located.tehsil }
      await loadTehsilLayers(ref)
      if (located.mws_uid) await selectMws(located.mws_uid)
    } catch (err) {
      setMapError(err instanceof Error ? err.message : 'Locate failed')
    }
  }

  async function handleDiagnosis() {
    if (!selectedMwsUid) return
    setDiagnosisLoading(true)
    setDiagnosisError(null)
    try {
      const result = await runDiagnosisQuery(selectedMwsUid, problem, sessionId)
      setDiagnosis(result)
      setFollowUpHistory([])
      setSessionId(result.session_id)
      setPanelUpdates(result.panel_updates ?? [])
      setFollowUpAnswer('')
    } catch (err) {
      setDiagnosisError(err instanceof Error ? err.message : 'Diagnosis failed')
    } finally {
      setDiagnosisLoading(false)
    }
  }

  async function handleFollowUp() {
    if (!sessionId || !followUpAnswer.trim() || !followUpTarget) return
    const answer = followUpAnswer.trim()
    const question =
      followUpTarget.question ??
      (followUpTarget.structured ? 'Follow-up response' : 'Additional observation')
    setDiagnosisLoading(true)
    setDiagnosisError(null)
    try {
      const result = await submitDiagnosisAnswer(sessionId, followUpTarget.variable, answer)
      setFollowUpHistory((prev) => [
        ...prev,
        {
          question,
          answer,
          actions: result.panel_updates ?? [],
          explanation: result.panel_update_explanation ?? null,
          variable: followUpTarget.variable,
          revision: result.diagnosis_revision ?? null,
          signalUpdates: result.follow_up_signal_updates ?? [],
          signalEvaluation: result.signal_evaluation ?? null,
        },
      ])
      setDiagnosis(result)
      setPanelUpdates((prev) => [...prev, ...(result.panel_updates ?? [])])
      setFollowUpAnswer('')
    } catch (err) {
      setDiagnosisError(err instanceof Error ? err.message : 'Follow-up failed')
    } finally {
      setDiagnosisLoading(false)
    }
  }

  const ingestedCount = ingestedKeys.size

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-stone-300 bg-[#3f2f1f] px-4 py-3 text-white shadow">
        <div>
          <h1 className="text-lg font-semibold">Landscape Problem Diagnosis</h1>
          <p className="text-sm text-amber-100/80">Micro-watershed explorer · {ingestedCount} ingested tehsils</p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showVillages}
              onChange={(e) => setShowVillages(e.target.checked)}
              className="rounded border-stone-400"
            />
            Village boundaries
          </label>
          {selectedTehsil && (
            <span className="rounded-full bg-amber-700/80 px-3 py-1 text-xs">
              {selectedTehsil.tehsil}, {selectedTehsil.district}
            </span>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[320px_1fr_380px]">
        <aside className="flex min-h-0 flex-col border-r border-stone-300 bg-[#faf7f2]">
          <LocationSearch onSelect={handleLocationSelect} disabled={diagnosisLoading} />
          <DiagnosisPanel
            selectedMwsUid={selectedMwsUid}
            villageNames={villageNames}
            problem={problem}
            onProblemChange={setProblem}
            onSubmit={handleDiagnosis}
            loading={diagnosisLoading}
            error={diagnosisError}
            diagnosis={diagnosis}
            followUpHistory={followUpHistory}
            followUpAnswer={followUpAnswer}
            onFollowUpAnswerChange={setFollowUpAnswer}
            followUpTarget={followUpTarget}
            canContinueConversation={!!sessionId && !!diagnosis}
            onSubmitFollowUp={handleFollowUp}
            disabled={!selectedMwsUid}
            mwsAerCode={mwsData?.nbss_lup_aer_code ?? diagnosis?.mws_aer_code ?? null}
            retrievalAerTags={diagnosis?.retrieval_aer_tags ?? null}
          />
        </aside>

        <main className="relative min-h-0">
          {mapError && (
            <div className="absolute left-3 right-3 top-3 z-[1000] rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 shadow">
              {mapError}
            </div>
          )}
          <MapView
            tehsils={tehsils}
            mwsBoundaries={mwsBoundaries}
            villageBoundaries={villageBoundaries}
            selectedTehsil={selectedTehsil}
            selectedMwsUid={selectedMwsUid}
            showVillages={showVillages}
            flyTarget={flyTarget}
            onTehsilSelect={(ref) => {
              if (!ingestedKeys.has(tehsilKey(ref))) {
                setMapError(`${ref.tehsil} is not in the ingested corpus yet.`)
                return
              }
              void loadTehsilLayers(ref)
            }}
            onMwsSelect={(uid) => void selectMws(uid)}
          />
        </main>

        <aside className="min-h-0 border-l border-stone-300 bg-[#faf7f2]">
          <InfoPanel mws={mwsData} loading={mwsLoading} panelUpdates={panelUpdates} />
        </aside>
      </div>
    </div>
  )
}
