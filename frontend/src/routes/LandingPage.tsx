import type { ReactNode } from 'react'
import { appHref } from '../appBase'
import { ExternalLink } from '../components/ExternalLink'

function SectionCard({
  id,
  title,
  subtitle,
  children,
}: {
  id: string
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-20 rounded-2xl border border-stone-200/80 bg-white p-6 shadow-sm md:p-8">
      <h2 className="text-xl font-semibold tracking-tight text-stone-900 md:text-2xl">{title}</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-stone-600 md:text-base">{subtitle}</p>
      <div className="mt-5 space-y-4 text-sm leading-relaxed text-stone-700">{children}</div>
    </section>
  )
}

function ActionLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <ExternalLink
      to={to}
      className="inline-flex items-center rounded-lg bg-amber-800 px-4 py-2 text-sm font-medium text-amber-50 shadow-sm transition hover:bg-amber-900"
    >
      {children}
    </ExternalLink>
  )
}

function SecondaryLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <ExternalLink
      to={to}
      className="inline-flex items-center rounded-lg border border-stone-300 bg-white px-4 py-2 text-sm font-medium text-stone-800 transition hover:border-amber-700 hover:text-amber-900"
    >
      {children}
    </ExternalLink>
  )
}

const HIGHLIGHT_VARIABLES = [
  { name: 'mean_annual_delta_g_mm', note: 'Groundwater storage trend across the MWS' },
  { name: 'soge_dev_percent', note: 'Stage-of-groundwater-exploitation (% of area in stressed blocks)' },
  { name: 'drought_weeks_severe[-1]', note: 'Recent severe drought exposure' },
  { name: 'lulc_tree_forest_ha[-1]', note: 'Tree/forest cover for NTFP and biodiversity context' },
  { name: 'household_income_inr', note: 'Socio-economic stress indicators' },
  { name: 'borewell_density', note: 'Irrigation infrastructure intensity' },
]

export function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-100 via-[#f5f1ea] to-stone-200">
      <header className="border-b border-stone-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-800">CoRE Stack</p>
            <h1 className="text-2xl font-bold tracking-tight text-stone-900">CoRE insights v0.1</h1>
          </div>
          <nav className="flex flex-wrap gap-2 text-sm">
            <a href="#diagnose" className="rounded-md px-2 py-1 text-stone-600 hover:bg-stone-100 hover:text-stone-900">
              Diagnose
            </a>
            <a href="#data" className="rounded-md px-2 py-1 text-stone-600 hover:bg-stone-100 hover:text-stone-900">
              Data
            </a>
            <a href="#triage" className="rounded-md px-2 py-1 text-stone-600 hover:bg-stone-100 hover:text-stone-900">
              Triage
            </a>
            <a href="#about" className="rounded-md px-2 py-1 text-stone-600 hover:bg-stone-100 hover:text-stone-900">
              About
            </a>
            <ExternalLink
              to="https://github.com/aaditeshwar/landscape-problem-diagnosis"
              className="rounded-md px-2 py-1 text-stone-600 hover:bg-stone-100 hover:text-stone-900"
            >
              GitHub
            </ExternalLink>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-10 md:py-14">
        <div className="rounded-2xl border border-amber-200/60 bg-gradient-to-br from-amber-50 to-white p-6 shadow-sm md:p-10">
          <p className="text-sm font-medium text-amber-900">Landscape problem diagnosis</p>
          <h2 className="mt-2 text-3xl font-bold leading-tight text-stone-900 md:text-4xl">
            Understand watershed stress with evidence-backed pathways
          </h2>
          <p className="mt-4 max-w-3xl text-base leading-relaxed text-stone-700">
            CoRE insights connects micro-watershed (MWS) landscape data, diagnostic evidence cards, and optional
            large-language-model review to help practitioners and researchers explore water, agriculture, forest, and
            livelihood stresses across India — grounded in the CoRE Stack variable library.
          </p>
        </div>

        <SectionCard
          id="diagnose"
          title="Diagnose an MWS and give feedback"
          subtitle="Pick a tehsil on the map, select a micro-watershed, describe the problem, and receive pathway-level diagnosis with optional follow-up questions."
        >
          <p>
            The diagnosis workflow combines <strong>signal evaluation</strong> on CoRE Stack variables with evidence
            cards that encode causal pathways (for example groundwater stress, drought, or forest degradation). You can
            run the engine in several modes:
          </p>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong>Server-only</strong> — deterministic pathway confirmation from diagnostic signals and card
              policies; no LLM call. Fast and reproducible.
            </li>
            <li>
              <strong>Server + LLM opinion</strong> — the server diagnosis is shown alongside an independent LLM review
              of pathway presence and confidence.
            </li>
          </ul>
          <p>
            After a diagnosis you can open the <strong>feedback</strong> view to compare modes side-by-side and record
            structured reviewer notes. Query-bank evaluation summaries (rubric scores and pathway agreement) are
            available for a qualitative sense of how modes compare on benchmark questions.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <ActionLink to="/diagnose">Start on the map</ActionLink>
            <SecondaryLink to="/review">View query evaluation</SecondaryLink>
          </div>
        </SectionCard>

        <SectionCard
          id="data"
          title="Explore the CoRE Stack data landscape"
          subtitle="Browse over a hundred harmonised variables and global distributions across production systems and observed stresses."
        >
          <p>
            The CoRE Stack brings hydrology, land use, climate, groundwater, socio-economic, and programme indicators
            into a <strong>single MWS-level export</strong> — something few open landscape datasets do at this breadth.
            The variable catalog documents each indicator; the dashboard shows empirical CDFs and categorical
            distributions pooled across ingested watersheds for each diagnosis section.
          </p>
          <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Example variables</p>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {HIGHLIGHT_VARIABLES.map((item) => (
                <li key={item.name} className="rounded-lg bg-white px-3 py-2 text-sm shadow-sm">
                  <code className="text-amber-900">{item.name}</code>
                  <p className="mt-0.5 text-xs text-stone-600">{item.note}</p>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-wrap gap-3 pt-1">
            <ActionLink to="/variables">Variable catalog</ActionLink>
            <SecondaryLink to="/dashboard">Variable dashboard</SecondaryLink>
          </div>
        </SectionCard>

        <SectionCard
          id="triage"
          title="Triage case studies and suggest card improvements"
          subtitle="Experts can tune diagnostic signals against known field case studies and save patches for maintainer review."
        >
          <p>
            The <strong>triaging app</strong> loads case-study catalogs (built-in or your own upload) and lets you edit
            signal expressions, thresholds, and confirmation policy per evidence card. Changes are evaluated against the
            global MWS pool and case-study ground truth before you save.
          </p>
          <p>
            Saved patches are stored per catalog and reviewer name. <strong>CoRE Stack maintainers review patches</strong>{' '}
            before they are merged into the canonical evidence cards in the repository — this keeps community contributions
            quality-controlled.
          </p>
          <p>
            Upload your own case-study JSON (see the downloadable example in the triaging app). Only catalogs that match
            the required <code className="rounded bg-stone-100 px-1">diagnosis_framework</code> shape are accepted.
          </p>
          <p className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-amber-950">
            If you cannot save patches (reviewer name not whitelisted), email{' '}
            <a
              href="mailto:contact@core-stack.org"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium underline"
            >
              contact@core-stack.org
            </a>{' '}
            to request a username for suggesting changes.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <ActionLink to="/triaging">Open triaging app</ActionLink>
            <ExternalLink
              to={appHref('/api/triage/catalogs/example')}
              className="inline-flex items-center rounded-lg border border-stone-300 bg-white px-4 py-2 text-sm font-medium text-stone-800 transition hover:border-amber-700 hover:text-amber-900"
            >
              Download example catalog
            </ExternalLink>
            <SecondaryLink to="/logs">View diagnosis logs</SecondaryLink>
          </div>
        </SectionCard>

        <SectionCard
          id="about"
          title="About the CoRE Stack"
          subtitle="Commoning for Resilience and Equality"
        >
          <p>
            The{' '}
            <ExternalLink to="https://core-stack.org/" className="font-medium text-amber-800 hover:underline">
              CoRE Stack
            </ExternalLink>{' '}
            is a network-based approach to landscape intelligence: interoperable tools, curated geospatial datasets, and
            community-oriented methodologies for natural resource management. Rather than treating technology as the
            solution, the stack is designed to be <strong>used and managed by communities</strong> — enabling citizens,
            practitioners, and researchers to understand hydrological stress, land change, and livelihood vulnerability
            in context.
          </p>
          <p>
            CoRE insights is one application built on that stack: it ingests MWS-level CoRE exports, links them to
            structured diagnosis evidence, and exposes map-first exploration, benchmarking, and expert triage workflows
            on top of the same variable foundation used across CoRE tools.
          </p>
          <p>
            Learn more about datasets, APIs, case studies, and the developer community at{' '}
            <ExternalLink to="https://core-stack.org/" className="font-medium text-amber-800 hover:underline">
              core-stack.org
            </ExternalLink>
            .
          </p>
        </SectionCard>

        <footer className="border-t border-stone-200 pt-6 text-center text-xs text-stone-500">
          CoRE insights · landscape problem diagnosis · built with Claude and Cursor, guided by Aaditeshwar Seth, Shivani A. Mehta, Riti Verma, Immanuel Shadrach (IIT Delhi)
        </footer>
      </main>
    </div>
  )
}
