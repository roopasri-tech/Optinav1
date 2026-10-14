
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import LocationSearch from '../components/LocationSearch'
import { useTrip } from '../hooks/useTrip'
import { vehiclesApi } from '../services/api'
import type { Vehicle } from '../types'
import { VEHICLE_FUEL_LABEL } from '../utils/format'

export default function HomePage() {
  const navigate = useNavigate()

  const {
    sourceLoc,
    destLoc,
    sourceText,
    destText,
    setSource,
    setDest,
    vehicle,
    setVehicle,
  } = useTrip()

  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    vehiclesApi
      .list()
      .then(setVehicles)
      .catch((e) => setLoadError(e.message))
  }, [])

  const canPlan = Boolean(sourceLoc && destLoc && vehicle)

  const features = [
    {
      icon: '⛽',
      title: 'Multi-fuel support',
      description: 'Petrol, diesel, CNG and bi-fuel vehicles.',
    },
    {
      icon: '⚡',
      title: 'EV-ready routes',
      description: 'Plan charging stops and charge time.',
    },
    {
      icon: '📍',
      title: 'Route facilities',
      description: 'Discover facilities using map data.',
    },
    {
      icon: '₹',
      title: 'Cost estimates',
      description: 'Estimate travel costs from consumption.',
    },
  ]

  return (
    <div className="min-h-screen overflow-hidden bg-[#07130f] text-white">
      {/* Background decoration */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-40 top-20 h-96 w-96 rounded-full bg-green-500/10 blur-3xl" />
        <div className="absolute right-0 top-40 h-96 w-96 rounded-full bg-emerald-400/10 blur-3xl" />
      </div>

      {/* Navigation */}
      <header className="relative z-10 border-b border-white/10">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-green-400 text-xl font-black text-[#07130f] shadow-lg shadow-green-500/20">
              O
            </div>

            <div>
              <div className="text-xl font-bold tracking-tight">
                Opti<span className="text-green-400">Nav</span>
              </div>

              <div className="text-[10px] uppercase tracking-[0.22em] text-gray-500">
                Optimize every journey.
              </div>
            </div>
          </Link>

          <nav className="flex items-center gap-3 text-sm sm:gap-7">
            <Link
              to="/vehicles"
              className="rounded-lg px-2 py-2 text-gray-300 transition hover:text-green-400 sm:px-3"
            >
              Vehicles
            </Link>

            <Link
              to="/planner"
              className="rounded-lg border border-green-400/30 bg-green-400/10 px-3 py-2 font-medium text-green-300 transition hover:bg-green-400/20 sm:px-4"
            >
              Trip planner <span aria-hidden="true">↗</span>
            </Link>
          </nav>
        </div>
      </header>

      <main className="relative z-10">
        {/* Hero section and trip planner */}
        <section className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16 lg:py-24">
          <div>
            <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-green-400/20 bg-green-400/[0.07] px-4 py-2 text-xs font-medium tracking-wide text-green-300 sm:text-sm">
              <span className="h-2 w-2 rounded-full bg-green-400 shadow-[0_0_10px_rgba(74,222,128,0.8)]" />
              SMARTER TRAVEL STARTS HERE
            </div>

            <h1 className="max-w-2xl text-5xl font-bold leading-[1.08] tracking-tight sm:text-6xl xl:text-7xl">
              Smarter routes.
              <br />
              <span className="text-green-400">Lower costs.</span>
              <br />
              Better journeys.
            </h1>

            <p className="mt-7 max-w-xl text-base leading-8 text-gray-400 sm:text-lg">
              Plan your next journey with fuel-aware routes, estimated travel
              costs, and refuelling or EV charging stops across India.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button
                onClick={() =>
                  document
                    .getElementById('trip-planner')
                    ?.scrollIntoView({
                      behavior: 'smooth',
                      block: 'center',
                    })
                }
                className="rounded-xl bg-green-400 px-6 py-3.5 font-semibold text-[#07130f] shadow-lg shadow-green-500/10 transition hover:-translate-y-0.5 hover:bg-green-300"
              >
                Plan your journey <span aria-hidden="true">→</span>
              </button>

              <Link
                to="/vehicles"
                className="rounded-xl border border-white/15 px-6 py-3.5 font-medium text-gray-200 transition hover:border-green-400/50 hover:bg-white/5"
              >
                Explore vehicles
              </Link>
            </div>

            <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 border-t border-white/10 pt-6 text-sm text-gray-400">
              <span>
                <span className="mr-2 text-green-400">✓</span>
                Fuel-aware planning
              </span>
              <span>
                <span className="mr-2 text-green-400">✓</span>
                EV support
              </span>
              <span>
                <span className="mr-2 text-green-400">✓</span>
                Cost estimates
              </span>
            </div>
          </div>

          {/* Trip planner card */}
          <div id="trip-planner" className="scroll-mt-8">
            <div className="rounded-3xl border border-white/10 bg-[#101f19]/95 p-5 shadow-2xl shadow-black/30 sm:p-8">
              <div className="mb-7 flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.2em] text-green-400">
                    YOUR NEXT ADVENTURE
                  </div>

                  <h2 className="mt-2 text-2xl font-bold sm:text-3xl">
                    Plan your trip
                  </h2>

                  <p className="mt-2 text-sm text-gray-400">
                    Enter your route and choose your vehicle.
                  </p>
                </div>

                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-green-400/20 bg-green-400/10 text-2xl">
                  🧭
                </div>
              </div>

              <div className="space-y-5">
                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-gray-400">
                    Starting point
                  </label>

                  <div className="rounded-xl bg-white text-gray-900">
                    <LocationSearch
                      placeholder="Search starting city or address..."
                      value={sourceText}
                      selected={sourceLoc}
                      onTextChange={(t) => setSource(null, t)}
                      onSelect={(loc) => setSource(loc, loc.label)}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3 pl-4">
                  <div className="h-5 w-px bg-green-400/50" />
                  <span className="text-xs text-gray-500">
                    Your destination
                  </span>
                </div>

                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-gray-400">
                    Destination
                  </label>

                  <div className="rounded-xl bg-white text-gray-900">
                    <LocationSearch
                      placeholder="Search destination city or address..."
                      value={destText}
                      selected={destLoc}
                      onTextChange={(t) => setDest(null, t)}
                      onSelect={(loc) => setDest(loc, loc.label)}
                    />
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="vehicle-select"
                    className="mb-2 block text-xs font-semibold uppercase tracking-wider text-gray-400"
                  >
                    Your vehicle
                  </label>

                  <select
                    id="vehicle-select"
                    className="w-full rounded-xl border border-white/10 bg-[#172820] px-4 py-3.5 text-sm text-white outline-none transition focus:border-green-400 focus:ring-2 focus:ring-green-400/20"
                    value={vehicle?.id ?? ''}
                    onChange={(e) =>
                      setVehicle(
                        vehicles.find(
                          (v) => v.id === Number(e.target.value),
                        ) ?? null,
                      )
                    }
                  >
                    <option value="">Select your vehicle...</option>

                    {vehicles.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} —{' '}
                        {VEHICLE_FUEL_LABEL[v.fuel_type] ?? v.fuel_type}
                      </option>
                    ))}
                  </select>

                  {loadError && (
                    <p role="alert" className="mt-2 text-sm text-red-400">
                      Could not load vehicles: {loadError}
                    </p>
                  )}

                  {!loadError && vehicles.length === 0 && (
                    <p className="mt-2 text-sm text-gray-400">
                      No vehicles available yet.{' '}
                      <Link
                        to="/vehicles"
                        className="text-green-400 underline underline-offset-4"
                      >
                        Add a vehicle
                      </Link>
                    </p>
                  )}
                </div>

                <button
                  onClick={() => canPlan && navigate('/planner')}
                  disabled={!canPlan}
                  className="w-full rounded-xl bg-green-400 px-5 py-4 font-bold text-[#07130f] transition hover:bg-green-300 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
                >
                  {canPlan
                    ? 'Build my route →'
                    : !sourceLoc || !destLoc
                      ? 'Choose your start and destination'
                      : 'Select a vehicle to continue'}
                </button>

                <p className="text-center text-xs leading-5 text-gray-500">
                  Route options and estimates depend on available map,
                  vehicle, and facility data.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="mx-auto max-w-7xl px-5 pb-16 sm:px-8 sm:pb-24">
          <div className="mb-7">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-green-400">
              BUILT FOR BETTER JOURNEYS
            </p>

            <h2 className="mt-2 text-2xl font-bold sm:text-3xl">
              Everything you need on the road.
            </h2>

            <p className="mt-3 max-w-2xl text-sm leading-6 text-gray-400 sm:text-base">
              Make more informed travel decisions with route planning
              designed around your vehicle and journey.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature, index) => (
              <div
                key={feature.title}
                className="group rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition duration-300 hover:-translate-y-1 hover:border-green-400/30 hover:bg-green-400/[0.05]"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-green-400/20 bg-green-400/10 text-2xl transition group-hover:bg-green-400/15">
                  {feature.icon}
                </div>

                <div className="mt-5 text-xs font-medium text-gray-500">
                  0{index + 1}
                </div>

                <h3 className="mt-2 text-lg font-semibold">
                  {feature.title}
                </h3>

                <p className="mt-2 text-sm leading-6 text-gray-400">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-6 text-sm text-gray-500 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>
            <span className="font-semibold text-gray-300">OptiNav</span>
            {' '}— Optimize every journey.
          </p>

          <div className="flex gap-5">
            <Link
              to="/vehicles"
              className="transition hover:text-green-400"
            >
              Vehicles
            </Link>

            <Link
              to="/planner"
              className="transition hover:text-green-400"
            >
              Trip planner
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
