import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import { TripProvider } from './hooks/useTrip'
import HomePage from './pages/HomePage'
import PlannerPage from './pages/PlannerPage'
import ResultsPage from './pages/ResultsPage'
import VehiclePage from './pages/VehiclePage'

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <TripProvider>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/vehicles" element={<VehiclePage />} />
            <Route path="/planner" element={<PlannerPage />} />
            <Route path="/results" element={<ResultsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </TripProvider>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
