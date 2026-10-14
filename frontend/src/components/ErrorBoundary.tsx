import { Component, ErrorInfo, ReactNode } from 'react'

/** Shows a friendly message instead of a blank page if a screen fails to render. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('SmartRoute UI error:', error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <div className="bg-white rounded-2xl border border-gray-200 p-6 max-w-md text-center">
          <h1 className="font-bold text-gray-900 mb-2">Something went wrong displaying this page</h1>
          <p className="text-sm text-gray-500 mb-4">Your trip data is safe. Go back to the planner and try again.</p>
          <a href="/planner" className="px-4 py-2 bg-green-600 text-white rounded-xl text-sm">Back to planner</a>
        </div>
      </div>
    )
  }
}
