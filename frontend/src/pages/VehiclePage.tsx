import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { vehiclesApi } from '../services/api'
import type { Vehicle } from '../types'

const FUEL_TYPES = ['petrol', 'diesel', 'cng', 'electric', 'bifuel']
const FUEL_LABELS: Record<string, string> = {
  petrol: 'Petrol',
  diesel: 'Diesel',
  cng: 'CNG',
  electric: 'Electric (EV)',
  bifuel: 'Bi-fuel (CNG + Petrol)',
}

const FUEL_ICONS: Record<string, string> = {
  petrol: '⛽',
  diesel: '🛢️',
  cng: '🔵',
  electric: '⚡',
  bifuel: '🔵⛽',
}

interface FormData {
  name: string
  vehicle_type: string
  fuel_type: string
  tank_capacity: string
  efficiency: string
  current_fuel_pct: string
  cng_tank_capacity: string
  cng_efficiency: string
  current_cng_pct: string
  battery_capacity_kwh: string
  ev_efficiency: string
  current_battery_pct: string
}

const DEFAULT_FORM: FormData = {
  name: '',
  vehicle_type: 'car',
  fuel_type: 'petrol',
  tank_capacity: '45',
  efficiency: '14',
  current_fuel_pct: '80',
  cng_tank_capacity: '',
  cng_efficiency: '',
  current_cng_pct: '80',
  battery_capacity_kwh: '',
  ev_efficiency: '',
  current_battery_pct: '80',
}

function toNumber(s: string): number | undefined {
  const n = parseFloat(s)
  return isNaN(n) ? undefined : n
}

export default function VehiclePage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<FormData>(DEFAULT_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await vehiclesApi.list()
      setVehicles(data)
    } catch {
      setError('Failed to load vehicles')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const isBifuel = form.fuel_type === 'bifuel'
  const isCngOnly = form.fuel_type === 'cng'
  const isEV = form.fuel_type === 'electric'

  const handleOpen = (v?: Vehicle) => {
    if (v) {
      setEditId(v.id)
      setForm({
        name: v.name,
        vehicle_type: v.vehicle_type,
        fuel_type: v.fuel_type,
        tank_capacity: String(v.tank_capacity ?? 45),
        efficiency: String(v.efficiency ?? 14),
        current_fuel_pct: String(v.current_fuel_pct ?? 80),
        cng_tank_capacity: String(v.cng_tank_capacity ?? ''),
        cng_efficiency: String(v.cng_efficiency ?? ''),
        current_cng_pct: String(v.current_cng_pct ?? 80),
        battery_capacity_kwh: String(v.battery_capacity_kwh ?? ''),
        ev_efficiency: String(v.ev_efficiency ?? ''),
        current_battery_pct: String(v.current_battery_pct ?? 80),
      })
    } else {
      setEditId(null)
      setForm(DEFAULT_FORM)
    }
    setError(null)
    setShowForm(true)
  }

  const handleSave = async () => {
    if (!form.name.trim()) { setError('Vehicle name is required'); return }
    setSaving(true)
    setError(null)
    try {
      const payload: Partial<Vehicle> = {
        name: form.name.trim(),
        vehicle_type: form.vehicle_type,
        fuel_type: form.fuel_type,
        tank_capacity: toNumber(form.tank_capacity),
        efficiency: toNumber(form.efficiency),
        current_fuel_pct: toNumber(form.current_fuel_pct),
        cng_tank_capacity: toNumber(form.cng_tank_capacity),
        cng_efficiency: toNumber(form.cng_efficiency),
        current_cng_pct: toNumber(form.current_cng_pct),
        battery_capacity_kwh: toNumber(form.battery_capacity_kwh),
        ev_efficiency: toNumber(form.ev_efficiency),
        current_battery_pct: toNumber(form.current_battery_pct),
      }
      if (editId !== null) {
        await vehiclesApi.update(editId, payload)
      } else {
        await vehiclesApi.create(payload)
      }
      setShowForm(false)
      load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save vehicle')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await vehiclesApi.delete(id)
      setDeleteConfirm(null)
      load()
    } catch {
      setError('Failed to delete vehicle')
    }
  }

  const field = (label: string, key: keyof FormData, type = 'text', placeholder = '') => (
    <div>
      <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{label}</label>
      <input
        type={type}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        placeholder={placeholder}
        value={form[key]}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
      />
    </div>
  )

  return (
    <div className="min-h-screen bg-[#07130f] text-white">
      {/* Header */}
      <header className="bg-[#0b1c15] border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-3">
  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-green-400 font-black text-[#07130f]">
    O
  </div>
  <div>
    <div className="text-lg font-bold tracking-tight text-gray-900">
      Opti<span className="text-green-600">Nav</span>
    </div>
    <div className="text-[10px] uppercase tracking-wider text-gray-500">
      Optimize every journey.
    </div>
  </div>
</Link>
          <span className="text-gray-300">/</span>
          <Link to="/planner" className="text-gray-500 hover:text-gray-800 text-sm">Planner</Link>
          <span className="text-gray-300">/</span>
          <span className="text-gray-600 font-medium">My Vehicles</span>
        </div>
        <button
          onClick={() => handleOpen()}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors text-sm"
        >
          <span>+</span> Add Vehicle
        </button>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : vehicles.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">🚗</div>
            <h2 className="text-xl font-semibold text-gray-700 mb-2">No vehicles yet</h2>
            <p className="text-gray-400 mb-6">Add your vehicles to get personalized trip optimization</p>
            <button
              onClick={() => handleOpen()}
              className="px-6 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 transition-colors"
            >
              Add Your First Vehicle
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {vehicles.map(v => (
              <div key={v.id} className="bg-[#10251b] rounded-2xl border border-white/10 p-5 hover:border-green-400/40 transition-all">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="text-2xl">{FUEL_ICONS[v.fuel_type] || '🚗'}</div>
                    <div>
                      <h3 className="font-semibold text-red-500">{v.name}</h3>
                      <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">
                        {FUEL_LABELS[v.fuel_type] || v.fuel_type}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleOpen(v)}
                      className="p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                      title="Edit"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => setDeleteConfirm(v.id)}
                      className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                      title="Delete"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
                  {v.fuel_type !== 'electric' && (
                    <>
                      <div className="flex items-center gap-1">
                        <span>Tank:</span>
                        <span className="font-medium text-gray-700">{v.tank_capacity} {v.fuel_type === 'cng' ? 'kg' : 'L'}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span>Mileage:</span>
                        <span className="font-medium text-gray-700">{v.efficiency} {v.fuel_type === 'cng' ? 'km/kg' : 'km/L'}</span>
                      </div>
                      <div className="col-span-2">
                        <div className="flex items-center justify-between mb-1">
                          <span>{v.fuel_type === 'bifuel' ? 'Petrol level' : 'Fuel level'}</span>
                          <span className="font-medium text-gray-700">{v.current_fuel_pct}%</span>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-green-500 rounded-full transition-all"
                            style={{ width: `${v.current_fuel_pct}%` }}
                          />
                        </div>
                      </div>
                    </>
                  )}
                  {v.fuel_type === 'bifuel' && (
                    <>
                      <div className="flex items-center gap-1"><span>CNG tank:</span>
                        <span className="font-medium text-gray-700">{v.cng_tank_capacity} kg</span></div>
                      <div className="flex items-center gap-1"><span>CNG mileage:</span>
                        <span className="font-medium text-gray-700">{v.cng_efficiency} km/kg</span></div>
                      <div className="col-span-2">
                        <div className="flex items-center justify-between mb-1"><span>CNG level</span>
                          <span className="font-medium text-blue-600">{v.current_cng_pct ?? 100}%</span></div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500 rounded-full" style={{ width: `${v.current_cng_pct ?? 100}%` }} />
                        </div>
                      </div>
                    </>
                  )}
                  {v.fuel_type === 'electric' && (
                    <>
                      <div className="flex items-center gap-1">
                        <span>Battery:</span>
                        <span className="font-medium text-gray-700">{v.battery_capacity_kwh} kWh</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span>Efficiency:</span>
                        <span className="font-medium text-gray-700">{v.ev_efficiency} km/kWh</span>
                      </div>
                      <div className="col-span-2">
                        <div className="flex items-center justify-between mb-1">
                          <span>Charge level</span>
                          <span className="font-medium text-blue-600">{v.current_battery_pct}%</span>
                        </div>
                        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${v.current_battery_pct}%` }}
                          />
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal Form */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-100 flex items-center justify-between">
              <h2 className="font-bold text-lg text-gray-900">
                {editId !== null ? 'Edit Vehicle' : 'Add Vehicle'}
              </h2>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 space-y-4">
              {field('Vehicle Name', 'name', 'text', 'e.g. My Wagon R')}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Type</label>
                  <select
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                    value={form.vehicle_type}
                    onChange={e => setForm(f => ({ ...f, vehicle_type: e.target.value }))}
                  >
                    <option value="car">Car</option>
                    <option value="bike">Bike / Scooter</option>
                    <option value="truck">Truck</option>
                    <option value="bus">Bus</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Fuel Type</label>
                  <select
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                    value={form.fuel_type}
                    onChange={e => setForm(f => ({ ...f, fuel_type: e.target.value }))}
                  >
                    {FUEL_TYPES.map(ft => (
                      <option key={ft} value={ft}>{FUEL_LABELS[ft]}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Petrol/Diesel/Bifuel fields */}
              {(form.fuel_type !== 'electric') && (
                <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl space-y-3">
                  <h3 className="text-sm font-semibold text-amber-800">
                    {isBifuel ? 'Petrol tank' : isCngOnly ? 'CNG tank' : FUEL_LABELS[form.fuel_type] + ' tank'}
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    {field(isCngOnly ? 'Tank size (kg)' : 'Tank size (L)', 'tank_capacity', 'number', isCngOnly ? '12' : '45')}
                    {field(isCngOnly ? 'Mileage (km/kg)' : 'Mileage (km/L)', 'efficiency', 'number', isCngOnly ? '25' : '14')}
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                      Current Level: {form.current_fuel_pct}%
                    </label>
                    <input
                      type="range" min="0" max="100" step="5"
                      className="w-full accent-green-600"
                      value={form.current_fuel_pct}
                      onChange={e => setForm(f => ({ ...f, current_fuel_pct: e.target.value }))}
                    />
                  </div>
                </div>
              )}

              {/* CNG fields (bifuel) */}
              {isBifuel && (
                <div className="p-4 bg-blue-50 border border-blue-100 rounded-xl space-y-3">
                  <h3 className="text-sm font-semibold text-blue-800">CNG Tank</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {field('CNG Tank (kg)', 'cng_tank_capacity', 'number', '12')}
                    {field('CNG Mileage (km/kg)', 'cng_efficiency', 'number', '25')}
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                      CNG Level: {form.current_cng_pct}%
                    </label>
                    <input
                      type="range" min="0" max="100" step="5"
                      className="w-full accent-blue-600"
                      value={form.current_cng_pct}
                      onChange={e => setForm(f => ({ ...f, current_cng_pct: e.target.value }))}
                    />
                  </div>
                </div>
              )}

              {/* EV fields */}
              {isEV && (
                <div className="p-4 bg-blue-50 border border-blue-100 rounded-xl space-y-3">
                  <h3 className="text-sm font-semibold text-blue-800">Battery</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {field('Capacity (kWh)', 'battery_capacity_kwh', 'number', '40')}
                    {field('Efficiency (km/kWh)', 'ev_efficiency', 'number', '6')}
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                      Charge Level: {form.current_battery_pct}%
                    </label>
                    <input
                      type="range" min="0" max="100" step="5"
                      className="w-full accent-blue-600"
                      value={form.current_battery_pct}
                      onChange={e => setForm(f => ({ ...f, current_battery_pct: e.target.value }))}
                    />
                  </div>
                </div>
              )}

              {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
              )}
            </div>

            <div className="p-6 border-t border-gray-100 flex gap-3">
              <button
                onClick={() => setShowForm(false)}
                className="flex-1 py-2.5 border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-2.5 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {saving && <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                {saving ? 'Saving…' : (editId !== null ? 'Save Changes' : 'Add Vehicle')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {deleteConfirm !== null && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-sm w-full">
            <h3 className="font-bold text-gray-900 mb-2">Delete Vehicle?</h3>
            <p className="text-gray-500 text-sm mb-6">This action cannot be undone.</p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="flex-1 py-2.5 border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                className="flex-1 py-2.5 bg-red-600 text-white rounded-xl font-medium hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
