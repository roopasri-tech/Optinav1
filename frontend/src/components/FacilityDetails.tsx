import type { Facility } from '../types'
import { CATEGORY_LABEL, FUEL_LABEL, formatKm } from '../utils/format'

export const CATEGORY_ICON: Record<string, string> = {
  fuel: '⛽', cng: '🔵', ev: '⚡', restaurant: '🍽️', parking: '🅿️', restroom: '🚻',
}

export function fuelSummary(f: Facility): string {
  const list = (f.fuel_types || []).map(t => FUEL_LABEL[t] ?? t).join(', ')
  return f.fuel_types_inferred ? `${list || 'Fuel'} (assumed)` : list || 'Fuel types not tagged'
}

export function facilitySubtitle(f: Facility): string {
  if (f.category === 'fuel') return fuelSummary(f)
  if (f.category === 'ev') {
    const kw = f.charging_power_kw ? `${Math.round(f.charging_power_kw)} kW` : 'power unknown'
    return [kw, ...(f.connector_types || [])].join(' · ')
  }
  const kind = (f.extra?.kind as string | undefined)?.replace('_', ' ')
  return kind ? kind.charAt(0).toUpperCase() + kind.slice(1) : CATEGORY_LABEL[f.category] ?? f.category
}

export default function FacilityDetails({ f, onClose }: { f: Facility; onClose: () => void }) {
  const extra = (f.extra || {}) as Record<string, string | boolean | undefined>
  const link = (extra.osm_url || extra.ocm_url) as string | undefined
  return (
    <div className="bg-white rounded-2xl shadow-xl border border-gray-200 p-4 max-w-md w-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-gray-900">{CATEGORY_ICON[f.category]} {f.name}</div>
          <div className="text-sm text-gray-500 mt-0.5">{facilitySubtitle(f)}</div>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600" aria-label="Close">✕</button>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {f.km_along != null && <><dt className="text-gray-400">Along route</dt><dd>km {Math.round(f.km_along)}</dd></>}
        {f.distance_from_route_km != null && <><dt className="text-gray-400">Off route</dt><dd>{formatKm(f.distance_from_route_km)}</dd></>}
        {f.detour_km != null && <><dt className="text-gray-400">Approx. detour</dt><dd>+{formatKm(f.detour_km)}{f.detour_min ? ` (~${f.detour_min} min)` : ''}</dd></>}
        {f.address && <><dt className="text-gray-400">Address</dt><dd>{f.address}</dd></>}
        {extra.opening_hours && <><dt className="text-gray-400">Hours</dt><dd>{String(extra.opening_hours)}</dd></>}
        {extra.phone && <><dt className="text-gray-400">Phone</dt><dd>{String(extra.phone)}</dd></>}
        {extra.cuisine && <><dt className="text-gray-400">Cuisine</dt><dd>{String(extra.cuisine)}</dd></>}
        <dt className="text-gray-400">Source</dt>
        <dd>{link ? <a className="text-green-700 underline" href={link} target="_blank" rel="noreferrer">{f.source_label ?? f.source}</a> : (f.source_label ?? f.source)}</dd>
      </dl>
      {extra.website && (
        <a className="mt-2 inline-block text-xs text-green-700 underline" href={String(extra.website)} target="_blank" rel="noreferrer">Website</a>
      )}
      {f.fuel_types_inferred && (
        <p className="mt-2 text-[11px] text-amber-700">Fuel types are not tagged in OpenStreetMap for this station; petrol/diesel is assumed.</p>
      )}
    </div>
  )
}
