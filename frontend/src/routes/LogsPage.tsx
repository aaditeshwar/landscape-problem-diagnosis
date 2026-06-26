import { appUrl } from '../appBase'
import { ExternalLink } from '../components/ExternalLink'

const LOGS_API_BASE = appUrl('/api/logs')

export function LogsPage() {
  const dashboardSrc = `${appUrl('/api/logs/dashboard')}?api_base=${encodeURIComponent(LOGS_API_BASE)}`

  return (
    <div className="flex h-screen flex-col bg-stone-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 bg-white px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold text-stone-900">Diagnosis logs</h1>
          <p className="text-sm text-stone-500">Structured diagnosis run events and replay metadata</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <ExternalLink to="/" className="text-amber-800 hover:underline">
            Home
          </ExternalLink>
          <ExternalLink to="/diagnose" className="text-amber-800 hover:underline">
            Diagnosis map
          </ExternalLink>
        </div>
      </header>
      <iframe
        src={dashboardSrc}
        title="Diagnosis log dashboard"
        className="min-h-0 w-full flex-1 border-0 bg-white"
      />
    </div>
  )
}
