import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTrip } from '../hooks/useTrip'
import { vehiclesApi } from '../services/api'
import type { Levels, RangeSummary, Vehicle } from '../types'
import { formatKm, VEHICLE_FUEL_LABEL } from '../utils/format'

const SLIDERS: { key: keyof Levels; label: string; fuels: string[]; color: string }[] = [
  { key: 'current_cng_pct', label: 'CNG level', fuels: ['bifuel'], color: 'accent-blue-600' },
  { key: 'current_fuel_pct', label: 'Fuel level', fuels: ['petrol', 'diesel', 'cng', 'bifuel'], color: 'accent-green-600' },
  { key: 'current_battery_pct', label: 'Battery level', fuels: ['electric'], color: 'accent-blue-600' },
]

/** Vehicle choice, current fuel/battery levels and the resulting usable range. */
export default function VehiclePanel() {
  const { vehicle, setVehicle, levels, setLevels } = useTrip()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [range, setRange] = useState<RangeSummary | null>(null)
  const [rangeError, setRangeError] = useState<string | null>(null)
  const req = useRef(0)

  useEffect(() => { vehiclesApi.list().then(setVehicles).catch(() => setVehicles([])) }, [])

  useEffect(() => {
    if (!vehicle) { setRange(null); return }
    const id = ++req.current
    const t = setTimeout(() => {
      vehiclesApi.range(vehicle.id, levels)
        .then(r => { if (id === req.current) { setRange(r); setRangeError(null) } })
        .catch(e => { if (id === req.current) setRangeError(e.message) })
    }, 250)
    return () => clearTimeout(t)
  }, [vehicle, levels])

  return (
    <div className="space-y-3">
      <select
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        value={vehicle?.id ?? ''}
        onChange={e => setVehicle(vehicles.find(v => v.id === Number(e.target.value)) ?? null)}
      >
        <option value="">Select a vehicle…</option>
        {vehicles.map(v => (
          <option key={v.id} value={v.id}>{v.name} — {VEHICLE_FUEL_LABEL[v.fuel_type] ?? v.fuel_type}</option>
        ))}
      </select>
      {vehicles.length === 0 && (
        <p className="text-xs text-gray-500">No vehicles yet — <Link to="/vehicles" className="underline">add one</Link>.</p>
      )}

      {vehicle && SLIDERS.filter(s => s.fuels.includes(vehicle.fuel_type)).map(s => {
        const label = vehicle.fuel_type === 'bifuel' && s.key === 'current_fuel_pct' ? 'Petrol level' : s.label
        const value = levels[s.key] ?? 100
        return (
          <div key={s.key}>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>{label}</span><span className="font-medium text-gray-800">{Math.round(value)}%</span>
            </div>
            <input type="range" min={0} max={100} step={5} value={value} aria-label={label}
              className={`w-full ${s.color}`}
              onChange={e => setLevels({ ...levels, [s.key]: Number(e.target.value) })} />
          </div>
        )
      })}

      {vehicle && range && (
        <div className="rounded-lg bg-gray-50 border border-gray-100 p-3 text-xs space-y-1">
          {range.fuels.map(f => (
            <div key={f.fuel_type} className="flex justify-between">
              <span className="text-gray-500">
                {f.label}: {Number(f.current_units.toFixed(1))} {f.unit} × {f.efficiency} {f.efficiency_unit}
              </span>
              <span className="font-medium text-gray-800">{formatKm(f.usable_range_km)}</span>
            </div>
          ))}
          <div className="flex justify-between border-t border-gray-200 pt-1 mt-1">
            <span className="font-semibold text-gray-700">Safe range now</span>
            <span className="font-bold text-green-700">{formatKm(range.total_usable_range_km)}</span>
          </div>
          <p className="text-[11px] text-gray-400">
            Includes a {Math.round((1 - range.safety_factor) * 100)}% safety margin on rated efficiency.
          </p>
        </div>
      )}
      {rangeError && <p className="text-xs text-red-600">{rangeError}</p>}
    </div>
  )
}
