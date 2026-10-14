// Shapes returned by the SmartRoute API.

export interface GeoLocation {
  label: string
  lat: number
  lon: number
}

export interface PlaceResult extends GeoLocation {
  name: string
  kind: string
  state?: string | null
  source: string
}

export type VehicleFuelType = 'petrol' | 'diesel' | 'cng' | 'electric' | 'bifuel'

export interface Vehicle {
  id: number
  name: string
  vehicle_type: string
  fuel_type: VehicleFuelType | string
  secondary_fuel_type?: string | null
  tank_capacity?: number | null
  efficiency?: number | null
  current_fuel_pct?: number | null
  cng_tank_capacity?: number | null
  cng_efficiency?: number | null
  current_cng_pct?: number | null
  battery_capacity_kwh?: number | null
  ev_efficiency?: number | null
  current_battery_pct?: number | null
}

export interface FuelRange {
  fuel_type: string
  label: string
  capacity: number
  unit: string
  current_pct: number
  current_units: number
  efficiency: number
  efficiency_unit: string
  price_per_unit: number
  cost_per_km: number
  usable_range_km: number
  refill_range_km: number
  max_fill_pct: number
}

export interface RangeSummary {
  vehicle_id: number
  name: string
  safety_factor: number
  total_usable_range_km: number
  fuels: FuelRange[]
}

export interface Route {
  id: number
  source: GeoLocation
  destination: GeoLocation
  source_name: string
  destination_name: string
  distance_km: number
  duration_min: number
  geometry: [number, number][]
  provider: string
}

export interface Facility {
  id: number
  name: string
  category: string
  latitude: number
  longitude: number
  address?: string
  fuel_types?: string[]
  fuel_types_inferred?: boolean
  connector_types?: string[]
  charging_power_kw?: number | null
  num_chargers?: number | null
  km_along?: number
  distance_from_route_km?: number
  detour_km?: number
  detour_min?: number
  source: string
  source_label?: string
  extra?: Record<string, unknown>
}

export interface Coverage {
  sections_total: number
  sections_ready: number
  sections_failed: number
  sections_pending: number
  complete: boolean
  external_enabled: boolean
  failed_ranges_km: [number, number][]
}

export interface NearRouteResponse {
  route_id: number | null
  facilities: Facility[]
  total: number
  counts: Record<string, number>
  coverage: Coverage
  sources: Record<string, number>
  warnings: string[]
}

export interface Purchase {
  fuel_type: string
  quantity: number
  unit: string
  cost_inr: number
  level_after_pct: number
  charge_minutes: number
}

export interface OptimizationStop {
  facility_id: number
  name: string
  latitude: number
  longitude: number
  km_along: number
  detour_km: number
  source: string
  source_label?: string
  purchases: Purchase[]
  arrival_pct: Record<string, number>
  expected_arrival_pct: Record<string, number>
  departure_pct: Record<string, number>
  reason: string
  charging_power_kw?: number | null
  address?: string
  cost_inr: number
  fuel_types_inferred?: boolean
  extra?: Record<string, unknown>
}

export interface Leg {
  from_name: string
  to_name: string
  start_km: number
  end_km: number
  distance_km: number
  fuel_km: Record<string, number>
  cost_inr: number
}

export interface FuelBreakdown {
  km: number
  quantity: number
  unit: string
  cost_inr: number
}

export interface Baseline {
  cost_inr: number
  description: string
}

export interface OptimizationResult {
  feasible: boolean
  preference: 'cheapest' | 'fewest_stops'
  message: string
  stops: OptimizationStop[]
  legs: Leg[]
  energy_cost_inr: number | null
  purchase_cost_inr: number | null
  fuel_breakdown: Record<string, FuelBreakdown>
  driven_km: number
  stop_minutes: number
  arrival_pct: Record<string, number>
  max_reachable_km: number
  baseline: Baseline | null
  savings_inr: number | null
  savings_pct: number | null
  energy_estimates?: { fuel_type: string; label: string; cost_inr: number; quantity: number; unit: string }[]
}

export interface TripResult {
  trip_id: number
  route: Route
  vehicle: RangeSummary & { fuel_type: string; vehicle_type: string }
  range_check: { trip_km: number; usable_range_km: number; needs_stop: boolean; explanation: string }
  optimization: OptimizationResult
  alternative: {
    preference: 'cheapest' | 'fewest_stops'
    stops_count: number
    energy_cost_inr: number
    purchase_cost_inr: number
    stop_minutes: number
  } | null
  facilities: { candidates: number; coverage: Coverage; sources: Record<string, number> }
  warnings: string[]
  assumptions: { safety_factor: number; prices: Record<string, number>; note: string }
}

export interface Levels {
  current_fuel_pct?: number
  current_cng_pct?: number
  current_battery_pct?: number
}
