// Display helpers - never show raw floating point values to the user.

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const num1 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 })

/** 1737.3 -> "28h 57m"; 2000 -> "1d 9h 20m"; 45 -> "45m" */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes == null || !isFinite(minutes)) return '—'
  const total = Math.max(0, Math.round(minutes))
  const d = Math.floor(total / 1440)
  const h = Math.floor((total % 1440) / 60)
  const m = total % 60
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

/** 2238.00000004 -> "2,238 km"; 4.26 -> "4.3 km" */
export function formatKm(km: number | null | undefined): string {
  if (km == null || !isFinite(km)) return '—'
  return km >= 100 ? `${inr.format(Math.round(km))} km` : `${num1.format(km)} km`
}

/** 12345.678 -> "₹12,346" */
export function formatINR(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return '—'
  return `₹${inr.format(Math.round(value))}`
}

export function formatPct(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return '—'
  return `${Math.round(value)}%`
}

export function formatQty(value: number, unit: string): string {
  const digits = unit === 'kg' ? 2 : 1
  return `${Number(value.toFixed(digits))} ${unit}`
}

export const FUEL_LABEL: Record<string, string> = {
  petrol: 'Petrol', diesel: 'Diesel', cng: 'CNG', electric: 'Electricity', lpg: 'LPG',
}

export const VEHICLE_FUEL_LABEL: Record<string, string> = {
  petrol: 'Petrol', diesel: 'Diesel', cng: 'CNG', electric: 'Electric (EV)', bifuel: 'Bi-fuel (CNG + Petrol)',
}

export const CATEGORY_LABEL: Record<string, string> = {
  fuel: 'Fuel', cng: 'CNG', ev: 'EV charging', restaurant: 'Food', parking: 'Parking', restroom: 'Restrooms',
}
