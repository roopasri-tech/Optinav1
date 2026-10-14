import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TripResult } from '../../types'
import { FUEL_LABEL, formatINR, formatKm, formatQty } from '../../utils/format'

/** Honest cost summary: consumption-based cost, baseline and real savings only. */
export default function CostComparison({ result }: { result: TripResult }) {
  const opt = result.optimization
  if (!opt.feasible || opt.energy_cost_inr == null) return null
  const alt = result.alternative
  const bars = [
    ...(opt.baseline ? [{ name: 'Baseline', cost: Math.round(opt.baseline.cost_inr), color: '#9ca3af' }] : []),
    { name: opt.preference === 'cheapest' ? 'This plan (lowest cost)' : 'This plan (fewest stops)', cost: Math.round(opt.energy_cost_inr), color: '#16a34a' },
    ...(alt ? [{ name: alt.preference === 'cheapest' ? 'Lowest-cost plan' : 'Fewest-stops plan', cost: Math.round(alt.energy_cost_inr), color: '#60a5fa' }] : []),
  ]
  const savings = opt.savings_inr
  const vehicleSingleFuel = result.vehicle.fuels.length <= 1

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-6">
      <h2 className="font-bold text-gray-900 mb-4">💰 Trip cost</h2>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <div className="p-3 bg-green-50 rounded-xl">
          <div className="text-xl font-bold text-green-700">{formatINR(opt.energy_cost_inr)}</div>
          <div className="text-xs text-gray-500">Fuel/energy used on this trip</div>
        </div>
        <div className="p-3 bg-gray-50 rounded-xl">
          <div className="text-xl font-bold text-gray-800">{formatINR(opt.purchase_cost_inr)}</div>
          <div className="text-xs text-gray-500">To pay at the recommended stops</div>
        </div>
        <div className="p-3 bg-gray-50 rounded-xl">
          <div className="text-xl font-bold text-gray-800">{opt.baseline ? formatINR(opt.baseline.cost_inr) : '—'}</div>
          <div className="text-xs text-gray-500">Baseline{opt.baseline ? '' : ' (not available)'}</div>
        </div>
        <div className={`p-3 rounded-xl ${savings && savings > 0.5 ? 'bg-amber-50' : 'bg-gray-50'}`}>
          <div className={`text-xl font-bold ${savings && savings > 0.5 ? 'text-amber-700' : 'text-gray-800'}`}>
            {savings == null ? '—' : savings > 0.5 ? `${formatINR(savings)} (${opt.savings_pct}%)` : '₹0'}
          </div>
          <div className="text-xs text-gray-500">Saving vs baseline</div>
        </div>
      </div>

      {opt.baseline && <p className="text-xs text-gray-500 mb-1"><b>Baseline:</b> {opt.baseline.description}.</p>}
      {savings != null && savings <= 0.5 && (
        <p className="text-xs text-gray-500 mb-1">
          {savings < -0.5
            ? `This plan uses ${formatINR(-savings)} more fuel than the baseline because its stations need longer detours.`
            : vehicleSingleFuel
              ? 'No saving: for a single-fuel vehicle the fuel cost is set by the distance. SmartRoute ensures the trip is feasible and keeps detours small.'
              : 'No saving compared with the baseline on this route.'}
        </p>
      )}
      {alt && (
        <p className="text-xs text-gray-500 mb-3">
          <b>Alternative:</b> the {alt.preference === 'cheapest' ? 'lowest-cost' : 'fewest-stops'} plan needs {alt.stops_count} stop{alt.stops_count === 1 ? '' : 's'} and
          uses {formatINR(alt.energy_cost_inr)} of fuel/energy (this plan: {result.optimization.stops.length} stop{result.optimization.stops.length === 1 ? '' : 's'}, {formatINR(opt.energy_cost_inr)}).
        </p>
      )}

      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={bars} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6b7280' }} />
          <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} tickFormatter={v => `₹${v}`} width={64} />
          <Tooltip formatter={(v: number) => [formatINR(v), 'Fuel/energy cost']} />
          <Bar dataKey="cost" radius={[6, 6, 0, 0]} isAnimationActive={false}>
            {bars.map(b => <Cell key={b.name} fill={b.color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <table className="w-full text-xs mt-4">
        <thead><tr className="text-gray-400 text-left"><th className="py-1">Fuel</th><th>Distance</th><th>Used</th><th>Cost</th><th>Per km</th></tr></thead>
        <tbody>
          {Object.entries(opt.fuel_breakdown ?? {}).map(([ft, b]) => (
            <tr key={ft} className="border-t border-gray-100">
              <td className="py-1 font-medium">{FUEL_LABEL[ft] ?? ft}</td>
              <td>{formatKm(b.km)}</td>
              <td>{formatQty(b.quantity, b.unit)}</td>
              <td>{formatINR(b.cost_inr)}</td>
              <td>₹{(b.cost_inr / Math.max(b.km, 1)).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[11px] text-gray-400 mt-2">{result.assumptions?.note} Prices used: {Object.entries(result.assumptions?.prices ?? {})
        .map(([ft, p]) => `${FUEL_LABEL[ft]} ₹${p}`).join(', ')}.</p>
    </div>
  )
}
