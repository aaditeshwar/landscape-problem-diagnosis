import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
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
  const [wantLlmOpinion, setWantLlmOpinion] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [diagnosis, setDiagnosis] = useState<DiagnosisResponse | null>(null)
  const [followUpHistory, setFollowUpHistory] = useState<FollowUpExchange[]>([])
  const [panelUpdates, setPanelUpdates] = useState<string[]>([])
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisError, setDiagnosisError] = useState<string | null>(null)
  const [followUpAnswer, setFollowUpAnswer] = useState('')
  const [diagnosisSessionMwsUid, setDiagnosisSessionMwsUid] = useState<string | null>(null)
  const [diagnosisSessionTehsil, setDiagnosisSessionTehsil] = useState<TehsilRef | null>(null)
  const [analysisMwsDoc, setAnalysisMwsDoc] = useState<MwsDocument | null>(null)
  const [mwsHighlightEpoch, setMwsHighlightEpoch] = useState(0)

  const activeSessionId = sessionId ?? diagnosis?.session_id ?? null
  const askedVariables = useMemo(() => askedVariablesFromHistory(followUpHistory), [followUpHistory])
  const askedQuestions = useMemo(() => askedQuestionsFromHistory(followUpHistory), [followUpHistory])
  const followUpTarget = useMemo(
    () => resolveFollowUpTarget(diagnosis, askedVariables, askedQuestions),
    [diagnosis, askedVariables, askedQuestions],
  )
  const tehsilLoadSeq = useRef(0)
  const mwsSelectSeq = useRef(0)
  const restoreEpoch = useRef(0)
  const activeDiagnosisContextRef = useRef<{ mwsUid: string; tehsil: TehsilRef } | null>(null)
  const restoringDiagnosisContextRef = useRef(false)
  const diagnosisSessionMwsUidRef = useRef<string | null>(null)
  const diagnosisSessionTehsilRef = useRef<TehsilRef | null>(null)
  const diagnosisLoadingRef = useRef(false)
  const analysisMwsDocRef = useRef<MwsDocument | null>(null)
  const selectedTehsilRef = useRef<TehsilRef | null>(null)
  selectedTehsilRef.current = selectedTehsil
  diagnosisSessionMwsUidRef.current = diagnosisSessionMwsUid
  diagnosisSessionTehsilRef.current = diagnosisSessionTehsil
  diagnosisLoadingRef.current = diagnosisLoading
  analysisMwsDocRef.current = analysisMwsDoc

  const lockedDiagnosisMwsUid = diagnosisSessionMwsUid ?? diagnosisSessionMwsUidRef.current
  const lockedAnalysisMwsDoc = analysisMwsDoc ?? analysisMwsDocRef.current
  const isDiagnosisSessionLocked = Boolean(lockedDiagnosisMwsUid)

  function lockDiagnosisSession(mwsUid: string, tehsil: TehsilRef, snapshot: MwsDocument | null) {
    activeDiagnosisContextRef.current = { mwsUid, tehsil }
    diagnosisSessionMwsUidRef.current = mwsUid
    diagnosisSessionTehsilRef.current = tehsil
    setDiagnosisSessionMwsUid(mwsUid)
    setDiagnosisSessionTehsil(tehsil)
    if (snapshot?.uid === mwsUid) {
      analysisMwsDocRef.current = snapshot
      setAnalysisMwsDoc(snapshot)
    }
  }

  function unlockDiagnosisSession() {
    activeDiagnosisContextRef.current = null
    diagnosisSessionMwsUidRef.current = null
    diagnosisSessionTehsilRef.current = null
    analysisMwsDocRef.current = null
    setDiagnosisSessionMwsUid(null)
    setDiagnosisSessionTehsil(null)
    setAnalysisMwsDoc(null)
  }

  function shouldPreserveDiagnosisSession(): boolean {
    return (
      diagnosisLoadingRef.current ||
      restoringDiagnosisContextRef.current ||
      activeDiagnosisContextRef.current != null ||
      diagnosisSessionMwsUidRef.current != null
    )
  }

  function preserveDiagnosisOnMapBrowse(options?: { preserveDiagnosis?: boolean }): boolean {
    return shouldPreserveDiagnosisSession() || Boolean(options?.preserveDiagnosis)
  }

  function flyToMwsUid(uid: string, tehsil: TehsilRef, boundaries: MwsFeatureCollection | null) {
    if (!boundaries) return
    const feature = boundaries.features.find((item) => {
      const props = item.properties as Record<string, unknown>
      return (
        props.uid === uid &&
        props.state === tehsil.state &&
        props.district === tehsil.district &&
        props.tehsil === tehsil.tehsil
      )
    })
    if (!feature) return
    const layer = L.geoJSON(feature)
    const bounds = layer.getBounds()
    if (!bounds.isValid()) return
    const center = bounds.getCenter()
    setFlyTarget({ lat: center.lat, lon: center.lng, zoom: 13 })
  }

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
    unlockDiagnosisSession()
  }, [])

  const diagnosisContextSnapshot = useCallback((): { mwsUid: string; tehsil: TehsilRef } | null => {
    if (activeDiagnosisContextRef.current) return activeDiagnosisContextRef.current
    const mwsUid = diagnosisSessionMwsUidRef.current
    const tehsil = diagnosisSessionTehsilRef.current
    if (mwsUid && tehsil) return { mwsUid, tehsil }
    return null
  }, [])

  const restoreActiveDiagnosisContext = useCallback(async () => {
    const ctx = diagnosisContextSnapshot()
    if (!ctx) return

    restoringDiagnosisContextRef.current = true
    mwsSelectSeq.current += 1
    tehsilLoadSeq.current += 1
    const epoch = ++restoreEpoch.current
    const restoreTehsilSeq = tehsilLoadSeq.current
    try {
      setMapError(null)
      setSelectedTehsil(ctx.tehsil)
      setMwsBoundaries(null)
      if (showVillages) setVillageBoundaries(null)

      let restoredBoundaries: MwsFeatureCollection | null = null
      try {
        const boundaries = await fetchMwsBoundaries(ctx.tehsil)
        if (restoreEpoch.current !== epoch) return
        if (tehsilLoadSeq.current === restoreTehsilSeq) {
          setMwsBoundaries(boundaries)
          restoredBoundaries = boundaries
        }
      } catch (err) {
        if (restoreEpoch.current !== epoch) return
        if (tehsilLoadSeq.current === restoreTehsilSeq) {
          setMwsBoundaries(null)
          setMapError(err instanceof Error ? err.message : 'Failed to load tehsil layers')
        }
      }

      if (restoreEpoch.current !== epoch) return

      if (!restoredBoundaries) {
        try {
          const boundaries = await fetchMwsBoundaries(ctx.tehsil)
          if (restoreEpoch.current !== epoch) return
          setMwsBoundaries(boundaries)
          restoredBoundaries = boundaries
        } catch (err) {
          if (restoreEpoch.current !== epoch) return
          setMapError(err instanceof Error ? err.message : 'Failed to load tehsil layers')
        }
      }

      if (restoreEpoch.current !== epoch) return

      setSelectedMwsUid(ctx.mwsUid)
      setMwsHighlightEpoch((value) => value + 1)
      setMwsLoading(true)
      setMapError(null)
      try {
        const doc = await fetchMws(ctx.mwsUid)
        if (restoreEpoch.current !== epoch) return
        setMwsData(doc)
        flyToMwsUid(ctx.mwsUid, ctx.tehsil, restoredBoundaries)
      } catch (err) {
        if (restoreEpoch.current !== epoch) return
        setMwsData(null)
        setMapError(err instanceof Error ? err.message : 'Failed to load MWS')
      } finally {
        if (restoreEpoch.current === epoch) {
          setMwsLoading(false)
        }
      }
    } finally {
      if (restoreEpoch.current === epoch) {
        activeDiagnosisContextRef.current = null
      }
      restoringDiagnosisContextRef.current = false
    }
  }, [showVillages, diagnosisContextSnapshot])

  const loadTehsilLayers = useCallback(async (ref: TehsilRef, options?: { preserveDiagnosis?: boolean }) => {
    if (restoringDiagnosisContextRef.current) return
    const preserveDiagnosis = preserveDiagnosisOnMapBrowse(options)
    const seq = ++tehsilLoadSeq.current
    setMapError(null)
    setSelectedTehsil(ref)
    setSelectedMwsUid(null)
    setMwsData(null)
    setMwsBoundaries(null)
    if (showVillages) setVillageBoundaries(null)
    if (!preserveDiagnosis) {
      resetDiagnosisForNewMws()
    }
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
    if (restoringDiagnosisContextRef.current) return
    const seq = ++mwsSelectSeq.current
    setSelectedMwsUid(uid)
    if (!shouldPreserveDiagnosisSession()) {
      resetDiagnosisForNewMws()
    }
    setMwsLoading(true)
    setMapError(null)
    try {
      const doc = await fetchMws(uid)
      if (mwsSelectSeq.current !== seq) return
      setMwsData(doc)
    } catch (err) {
      if (mwsSelectSeq.current !== seq) return
      setMwsData(null)
      setMapError(err instanceof Error ? err.message : 'Failed to load MWS')
    } finally {
      if (mwsSelectSeq.current === seq) {
        setMwsLoading(false)
      }
    }
  }, [resetDiagnosisForNewMws])

  const mapVillageNames = useMemo(
    () => (mwsData?.intersect_village_names ?? []).map((v) => v.name).filter(Boolean) as string[],
    [mwsData],
  )

  const analysisVillageNames = useMemo(
    () =>
      (lockedAnalysisMwsDoc?.intersect_village_names ?? [])
        .map((v) => v.name)
        .filter(Boolean) as string[],
    [lockedAnalysisMwsDoc],
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
      await loadTehsilLayers(ref, { preserveDiagnosis: preserveDiagnosisOnMapBrowse() })
      if (located.mws_uid) await selectMws(located.mws_uid)
    } catch (err) {
      setMapError(err instanceof Error ? err.message : 'Locate failed')
    }
  }

  async function handleDiagnosis() {
    if (!selectedMwsUid || !selectedTehsil) return
    const analysisUid = selectedMwsUid
    const analysisTehsil = selectedTehsil
    lockDiagnosisSession(analysisUid, analysisTehsil, mwsData?.uid === analysisUid ? mwsData : null)
    if (mwsData?.uid !== analysisUid) {
      try {
        const snapshot = await fetchMws(analysisUid)
        if (diagnosisSessionMwsUidRef.current === analysisUid) {
          analysisMwsDocRef.current = snapshot
          setAnalysisMwsDoc(snapshot)
        }
      } catch {
        if (diagnosisSessionMwsUidRef.current === analysisUid) {
          analysisMwsDocRef.current = null
          setAnalysisMwsDoc(null)
        }
      }
    }
    diagnosisLoadingRef.current = true
    setDiagnosisLoading(true)
    setDiagnosisError(null)
    try {
      const result = await runDiagnosisQuery(
        analysisUid,
        wantLlmOpinion ? problem : '',
        sessionId,
        analysisTehsil,
        wantLlmOpinion,
      )
      setDiagnosis(result)
      setFollowUpHistory([])
      setSessionId(result.session_id)
      setPanelUpdates(result.panel_updates ?? [])
      setFollowUpAnswer('')
    } catch (err) {
      setDiagnosisError(err instanceof Error ? err.message : 'Diagnosis failed')
    } finally {
      await restoreActiveDiagnosisContext()
      diagnosisLoadingRef.current = false
      setDiagnosisLoading(false)
    }
  }

  async function handleFollowUp() {
    if (!sessionId || !followUpTarget) return
    const mcq = diagnosis?.follow_up_mcq
    const usingMcq = Boolean(mcq && mcq.variable === followUpTarget.variable)
    if (usingMcq && !followUpAnswer.trim()) return
    if (!usingMcq && !followUpAnswer.trim()) return

    const answer = followUpAnswer.trim()

    const displayAnswer = usingMcq
      ? mcq!.choices.find((choice) => choice.id === answer)?.label ?? answer
      : answer
    const question =
      followUpTarget.question ??
      mcq?.question ??
      (followUpTarget.structured ? 'Follow-up response' : 'Additional observation')
    const sessionMwsUid = diagnosisSessionMwsUidRef.current
    const sessionTehsil = diagnosisSessionTehsilRef.current
    if (sessionMwsUid && sessionTehsil) {
      lockDiagnosisSession(sessionMwsUid, sessionTehsil, lockedAnalysisMwsDoc)
    }
    diagnosisLoadingRef.current = true
    setDiagnosisLoading(true)
    setDiagnosisError(null)
    try {
      const result = await submitDiagnosisAnswer(
        sessionId,
        followUpTarget.variable,
        usingMcq ? '' : answer,
        wantLlmOpinion,
        usingMcq ? answer : null,
      )
      if (result.session_id) setSessionId(result.session_id)
      setFollowUpHistory((prev) => [
        ...prev,
        {
          question,
          answer: displayAnswer,
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
      await restoreActiveDiagnosisContext()
      diagnosisLoadingRef.current = false
      setDiagnosisLoading(false)
    }
  }

  const lockedDiagnosisTehsil = diagnosisSessionTehsil ?? diagnosisSessionTehsilRef.current
  const panelDisplayLocation: TehsilRef | null = isDiagnosisSessionLocked
    ? lockedDiagnosisTehsil
    : selectedTehsil ??
      (mwsData
        ? { state: mwsData.state, district: mwsData.district, tehsil: mwsData.tehsil }
        : null)

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
            analysisMwsUid={lockedDiagnosisMwsUid}
            displayMwsUid={isDiagnosisSessionLocked ? lockedDiagnosisMwsUid : selectedMwsUid}
            villageNames={isDiagnosisSessionLocked ? analysisVillageNames : mapVillageNames}
            problem={problem}
            onProblemChange={setProblem}
            wantLlmOpinion={wantLlmOpinion}
            onWantLlmOpinionChange={setWantLlmOpinion}
            onSubmit={handleDiagnosis}
            loading={diagnosisLoading}
            error={diagnosisError}
            diagnosis={diagnosis}
            followUpHistory={followUpHistory}
            followUpAnswer={followUpAnswer}
            onFollowUpAnswerChange={setFollowUpAnswer}
            followUpTarget={followUpTarget}
            canContinueConversation={Boolean(activeSessionId) && Boolean(diagnosis)}
            onSubmitFollowUp={handleFollowUp}
            disabled={!selectedMwsUid}
            mwsAerCode={
              isDiagnosisSessionLocked
                ? lockedAnalysisMwsDoc?.nbss_lup_aer_code ?? diagnosis?.mws_aer_code ?? null
                : mwsData?.nbss_lup_aer_code ?? diagnosis?.mws_aer_code ?? null
            }
            retrievalAerTags={diagnosis?.retrieval_aer_tags ?? null}
            freezeContext={isDiagnosisSessionLocked}
            lockedTehsil={lockedDiagnosisTehsil}
            mapTehsil={selectedTehsil}
            displayLocation={panelDisplayLocation}
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
            mwsHighlightEpoch={mwsHighlightEpoch}
            showVillages={showVillages}
            flyTarget={flyTarget}
            onTehsilSelect={(ref) => {
              if (!ingestedKeys.has(tehsilKey(ref))) {
                setMapError(`${ref.tehsil} is not in the ingested corpus yet.`)
                return
              }
              void loadTehsilLayers(ref, {
                preserveDiagnosis: preserveDiagnosisOnMapBrowse(),
              })
            }}
            onMwsSelect={(uid) => void selectMws(uid)}
          />
        </main>

        <aside className="min-h-0 border-l border-stone-300 bg-[#faf7f2]">
          <InfoPanel
            mws={mwsData}
            loading={mwsLoading}
            activeTehsil={selectedTehsil}
            panelUpdates={
              lockedDiagnosisMwsUid && selectedMwsUid !== lockedDiagnosisMwsUid ? [] : panelUpdates
            }
          />
        </aside>
      </div>
    </div>
  )
}
