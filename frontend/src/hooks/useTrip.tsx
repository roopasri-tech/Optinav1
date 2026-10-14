import { createContext, ReactNode, useCallback, useContext, useRef, useState } from 'react'
import type { Facility, GeoLocation, Levels, NearRouteResponse, Route, TripResult, Vehicle } from '../types'

/**
 * Shared trip state (in memory only - nothing is restored from browser storage,
 * so an old trip can never reappear unexpectedly).
 *
 * Rule: whenever the source or destination changes, everything derived from the
 * old route (route, facilities, optimisation result) is cleared immediately.
 */
interface TripState {
  sourceLoc: GeoLocation | null
  destLoc: GeoLocation | null
  sourceText: string
  destText: string
  vehicle: Vehicle | null
  levels: Levels
  preference: 'cheapest' | 'fewest_stops'
  route: Route | null
  facilities: Facility[]
  facilityMeta: Omit<NearRouteResponse, 'facilities'> | null
  tripResult: TripResult | null

  setSource: (loc: GeoLocation | null, text: string) => void
  setDest: (loc: GeoLocation | null, text: string) => void
  setVehicle: (v: Vehicle | null) => void
  setLevels: (l: Levels) => void
  setPreference: (p: 'cheapest' | 'fewest_stops') => void
  setRoute: (r: Route | null) => void
  setFacilityData: (d: NearRouteResponse | null) => void
  setTripResult: (r: TripResult | null) => void
  clearDerived: () => void
  reset: () => void
}

const TripContext = createContext<TripState | null>(null)

export function levelsFromVehicle(v: Vehicle | null): Levels {
  if (!v) return {}
  if (v.fuel_type === 'electric') return { current_battery_pct: v.current_battery_pct ?? 100 }
  if (v.fuel_type === 'bifuel') return { current_cng_pct: v.current_cng_pct ?? 100, current_fuel_pct: v.current_fuel_pct ?? 100 }
  return { current_fuel_pct: v.current_fuel_pct ?? 100 }
}

export function TripProvider({ children }: { children: ReactNode }) {
  const [sourceLoc, setSourceLoc] = useState<GeoLocation | null>(null)
  const [destLoc, setDestLoc] = useState<GeoLocation | null>(null)
  const [sourceText, setSourceText] = useState('')
  const [destText, setDestText] = useState('')
  const [vehicle, setVehicleState] = useState<Vehicle | null>(null)
  const [levels, setLevels] = useState<Levels>({})
  const [preference, setPreference] = useState<'cheapest' | 'fewest_stops'>('cheapest')
  const [route, setRoute] = useState<Route | null>(null)
  const [facilities, setFacilities] = useState<Facility[]>([])
  const [facilityMeta, setFacilityMeta] = useState<Omit<NearRouteResponse, 'facilities'> | null>(null)
  const [tripResult, setTripResult] = useState<TripResult | null>(null)

  const clearDerived = useCallback(() => {
    setRoute(null)
    setFacilities([])
    setFacilityMeta(null)
    setTripResult(null)
  }, [])

  const srcRef = useRef<GeoLocation | null>(null)
  const dstRef = useRef<GeoLocation | null>(null)
  const sameLoc = (a: GeoLocation | null, b: GeoLocation | null) => a?.lat === b?.lat && a?.lon === b?.lon

  const setSource = useCallback((loc: GeoLocation | null, text: string) => {
    setSourceText(text)
    if (!sameLoc(srcRef.current, loc)) clearDerived()
    srcRef.current = loc
    setSourceLoc(loc)
  }, [clearDerived])

  const setDest = useCallback((loc: GeoLocation | null, text: string) => {
    setDestText(text)
    if (!sameLoc(dstRef.current, loc)) clearDerived()
    dstRef.current = loc
    setDestLoc(loc)
  }, [clearDerived])

  const setVehicle = useCallback((v: Vehicle | null) => {
    setVehicleState(v)
    setLevels(levelsFromVehicle(v))
    setTripResult(null)
  }, [])

  const setFacilityData = useCallback((d: NearRouteResponse | null) => {
    if (!d) { setFacilities([]); setFacilityMeta(null); return }
    const { facilities: list, ...meta } = d
    setFacilities(list)
    setFacilityMeta(meta)
  }, [])

  const reset = useCallback(() => {
    srcRef.current = null
    dstRef.current = null
    setSourceLoc(null); setDestLoc(null); setSourceText(''); setDestText('')
    clearDerived()
  }, [clearDerived])

  return (
    <TripContext.Provider value={{
      sourceLoc, destLoc, sourceText, destText, vehicle, levels, preference, route, facilities, facilityMeta,
      tripResult, setSource, setDest, setVehicle, setLevels, setPreference, setRoute, setFacilityData,
      setTripResult, clearDerived, reset,
    }}>
      {children}
    </TripContext.Provider>
  )
}

export function useTrip(): TripState {
  const ctx = useContext(TripContext)
  if (!ctx) throw new Error('useTrip must be used within TripProvider')
  return ctx
}
