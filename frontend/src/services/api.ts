import axios from 'axios'
import type {
  Levels, NearRouteResponse, PlaceResult, RangeSummary, Route, TripResult, Vehicle,
} from '../types'

const api = axios.create({ baseURL: '/api', timeout: 60000 })

// Turn every failure into a short, human-readable Error message.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return Promise.reject(new Error(detail))
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('The server took too long to answer. Please try again.'))
    }
    if (error.response?.status === 502 || error.response?.status === 504) {
      return Promise.reject(new Error('The SmartRoute server is not responding. Please try again in a moment.'))
    }
    if (error.response) return Promise.reject(new Error('Something went wrong. Please try again.'))
    return Promise.reject(new Error('Cannot reach the SmartRoute server. Check that it is running.'))
  },
)

export const vehiclesApi = {
  list: () => api.get<Vehicle[]>('/vehicles').then(r => r.data),
  get: (id: number) => api.get<Vehicle>(`/vehicles/${id}`).then(r => r.data),
  create: (data: Partial<Vehicle>) => api.post<Vehicle>('/vehicles', data).then(r => r.data),
  update: (id: number, data: Partial<Vehicle>) => api.put<Vehicle>(`/vehicles/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/vehicles/${id}`),
  range: (id: number, levels: Levels = {}) =>
    api.get<RangeSummary>(`/vehicles/${id}/range`, { params: levels }).then(r => r.data),
}

export const placesApi = {
  search: (q: string, signal?: AbortSignal) =>
    api.get<{ results: PlaceResult[] }>('/places/search', { params: { q }, signal }).then(r => r.data.results),
  nearRoute: (routeId: number) =>
    api.post<NearRouteResponse>('/places/near-route', { route_id: routeId }, { timeout: 90000 }).then(r => r.data),
}

export interface LocationPayload { query: string; lat?: number; lon?: number }

export const routesApi = {
  plan: (source: LocationPayload, destination: LocationPayload) =>
    api.post<Route>('/routes/plan', { source, destination }).then(r => r.data),
  get: (id: number) => api.get<Route>(`/routes/${id}`).then(r => r.data),
}

export interface OptimizationPayload extends Levels {
  vehicle_id: number
  route_id: number
  preference: 'cheapest' | 'fewest_stops'
}

export const optimizationApi = {
  optimize: (payload: OptimizationPayload) =>
    api.post<TripResult>('/optimization/trip', payload, { timeout: 120000 }).then(r => r.data),
  getTrip: (id: number) => api.get<TripResult>(`/trips/${id}`).then(r => r.data),
}

export default api
