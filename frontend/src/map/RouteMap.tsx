import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { Facility, OptimizationStop } from '../types'
import { FUEL_LABEL, formatINR, formatQty } from '../utils/format'

const COLORS: Record<string, string> = {
  fuel: '#f59e0b', cng: '#0ea5e9', ev: '#2563eb', restaurant: '#ef4444', parking: '#8b5cf6', restroom: '#06b6d4',
}
const MAX_MARKERS = 800

function stopIcon(index: number) {
  return L.divIcon({
    html: `<div style="width:30px;height:30px;border-radius:50%;background:#16a34a;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4)">${index + 1}</div>`,
    className: '', iconSize: [30, 30], iconAnchor: [15, 15],
  })
}

function endpointIcon(label: string, color: string) {
  return L.divIcon({
    html: `<div style="background:${color};color:#fff;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.3);transform:translate(-50%,-50%);display:inline-block">${label}</div>`,
    className: '', iconSize: [0, 0],
  })
}

function FitBounds({ geometry }: { geometry: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    const fit = () => {
      map.invalidateSize()
      if (geometry.length >= 2) map.fitBounds(L.latLngBounds(geometry), { padding: [40, 40] })
    }
    fit()
    // The container can change size after mount (responsive layouts) - re-measure and re-fit.
    const observer = new ResizeObserver(() => fit())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [geometry, map])
  return null
}

interface Props {
  geometry?: [number, number][]
  facilities?: Facility[]
  stops?: OptimizationStop[]
  selectedId?: number
  onFacilityClick?: (f: Facility) => void
}

export default function RouteMap({ geometry = [], facilities = [], stops = [], selectedId, onFacilityClick }: Props) {
  const shown = useMemo(() => facilities.slice(0, MAX_MARKERS), [facilities])
  const start = geometry[0]
  const end = geometry[geometry.length - 1]

  return (
    <MapContainer center={[22.5, 79]} zoom={5} preferCanvas style={{ width: '100%', height: '100%' }}>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {geometry.length >= 2 && (
        <>
          <FitBounds geometry={geometry} />
          <Polyline positions={geometry} pathOptions={{ color: '#16a34a', weight: 5, opacity: 0.8 }} />
          <Marker position={start} icon={endpointIcon('Start', '#16a34a')} />
          <Marker position={end} icon={endpointIcon('Destination', '#dc2626')} />
        </>
      )}

      {shown.map(f => {
        const isCng = f.category === 'fuel' && (f.fuel_types || []).includes('cng')
        const color = COLORS[isCng ? 'cng' : f.category] ?? '#6b7280'
        return (
          <CircleMarker key={f.id} center={[f.latitude, f.longitude]} radius={selectedId === f.id ? 9 : 5}
            pathOptions={{ color: '#fff', weight: 1.5, fillColor: color, fillOpacity: 0.95 }}
            eventHandlers={{ click: () => onFacilityClick?.(f) }}>
            <Tooltip direction="top">{f.name}</Tooltip>
          </CircleMarker>
        )
      })}

      {stops.map((s, i) => (
        <Marker key={`stop-${i}`} position={[s.latitude, s.longitude]} icon={stopIcon(i)} zIndexOffset={1000}>
          <Popup>
            <div style={{ minWidth: 180 }}>
              <strong>Stop {i + 1}: {s.name}</strong>
              <div style={{ fontSize: 12, marginTop: 4 }}>km {Math.round(s.km_along)}</div>
              {s.purchases.map(p => (
                <div key={p.fuel_type} style={{ fontSize: 12 }}>
                  {FUEL_LABEL[p.fuel_type]}: {formatQty(p.quantity, p.unit)} · {formatINR(p.cost_inr)}
                </div>
              ))}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  )
}
