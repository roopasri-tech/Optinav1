import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import FacilityDetails, { CATEGORY_ICON, facilitySubtitle } from '../components/FacilityDetails'
import LocationSearch from '../components/LocationSearch'
import VehiclePanel from '../components/VehiclePanel'
import { useTrip } from '../hooks/useTrip'
import RouteMap from '../map/RouteMap'
import { optimizationApi, placesApi, routesApi } from '../services/api'
import type { Facility } from '../types'
import { CATEGORY_LABEL, formatDuration, formatKm } from '../utils/format'

const TABS = ['all', 'fuel', 'cng', 'ev', 'restaurant', 'parking', 'restroom'] as const
const LIST_LIMIT = 300
const POLL_MS = 4000
const MAX_POLLS = 45

function matches(f: Facility, tab: string) {
  if (tab === 'all') return true
  if (tab === 'cng') return f.category === 'fuel' && (f.fuel_types || []).includes('cng')
  return f.category === tab
}

export default function PlannerPage() {
  const navigate = useNavigate()
  const {
    sourceLoc, destLoc, sourceText, destText, setSource, setDest, vehicle, levels, preference, setPreference,
    route, setRoute, facilities, facilityMeta, setFacilityData, setTripResult, clearDerived,
  } = useTrip()

  const [tab, setTab] = useState<string>('all')
  const [selected, setSelected] = useState<Facility | null>(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [facError, setFacError] = useState<string | null>(null)
  const [facRequestActive, setFacRequestActive] = useState(false)
  const [optimizing, setOptimizing] = useState(false)
  const [optError, setOptError] = useState<string | null>(null)

  // Request counters: a response is applied only if it belongs to the latest request.
  const routeReq = useRef(0)
  const optReq = useRef(0)
  const pollTimer = useRef<number | null>(null)

  const stopPolling = () => {
    if (pollTimer.current) window.clearTimeout(pollTimer.current)
    pollTimer.current = null
  }

  const loadFacilities = useCallback(async (routeId: number, reqId: number, attempt = 0) => {
    stopPolling()
    setFacRequestActive(true)
    setFacError(null)
    try {
      const data = await placesApi.nearRoute(routeId)
      if (reqId !== routeReq.current) return
      setFacilityData(data)
      if (!data.coverage.complete && attempt < MAX_POLLS) {
        pollTimer.current = window.setTimeout(() => loadFacilities(routeId, reqId, attempt + 1), POLL_MS)
      }
    } catch (e) {
      if (reqId === routeReq.current) setFacError((e as Error).message)
    } finally {
      if (reqId === routeReq.current) setFacRequestActive(false)
    }
  }, [setFacilityData])

  const planRoute = useCallback(async () => {
    if (!sourceLoc || !destLoc) return
    const reqId = ++routeReq.current
    stopPolling()
    clearDerived()                 // old route, facilities and results disappear immediately
    setSelected(null)
    setRouteError(null)
    setOptError(null)
    setRouteLoading(true)
    try {
      const r = await routesApi.plan(
        { query: sourceLoc.label, lat: sourceLoc.lat, lon: sourceLoc.lon },
        { query: destLoc.label, lat: destLoc.lat, lon: destLoc.lon },
      )
      if (reqId !== routeReq.current) return
      setRoute(r)
      loadFacilities(r.id, reqId)
    } catch (e) {
      if (reqId === routeReq.current) setRouteError((e as Error).message)
    } finally {
      if (reqId === routeReq.current) setRouteLoading(false)
    }
  }, [sourceLoc, destLoc, clearDerived, setRoute, loadFacilities])

  // Plan automatically whenever a new start/destination pair has been chosen.
  useEffect(() => {
    if (sourceLoc && destLoc && !route) planRoute()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceLoc, destLoc])

  // Coming back to this page with a route whose facilities were still loading: resume.
  useEffect(() => {
    if (route && facilityMeta && !facilityMeta.coverage.complete) loadFacilities(route.id, routeReq.current)
    return () => { stopPolling(); routeReq.current++; optReq.current++ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const optimize = async () => {
    if (!route || !vehicle) return
    const id = ++optReq.current
    setOptimizing(true)
    setOptError(null)
    setTripResult(null)
    try {
      const res = await optimizationApi.optimize({ vehicle_id: vehicle.id, route_id: route.id, preference, ...levels })
      if (id !== optReq.current) return
      setTripResult(res)
      navigate('/results')
    } catch (e) {
      if (id === optReq.current) setOptError((e as Error).message)
    } finally {
      if (id === optReq.current) setOptimizing(false)
    }
  }

  const filtered = useMemo(() => facilities.filter(f => matches(f, tab)), [facilities, tab])
  const counts = facilityMeta?.counts ?? {}
  const coverage = facilityMeta?.coverage
  const loadingMore = !!coverage && !coverage.complete

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex flex-wrap items-start gap-3 flex-shrink-0">
        <Link to="/" className="w-8 h-8 mt-1.5 bg-green-500 rounded-lg flex items-center justify-center font-bold text-white text-sm">S</Link>
        <div className="flex-1 min-w-[260px] grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_auto] gap-2 items-start">
          <LocationSearch placeholder="From…" value={sourceText} selected={sourceLoc}
            onTextChange={t => setSource(null, t)} onSelect={loc => setSource(loc, loc.label)} />
          <div className="hidden md:block text-gray-300 mt-3">→</div>
          <LocationSearch placeholder="To…" value={destText} selected={destLoc}
            onTextChange={t => setDest(null, t)} onSelect={loc => setDest(loc, loc.label)} />
          <button onClick={planRoute} disabled={!sourceLoc || !destLoc || routeLoading}
            className="px-4 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm whitespace-nowrap">
            {routeLoading ? 'Routing…' : route ? 'Re-plan' : 'Find route'}
          </button>
        </div>
        <Link to="/vehicles" className="text-sm text-gray-500 hover:text-gray-800 mt-3">Vehicles</Link>
      </header>

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        <aside className="md:w-[360px] flex-shrink-0 flex flex-col bg-white border-r border-gray-200 overflow-y-auto">
          {routeError && <div className="m-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{routeError}</div>}

          {route && (
            <section className="p-4 border-b border-gray-100 bg-green-50">
              <div className="text-xs text-gray-500 truncate" title={route.source.label}>From <b className="text-gray-800">{route.source.label}</b></div>
              <div className="text-xs text-gray-500 truncate" title={route.destination.label}>To <b className="text-gray-800">{route.destination.label}</b></div>
              <div className="flex gap-6 mt-2">
                <div><div className="font-bold text-lg text-gray-900">{formatKm(route.distance_km)}</div><div className="text-xs text-gray-500">Road distance</div></div>
                <div><div className="font-bold text-lg text-gray-900">{formatDuration(route.duration_min)}</div><div className="text-xs text-gray-500">Driving time</div></div>
              </div>
              <div className="text-[11px] text-gray-400 mt-1">Route by OSRM (OpenStreetMap road network)</div>
            </section>
          )}

          <section className="p-4 border-b border-gray-100">
            <h3 className="font-semibold text-sm text-gray-700 mb-2">Vehicle &amp; current level</h3>
            <VehiclePanel />
            <div className="mt-3">
              <div className="text-xs text-gray-500 mb-1">Optimise for</div>
              <div className="grid grid-cols-2 gap-1 bg-gray-100 p-1 rounded-lg text-xs">
                {(['cheapest', 'fewest_stops'] as const).map(p => (
                  <button key={p} onClick={() => setPreference(p)}
                    className={`py-1.5 rounded-md font-medium ${preference === p ? 'bg-white shadow text-gray-900' : 'text-gray-500'}`}>
                    {p === 'cheapest' ? 'Lowest cost' : 'Fewest stops'}
                  </button>
                ))}
              </div>
            </div>
            <button onClick={optimize} disabled={!route || !vehicle || optimizing}
              className="mt-3 w-full py-2.5 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-2">
              {optimizing && <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
              {optimizing ? 'Planning stops…' : !route ? 'Plan a route first' : !vehicle ? 'Select a vehicle' : 'Calculate range & stops'}
            </button>
            {optimizing && <p className="text-[11px] text-gray-500 mt-1">Long trips can take up to a minute while fuel-station data is loaded.</p>}
            {optError && <p className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">{optError}</p>}
          </section>

          {route && (
            <section className="flex-1 flex flex-col min-h-[300px]">
              <div className="px-3 pt-3 flex flex-wrap gap-1">
                {TABS.map(t => (
                  <button key={t} onClick={() => setTab(t)}
                    className={`px-2 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${tab === t ? 'bg-green-600 text-white' : 'text-gray-600 bg-gray-100 hover:bg-gray-200'}`}>
                    {t === 'all' ? 'All' : `${CATEGORY_ICON[t]} ${CATEGORY_LABEL[t]}`}
                    {t !== 'all' && facilityMeta && <span className="ml-1 opacity-75">{counts[t] ?? 0}</span>}
                  </button>
                ))}
              </div>

              <div className="px-3 pt-2 space-y-2">
                {coverage && (
                  <div className="text-[11px] text-gray-500 flex items-center gap-2">
                    {loadingMore && <span className="w-3 h-3 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />}
                    Facility data: {coverage.sections_ready}/{coverage.sections_total} route sections loaded
                    {facilityMeta && Object.keys(facilityMeta.sources).length > 0 && <> · {Object.keys(facilityMeta.sources).join(', ')}</>}
                  </div>
                )}
                {facilityMeta?.warnings.filter(w => !w.startsWith('Still loading')).map(w => (
                  <div key={w} className="p-2 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-xs">{w}</div>
                ))}
                {coverage && coverage.complete && coverage.sections_failed > 0 && route && (
                  <button onClick={() => loadFacilities(route.id, routeReq.current)} disabled={facRequestActive}
                    className="text-xs text-green-700 underline disabled:opacity-50">Retry loading missing sections</button>
                )}
                {facError && <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">{facError}</div>}
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {!facilityMeta && facRequestActive && <p className="text-sm text-gray-500 text-center py-6">Searching OpenStreetMap along your route…</p>}
                {facilityMeta && filtered.length === 0 && !loadingMore && (
                  <p className="text-sm text-gray-500 text-center py-6">No verified {tab === 'all' ? 'facility' : CATEGORY_LABEL[tab].toLowerCase()} found in this corridor.</p>
                )}
                {filtered.length > LIST_LIMIT && <p className="text-[11px] text-gray-400">Showing the first {LIST_LIMIT} of {filtered.length} in route order — use the filters to narrow down.</p>}
                {filtered.slice(0, LIST_LIMIT).map(f => (
                  <button key={f.id} onClick={() => setSelected(f)}
                    className={`w-full text-left p-2.5 border rounded-xl transition-all ${selected?.id === f.id ? 'border-green-400 bg-green-50' : 'border-gray-100 hover:bg-gray-50'}`}>
                    <div className="flex items-start gap-2">
                      <span className="text-lg">{CATEGORY_ICON[f.category] ?? '📍'}</span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-gray-900 truncate">{f.name}</div>
                        <div className="text-xs text-gray-500 truncate">{facilitySubtitle(f)}</div>
                        <div className="text-[11px] text-gray-400">
                          km {Math.round(f.km_along ?? 0)} · {formatKm(f.distance_from_route_km)} off route · {f.source_label ?? f.source}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          )}
          {!route && !routeLoading && !routeError && (
            <p className="p-6 text-sm text-gray-500 text-center">Choose a start and a destination to see the road route and facilities along it.</p>
          )}
        </aside>

        <main className="flex-1 relative min-h-[320px]">
          <RouteMap geometry={route?.geometry ?? []} facilities={filtered} onFacilityClick={setSelected}
            selectedId={selected?.id} />
          {routeLoading && (
            <div className="absolute inset-0 bg-white/60 flex items-center justify-center z-[500]">
              <div className="bg-white rounded-2xl p-5 shadow-xl flex items-center gap-3">
                <span className="w-6 h-6 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
                <span className="font-medium text-gray-800">Calculating road route…</span>
              </div>
            </div>
          )}
          {selected && (
            <div className="absolute bottom-4 left-4 right-4 z-[500] flex justify-center">
              <FacilityDetails f={selected} onClose={() => setSelected(null)} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
