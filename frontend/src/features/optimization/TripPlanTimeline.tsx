import type { OptimizationStop, TripResult } from '../../types'
import { FUEL_LABEL, formatDuration, formatINR, formatKm, formatPct, formatQty } from '../../utils/format'

function levels(map: Record<string, number> | null | undefined) {
  return Object.entries(map ?? {}).map(([ft, v]) => `${FUEL_LABEL[ft] ?? ft} ${formatPct(v)}`).join(' · ')
}

function StopCard({ stop, index, last }: { stop: OptimizationStop; index: number; last: boolean }) {
  const ext = (stop.extra || {}) as Record<string, string>
  const link = ext.osm_url || ext.ocm_url
  const chargeMin = stop.purchases.reduce((s, p) => s + p.charge_minutes, 0)
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="w-8 h-8 rounded-full bg-green-600 text-white flex items-center justify-center font-bold text-sm">{index + 1}</div>
        {!last && <div className="w-0.5 flex-1 bg-gray-200 my-1" />}
      </div>
      <div className="flex-1 pb-4 min-w-0">
        <div className="border border-gray-200 rounded-xl p-3">
          <div className="flex justify-between gap-2">
            <div className="min-w-0">
              <div className="font-semibold text-sm text-gray-900 truncate">{stop.name}</div>
              <div className="text-xs text-gray-400">
                km {Math.round(stop.km_along)} · +{formatKm(stop.detour_km)} detour · {link
                  ? <a href={link} target="_blank" rel="noreferrer" className="underline">{stop.source_label ?? stop.source}</a>
                  : stop.source_label ?? stop.source}
              </div>
            </div>
            <div className="text-sm font-bold text-green-700 whitespace-nowrap">{formatINR(stop.cost_inr)}</div>
          </div>
          <div className="mt-2 space-y-1">
            {stop.purchases.map(p => (
              <div key={p.fuel_type} className="text-xs bg-gray-50 rounded-lg px-2 py-1 flex justify-between">
                <span>{p.fuel_type === 'electric' ? 'Charge' : 'Buy'} <b>{formatQty(p.quantity, p.unit)}</b> {FUEL_LABEL[p.fuel_type]}
                  {' '}→ {formatPct(p.level_after_pct)}</span>
                <span>{formatINR(p.cost_inr)}</span>
              </div>
            ))}
          </div>
          <div className="text-[11px] text-gray-500 mt-2">
            Expected on arrival: {levels(stop.expected_arrival_pct)}
            <span className="text-gray-400"> (worst case {levels(stop.arrival_pct)})</span>
            {chargeMin > 0 && <> · charging ≈ {formatDuration(chargeMin)}{stop.charging_power_kw ? ` at ${Math.round(stop.charging_power_kw)} kW` : ' (charger power unknown, 30 kW assumed)'}</>}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">{stop.reason}</p>
          {stop.fuel_types_inferred && <p className="text-[11px] text-amber-700 mt-1">Fuel types not tagged in OpenStreetMap — petrol/diesel assumed.</p>}
        </div>
      </div>
    </div>
  )
}

export default function TripPlanTimeline({ result }: { result: TripResult }) {
  const opt = result.optimization
  const stops = opt.stops
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      <h2 className="font-bold text-gray-900 mb-4">🛣️ Stop plan</h2>
      <div className="text-xs text-gray-500 mb-3">Start: <b className="text-gray-800">{result.route.source.label}</b> · {levels(
        Object.fromEntries(result.vehicle.fuels.map(f => [f.fuel_type, f.current_pct])))}</div>
      {stops.length === 0 ? (
        <div className="text-center py-5 text-gray-500 border border-dashed border-gray-200 rounded-xl mb-3 text-sm">
          No stop needed — the trip fits within your current safe range.
        </div>
      ) : stops.map((s, i) => <StopCard key={`${s.facility_id}-${i}`} stop={s} index={i} last={i === stops.length - 1} />)}
      <div className="text-xs text-gray-500 mt-1">Destination: <b className="text-gray-800">{result.route.destination.label}</b>
        {' '}· expected left: {levels(opt.arrival_pct)}</div>
      <div className="mt-4 pt-3 border-t border-gray-100 grid grid-cols-3 gap-2 text-center text-xs">
        <div><div className="font-bold text-base text-gray-900">{stops.length}</div><div className="text-gray-400">Stops</div></div>
        <div><div className="font-bold text-base text-gray-900">{formatDuration(opt.stop_minutes)}</div><div className="text-gray-400">At stops</div></div>
        <div><div className="font-bold text-base text-gray-900">{formatKm(Math.max(0, opt.driven_km - result.route.distance_km))}</div><div className="text-gray-400">Total detour</div></div>
      </div>
    </div>
  )
}
