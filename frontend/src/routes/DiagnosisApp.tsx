import { Link, useSearchParams } from 'react-router-dom'
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
} from '../api/client'
import { DiagnosisPanel } from '../components/DiagnosisPanel'
import { InfoPanel } from '../components/InfoPanel'
import { LocationSearch } from '../components/LocationSearch'
import { MapView } from '../components/MapView'
import { PanelResizeHandle } from '../components/PanelResizeHandle'
import type { DiagnosisResponse, FeatureCollection, FollowUpExchange, MwsDocument, MwsFeatureCollection, TehsilFeatureCollection, TehsilRef } from '../types'
import {
  askedQuestionsFromHistory,
  askedVariablesFromHistory,
  resolveFollowUpTarget,
} from '../utils/followUp'

function tehsilKey(ref: TehsilRef): string {
  return `${ref.state}__${ref.district}__${ref.tehsil}`
}

const LEFT_PANEL_WIDTH_KEY = 'diagnose-left-panel-width'
const RIGHT_PANEL_WIDTH_KEY = 'diagnose-right-panel-width'
const DEFAULT_LEFT_PANEL_WIDTH = 320
const DEFAULT_RIGHT_PANEL_WIDTH = 380

function clampPanelWidth(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function readStoredPanelWidth(key: string, fallback: number): number {
  if (typeof window === 'undefined') return fallback
  const stored = window.localStorage.getItem(key)
  if (!stored) return fallback
  const parsed = Number(stored)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function DiagnosisApp() {
  const [searchParams] = useSearchParams()
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
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lon: number; zoom?: number; seq: number } | null>(null)

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
  const [leftPanelWidth, setLeftPanelWidth] = useState(() =>
    readStoredPanelWidth(LEFT_PANEL_WIDTH_KEY, DEFAULT_LEFT_PANEL_WIDTH),
  )
  const [rightPanelWidth, setRightPanelWidth] = useState(() =>
    readStoredPanelWidth(RIGHT_PANEL_WIDTH_KEY, DEFAULT_RIGHT_PANEL_WIDTH),
  )
  const [mapLayoutEpoch, setMapLayoutEpoch] = useState(0)
  const leftPanelWidthRef = useRef(leftPanelWidth)
  const rightPanelWidthRef = useRef(rightPanelWidth)
  leftPanelWidthRef.current = leftPanelWidth
  rightPanelWidthRef.current = rightPanelWidth

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
  const diagnosisRequestSeq = useRef(0)
  const followUpRequestSeq = useRef(0)
  const diagnosisLoadingRef = useRef(false)
  const analysisMwsDocRef = useRef<MwsDocument | null>(null)
  const selectedTehsilRef = useRef<TehsilRef | null>(null)
  const selectedMwsUidRef = useRef<string | null>(null)
  const mwsBoundariesRef = useRef<MwsFeatureCollection | null>(null)
  const deepLinkHandledRef = useRef(false)
  selectedTehsilRef.current = selectedTehsil
  selectedMwsUidRef.current = selectedMwsUid
  mwsBoundariesRef.current = mwsBoundaries
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
    setFlyTarget({ lat: center.lat, lon: center.lng, zoom: 13, seq: Date.now() })
  }

  const diagnosisContextSnapshot = useCallback((): { mwsUid: string; tehsil: TehsilRef } | null => {
    if (activeDiagnosisContextRef.current) return activeDiagnosisContextRef.current
    const mwsUid = diagnosisSessionMwsUidRef.current
    const tehsil = diagnosisSessionTehsilRef.current
    if (mwsUid && tehsil) return { mwsUid, tehsil }
    return null
  }, [])

  function sameDiagnosisMapContext(
    ctx: { mwsUid: string; tehsil: TehsilRef },
    tehsil: TehsilRef | null,
    mwsUid: string | null,
  ): boolean {
    if (!tehsil || mwsUid !== ctx.mwsUid) return false
    return (
      tehsil.state === ctx.tehsil.state &&
      tehsil.district === ctx.tehsil.district &&
      tehsil.tehsil === ctx.tehsil.tehsil
    )
  }

  function sameDiagnosisTehsil(ctx: { tehsil: TehsilRef }, tehsil: TehsilRef | null): boolean {
    if (!tehsil) return false
    return (
      tehsil.state === ctx.tehsil.state &&
      tehsil.district === ctx.tehsil.district &&
      tehsil.tehsil === ctx.tehsil.tehsil
    )
  }

  const restoreActiveDiagnosisContext = useCallback(
    async (options?: { fly?: boolean }) => {
      const ctx = diagnosisContextSnapshot()
      if (!ctx) return

      const currentTehsil = selectedTehsilRef.current
      const currentMwsUid = selectedMwsUidRef.current
      const sameContext = sameDiagnosisMapContext(ctx, currentTehsil, currentMwsUid)
      const sameTehsil = sameDiagnosisTehsil(ctx, currentTehsil)
      const boundaries = mwsBoundariesRef.current

      if (sameContext && boundaries) {
        if (options?.fly === true) {
          flyToMwsUid(ctx.mwsUid, ctx.tehsil, boundaries)
        }
        activeDiagnosisContextRef.current = null
        return
      }

      restoringDiagnosisContextRef.current = true
      mwsSelectSeq.current += 1
      const epoch = ++restoreEpoch.current
      const restoreTehsilSeq = sameTehsil ? tehsilLoadSeq.current : ++tehsilLoadSeq.current
      try {
        setMapError(null)
        setSelectedTehsil(ctx.tehsil)
        if (!sameTehsil) {
          setMwsBoundaries(null)
          if (showVillages) setVillageBoundaries(null)
        }

        let restoredBoundaries: MwsFeatureCollection | null = sameTehsil ? boundaries : null
        if (!restoredBoundaries) {
          try {
            const fetched = await fetchMwsBoundaries(ctx.tehsil)
            if (restoreEpoch.current !== epoch) return
            if (tehsilLoadSeq.current === restoreTehsilSeq) {
              setMwsBoundaries(fetched)
              restoredBoundaries = fetched
            }
          } catch (err) {
            if (restoreEpoch.current !== epoch) return
            if (tehsilLoadSeq.current === restoreTehsilSeq) {
              setMwsBoundaries(null)
              setMapError(err instanceof Error ? err.message : 'Failed to load tehsil layers')
            }
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
          if (restoredBoundaries && options?.fly !== false) {
            flyToMwsUid(ctx.mwsUid, ctx.tehsil, restoredBoundaries)
          }
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
    },
    [showVillages, diagnosisContextSnapshot],
  )

  const focusDiagnosisMwsOnMap = useCallback(async () => {
    const mwsUid = diagnosisSessionMwsUidRef.current
    const tehsil = diagnosisSessionTehsilRef.current
    if (!mwsUid || !tehsil) return
    activeDiagnosisContextRef.current = { mwsUid, tehsil }
    await restoreActiveDiagnosisContext({ fly: true })
  }, [restoreActiveDiagnosisContext])

  useEffect(() => {
    Promise.all([fetchTehsils(), fetchIngestedTehsils()])
      .then(([tehsilGeo, ingested]) => {
        setTehsils(tehsilGeo)
        setIngestedKeys(new Set(ingested.tehsils.map((t) => t.id)))
      })
      .catch((err) => setMapError(err instanceof Error ? err.message : 'Failed to load map'))
  }, [])

  useEffect(() => {
    if (deepLinkHandledRef.current || !tehsils) return
    const mwsUid = searchParams.get('mws') || searchParams.get('uid')
    if (!mwsUid) return
    deepLinkHandledRef.current = true

    void (async () => {
      let tehsil: TehsilRef | null = null
      const state = searchParams.get('state')
      const district = searchParams.get('district')
      const tehsilName = searchParams.get('tehsil')
      if (state && district && tehsilName) {
        tehsil = { state, district, tehsil: tehsilName }
      } else {
        try {
          const doc = await fetchMws(mwsUid)
          const primary = doc.tehsils?.[0]
          if (primary) {
            tehsil = primary
          } else if (doc.state && doc.district && doc.tehsil) {
            tehsil = { state: doc.state, district: doc.district, tehsil: doc.tehsil }
          }
        } catch (err) {
          setMapError(err instanceof Error ? err.message : 'Failed to open MWS deep link')
          return
        }
      }
      if (!tehsil) return
      activeDiagnosisContextRef.current = { mwsUid, tehsil }
      await restoreActiveDiagnosisContext({ fly: true })
    })()
  }, [searchParams, tehsils, restoreActiveDiagnosisContext])

  const resetDiagnosisForNewMws = useCallback(() => {
    setDiagnosis(null)
    setFollowUpHistory([])
    setSessionId(null)
    setPanelUpdates([])
    setDiagnosisError(null)
    setFollowUpAnswer('')
    unlockDiagnosisSession()
  }, [])

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
    setFlyTarget({ lat, lon, zoom: 12, seq: Date.now() })
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

  const handleCloseDiagnosis = useCallback(() => {
    diagnosisRequestSeq.current += 1
    followUpRequestSeq.current += 1
    diagnosisLoadingRef.current = false
    setDiagnosisLoading(false)
    resetDiagnosisForNewMws()
  }, [resetDiagnosisForNewMws])

  async function handleDiagnosis() {
    if (!selectedMwsUid || !selectedTehsil || isDiagnosisSessionLocked) return
    const requestSeq = ++diagnosisRequestSeq.current
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
      if (diagnosisRequestSeq.current !== requestSeq) return
      setDiagnosis(result)
      setFollowUpHistory([])
      setSessionId(result.session_id)
      setPanelUpdates(result.panel_updates ?? [])
      setFollowUpAnswer('')
    } catch (err) {
      if (diagnosisRequestSeq.current !== requestSeq) return
      setDiagnosisError(err instanceof Error ? err.message : 'Diagnosis failed')
      unlockDiagnosisSession()
    } finally {
      if (diagnosisRequestSeq.current === requestSeq) {
        await restoreActiveDiagnosisContext()
        diagnosisLoadingRef.current = false
        setDiagnosisLoading(false)
      }
    }
  }

  async function handleFollowUp() {
    if (!sessionId || !followUpTarget) return
    const mcq = diagnosis?.follow_up_mcq
    const usingMcq = Boolean(mcq && mcq.variable === followUpTarget.variable)
    if (!usingMcq) {
      setDiagnosisError('Follow-up requires an MCQ choice for this variable.')
      return
    }
    if (!followUpAnswer.trim()) return

    const answer = followUpAnswer.trim()
    const displayAnswer = mcq!.choices.find((choice) => choice.id === answer)?.label ?? answer
    const question = followUpTarget.question ?? mcq!.question ?? 'Follow-up response'
    const sessionMwsUid = diagnosisSessionMwsUidRef.current
    const sessionTehsil = diagnosisSessionTehsilRef.current
    if (sessionMwsUid && sessionTehsil) {
      lockDiagnosisSession(sessionMwsUid, sessionTehsil, lockedAnalysisMwsDoc)
    }
    diagnosisLoadingRef.current = true
    setDiagnosisLoading(true)
    setDiagnosisError(null)
    const requestSeq = ++followUpRequestSeq.current
    try {
      const result = await submitDiagnosisAnswer(
        sessionId,
        followUpTarget.variable,
        '',
        wantLlmOpinion,
        answer,
      )
      if (followUpRequestSeq.current !== requestSeq) return
      if (result.session_id) setSessionId(result.session_id)
      const historyEntry: FollowUpExchange = {
        question,
        answer: displayAnswer,
        actions: result.panel_updates ?? [],
        explanation: result.panel_update_explanation ?? null,
        variable: followUpTarget.variable,
        revision: result.diagnosis_revision ?? null,
        signalUpdates: result.follow_up_signal_updates ?? [],
        signalEvaluation: result.signal_evaluation ?? null,
      }
      const nextHistory = [...followUpHistory, historyEntry]
      setFollowUpHistory(nextHistory)
      setDiagnosis(result)
      setPanelUpdates((prev) => [...prev, ...(result.panel_updates ?? [])])
      setFollowUpAnswer('')
    } catch (err) {
      if (followUpRequestSeq.current !== requestSeq) return
      setDiagnosisError(err instanceof Error ? err.message : 'Follow-up failed')
    } finally {
      if (followUpRequestSeq.current === requestSeq) {
        await restoreActiveDiagnosisContext()
        diagnosisLoadingRef.current = false
        setDiagnosisLoading(false)
      }
    }
  }

  const lockedDiagnosisTehsil = diagnosisSessionTehsil ?? diagnosisSessionTehsilRef.current

  const panelDisplayLocation: TehsilRef | null = isDiagnosisSessionLocked
    ? lockedDiagnosisTehsil
    : selectedTehsil ??
      (mwsData
        ? { state: mwsData.state, district: mwsData.district, tehsil: mwsData.tehsil }
        : null)

  const clearFlyTarget = useCallback(() => setFlyTarget(null), [])

  const persistPanelWidths = useCallback(() => {
    window.localStorage.setItem(LEFT_PANEL_WIDTH_KEY, String(leftPanelWidthRef.current))
    window.localStorage.setItem(RIGHT_PANEL_WIDTH_KEY, String(rightPanelWidthRef.current))
    setMapLayoutEpoch((value) => value + 1)
  }, [])

  const handleLeftPanelDrag = useCallback((deltaX: number) => {
    setLeftPanelWidth((width) => {
      const next = clampPanelWidth(width + deltaX, 240, 520)
      leftPanelWidthRef.current = next
      return next
    })
  }, [])

  const handleRightPanelDrag = useCallback((deltaX: number) => {
    setRightPanelWidth((width) => {
      const next = clampPanelWidth(width - deltaX, 280, 560)
      rightPanelWidthRef.current = next
      return next
    })
  }, [])

  const ingestedCount = ingestedKeys.size

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-stone-300 bg-[#3f2f1f] px-4 py-3 text-white shadow">
        <div>
          <Link to="/" className="text-lg font-semibold hover:text-amber-100">
            CoRE Insights
          </Link>
          <p className="text-sm text-amber-100/80">Micro-watershed explorer · {ingestedCount} ingested tehsils</p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link
            to="/signals"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-amber-200/40 px-2 py-1 text-xs text-amber-50 hover:bg-amber-800/60"
          >
            Edit evidence signals
          </Link>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showVillages}
              onChange={(e) => setShowVillages(e.target.checked)}
              className="rounded border-stone-400"
            />
            Village boundaries
          </label>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          className="flex min-h-0 shrink-0 flex-col border-r border-stone-300 bg-[#faf7f2]"
          style={{ width: leftPanelWidth }}
        >
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
            onCloseDiagnosis={handleCloseDiagnosis}
            onFocusDiagnosisMws={() => void focusDiagnosisMwsOnMap()}
            sessionActive={isDiagnosisSessionLocked}
            loading={diagnosisLoading}
            error={diagnosisError}
            diagnosis={diagnosis}
            followUpHistory={followUpHistory}
            followUpAnswer={followUpAnswer}
            onFollowUpAnswerChange={setFollowUpAnswer}
            followUpTarget={followUpTarget}
            canContinueConversation={Boolean(activeSessionId) && Boolean(followUpTarget)}
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

        <PanelResizeHandle onDrag={handleLeftPanelDrag} onDragEnd={persistPanelWidths} />

        <main className="relative min-h-0 min-w-0 flex-1">
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
            layoutEpoch={mapLayoutEpoch}
            showVillages={showVillages}
            flyTarget={flyTarget}
            onFlyComplete={clearFlyTarget}
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

        <PanelResizeHandle onDrag={handleRightPanelDrag} onDragEnd={persistPanelWidths} />

        <aside
          className="min-h-0 shrink-0 border-l border-stone-300 bg-[#faf7f2]"
          style={{ width: rightPanelWidth }}
        >
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
