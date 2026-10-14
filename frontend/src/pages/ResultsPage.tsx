import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import CostComparison from '../features/optimization/CostComparison'
import TripPlanTimeline from '../features/optimization/TripPlanTimeline'
import { useTrip } from '../hooks/useTrip'
import RouteMap from '../map/RouteMap'
import { FUEL_LABEL, formatDuration, formatINR, formatKm, formatQty } from '../utils/format'

export default function ResultsPage() {
  const navigate = useNavigate()
  const { tripResult, reset } = useTrip()

  useEffect(() => { if (!tripResult) navigate('/planner', { replace: true }) }, [tripResult, navigate])
  if (!tripResult) return null

  const { route, optimization: opt, range_check: rc, vehicle } = tripResult

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-green-500 rounded-lg flex items-center justify-center font-bold text-white text-sm">S</div>
            <span className="font-bold text-gray-900">SmartRoute</span>
          </Link>
          <button onClick={() => navigate('/planner')}
            className="px-4 py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50">← Edit trip</button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 space-y-6">
        <div className={`rounded-2xl p-6 text-white ${opt.feasible ? 'bg-gradient-to-r from-green-600 to-green-700' : 'bg-gradient-to-r from-gray-700 to-gray-800'}`}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-bold mb-1">{opt.feasible ? 'Your trip plan' : 'Trip cannot be completed as planned'}</h1>
              <div className="text-sm opacity-90">{route.source.label} → {route.destination.label}</div>
              <div className="text-xs opacity-75 mt-1">{vehicle.name}</div>
            </div>
            <div className="flex gap-6 text-center">
              <div><div className="text-2xl font-bold">{formatKm(route.distance_km)}</div><div className="text-xs opacity-75">Road distance</div></div>
              <div><div className="text-2xl font-bold">{formatDuration(route.duration_min)}</div><div className="text-xs opacity-75">Driving time</div></div>
              <div><div className="text-2xl font-bold">{opt.feasible ? opt.stops.length : '—'}</div><div className="text-xs opacity-75">Stops</div></div>
              <div><div className="text-2xl font-bold">{opt.feasible ? formatINR(opt.energy_cost_inr) : '—'}</div><div className="text-xs opacity-75">Fuel/energy cost</div></div>
            </div>
          </div>
        </div>

        <div className={`rounded-2xl border p-4 text-sm ${rc.needs_stop ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-green-50 border-green-200 text-green-900'}`}>
          <b>Range check:</b> {rc.explanation}
          <div className="text-xs mt-1 opacity-80">
            {vehicle.fuels.map(f => `${f.label}: ${Math.round(f.current_pct)}% = ${Number(f.current_units.toFixed(1))} ${f.unit} → ${formatKm(f.usable_range_km)} safe range`).join(' · ')}
          </div>
        </div>

        {tripResult.warnings.length > 0 && (
          <div className="space-y-2">
            {tripResult.warnings.map(w => <div key={w} className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-sm">{w}</div>)}
          </div>
        )}

        {!opt.feasible && (
          <div className="bg-white rounded-2xl border border-red-200 p-6 space-y-3">
            <h2 className="font-bold text-red-700">Why no plan was produced</h2>
            <p className="text-sm text-gray-700">{opt.message}</p>
            {opt.energy_estimates && (
              <div className="text-sm text-gray-700">
                <div className="font-medium mb-1">For reference, energy needed for the full {formatKm(route.distance_km)} (not a plan):</div>
                <ul className="list-disc ml-5 text-xs text-gray-600">
                  {opt.energy_estimates.map(e => (
                    <li key={e.fuel_type}>Entirely on {FUEL_LABEL[e.fuel_type]}: {formatQty(e.quantity, e.unit)} ≈ {formatINR(e.cost_inr)}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-gray-500">Try a higher starting fuel/charge level, another vehicle, or try again in a minute if facility data was still loading.</p>
          </div>
        )}

        <div className="grid lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3 space-y-6">
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden h-[420px]">
              <RouteMap geometry={route.geometry} stops={opt.stops} />
            </div>
            <CostComparison result={tripResult} />
          </div>
          <div className="lg:col-span-2">
            {opt.feasible && <TripPlanTimeline result={tripResult} />}
          </div>
        </div>

        <div className="flex justify-center gap-4 pb-6">
          <button onClick={() => { reset(); navigate('/') }}
            className="px-6 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700">Plan another trip</button>
          <button onClick={() => navigate('/planner')}
            className="px-6 py-3 border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50">Modify this trip</button>
        </div>
      </div>
    </div>
  )
}
