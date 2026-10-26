import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Confidence, Empty, Failed, Loading, NoProject, PageHead, SourceLink } from '../components/ui'
import { Icon } from '../components/Icon'
import { sourcePath } from '../lib/answer'
import { useApi } from '../lib/useApi'
import { useStatus } from '../lib/useStatus'
import { useRememberedParam } from '../lib/pageState'
import type { FeatureDetail, FeatureList, FeatureSummary } from '../lib/features'
import './features.css'

const VIEWS = ['Overview', 'Code flow', 'APIs and data', 'Tests', 'Known problems'] as const
type View = typeof VIEWS[number]

function Feature({ summary, revision }: { summary: FeatureSummary; revision: number }) {
  const detail = useApi<FeatureDetail>(`/api/features/${encodeURIComponent(summary.id)}`, 0, revision)
  const [view, setView] = useState<View>('Overview')
  if (detail.error) return <Failed message={detail.error} onRetry={detail.reload} />
  if (!detail.data) return <Loading what="feature details" detail="Checking source access and reading the saved scan. No overview build is started." />
  const body = detail.data
  const data = body.apis_and_data
  return <section className="feature-detail" aria-label="Selected feature">
    <div className="feature-hero">
      <div className="feature-eyebrow"><Icon name="grid" size={16} /> FEATURE EXPLORER <Chip tone="accent">From saved code</Chip>
        <Button kind="ghost" icon="refresh" onClick={detail.reload}>Refresh feature</Button></div>
      <h2>{body.name}</h2>
      <p>Explore {data.routes.length} route{data.routes.length === 1 ? '' : 's'} and {body.related.length} related file{body.related.length === 1 ? '' : 's'} found in the imported code.</p>
      <div className="feature-metrics">
        {[
          { label: 'Routes', value: data.routes.length, view: 'APIs and data' },
          { label: 'Related files', value: body.related.length, view: 'Overview' },
          { label: 'Linked tests', value: body.tests.existing.length, view: 'Tests' },
          { label: 'Evidence gaps', value: body.gaps.length, view: 'Known problems' },
        ].map(metric => <button type="button" key={metric.label} onClick={() => setView(metric.view as View)}>
          <strong>{metric.value}</strong><span>{metric.label}</span><Icon name="chevron" size={14} />
        </button>)}
      </div>
    </div>
    <div className="feature-content">
      <div className="tabs feature-tabs" role="tablist" aria-label="Feature details">
        {VIEWS.map((name, index) => <button key={name} type="button" role="tab" id={`feature-tab-${index}`}
          aria-controls="feature-panel" aria-selected={view === name} tabIndex={view === name ? 0 : -1}
          className={`tab${view === name ? ' is-active' : ''}`} onClick={() => setView(name)}
          onKeyDown={event => {
            let next = index
            if (event.key === 'ArrowRight') next = (index + 1) % VIEWS.length
            else if (event.key === 'ArrowLeft') next = (index + VIEWS.length - 1) % VIEWS.length
            else if (event.key === 'Home') next = 0
            else if (event.key === 'End') next = VIEWS.length - 1
            else return
            event.preventDefault(); setView(VIEWS[next])
            document.getElementById(`feature-tab-${next}`)?.focus()
          }}>{name}</button>)}
      </div>
      <div id="feature-panel" role="tabpanel" aria-labelledby={`feature-tab-${VIEWS.indexOf(view)}`} tabIndex={0} className="feature-panel">
        {view === 'Overview' && <>
          <div className="feature-section-heading"><h3>Start with the code</h3><span>{body.related.length} file{body.related.length === 1 ? '' : 's'}</span></div>
          <p className="feature-muted">Features are grouped by route address and followed through imports up to two steps away. Shared files can appear in several features. A business-purpose explanation has not been generated.</p>
          <div className="feature-files">{body.related.map(file => <div className="feature-file" key={file.path}>
            <Icon name="doc" size={18} /><div><strong>{file.name}</strong><SourceLink {...file} /></div>
          </div>)}</div>
          <div className="feature-section-heading"><h3>Related Jira tickets</h3><span>{body.issues.length} matches</span></div>
          <p className="feature-muted">A ticket key found in code confirms a reference. A name match needs checking. Neither confirms that the requested work is complete.</p>
          {body.issues.length ? <div className="feature-evidence-list">{body.issues.map(issue => <article key={issue.key}>
            <div className="feature-row-heading"><Link to={`/jira?issue=${encodeURIComponent(issue.key)}`}>{issue.key}</Link><Confidence level={issue.confidence} /></div>
            <p>{issue.summary}</p>
            {issue.confidence === 'confirmed' ? <SourceLink {...issue} /> : <p className="feature-muted">Matched by words in the ticket summary.</p>}
          </article>)}</div> : <p className="feature-note">No Jira ticket matches were found in the saved information. Read relevant issues from <Link to="/connections">Connections</Link> to include them.</p>}
          <p className="feature-note">This view maps code and Jira references. To ask a question across code, Jira and Slack, use <Link to={`/ask?q=${encodeURIComponent(`How does ${body.name} work?`)}`}>Ask assistant</Link>.</p>
        </>}
        {view === 'Code flow' && <>
          <h3>{body.flow.title}</h3>
          <p className="feature-note">This is a static map of route declarations, imported files and data declarations. The order does not represent an observed request or prove that a request succeeds.</p>
          <ol className="feature-flow">{body.flow.steps.map(step => <li key={step.n}>
            <span className="feature-step">{step.n}</span><div><div className="feature-row-heading"><h4>{step.label}</h4><Chip>{step.component.kind}</Chip></div>
              <p>{step.plain}</p><SourceLink {...step.component} />
            </div>
          </li>)}</ol>
          {!body.flow.steps.length && <Empty title="No route or import evidence was found." />}
        </>}
        {view === 'APIs and data' && <>
          <h3>Route declarations</h3>
          <div className="feature-evidence-list">{data.routes.map((route, i) => <article key={i}>
            <div className="feature-row-heading">{route.method && <Chip tone="accent">{route.method}</Chip>}<code>{route.path}</code></div>
            <SourceLink {...route.declared_at} />
          </article>)}</div>
          <h3>Data declarations</h3>
          <p className="feature-muted">Tables, models and data shapes found in related files. This does not verify which ones a request reads or writes.</p>
          {data.tables.length ? <div className="feature-evidence-list">{data.tables.map((table, i) => <article key={i}>
            <strong>{table.name}</strong><p>{table.plain}</p><SourceLink {...table.declared_at} />
          </article>)}</div> : <p className="feature-note">No data declarations were found in the related files.</p>}
          <h3>External service references</h3>
          {data.services.length ? <div className="feature-evidence-list">{data.services.map((service, i) => <article key={i}>
            <strong>{service.name}</strong><p>{service.plain}</p><SourceLink {...service.called_at} />
          </article>)}</div> : <p className="feature-note">No external service references were found in the related files.</p>}
        </>}
        {view === 'Tests' && <>
          <h3>Tests linked by imports</h3>
          <p className="feature-note">These test files import a related file. They have not been executed here, and an import alone does not establish behavior coverage or a passing result.</p>
          {body.tests.existing.length ? <div className="feature-evidence-list">{body.tests.existing.map(test => <article key={test.path}>
            <strong>{test.name}</strong><p>Imports {sourcePath(test.covers.replace(/^Imports /, ''))}</p><SourceLink {...test} />
          </article>)}</div> : <Empty title="No linked test files were found" detail="Checked test-file imports in the saved scan. Tests using other patterns or files outside the scan may still exist." />}
        </>}
        {view === 'Known problems' && <>
          <h3>Runtime problems are not assessed</h3>
          <p className="feature-note">{body.known_problems.note} This is not a confirmation that the feature has no bugs.</p>
          <h3>Evidence gaps to review</h3>
          <p className="feature-muted">These are limits of the saved evidence, not confirmed defects.</p>
          {body.gaps.length ? <div className="feature-gaps">{body.gaps.map(gap => <details key={gap.what}>
            <summary><Icon name="warn" size={16} />{gap.what}</summary>
            <p>{gap.why_missing}</p><p className="feature-muted">Checked: {gap.checked}</p>
          </details>)}</div> : <p className="feature-note">No gaps were reported by these checks. Runtime behavior still needs verification.</p>}
        </>}
      </div>
    </div>
  </section>
}

export function Features() {
  const status = useStatus()
  const list = useApi<FeatureList>('/api/features', 0, status.data?.knowledge_revision,
    !!status.data && !status.data.awaiting_project)
  const [selection, setParams] = useRememberedParam('feature')
  const [filter, setFilter] = useState('')
  const head = <PageHead title="Feature explorer" lead="Follow a feature through its code, data, tests and related tickets."
    actions={<><Button icon="refresh" onClick={list.reload}>Refresh features</Button>
      <Link className="btn btn-secondary" to="/connections">Manage sources</Link></>} />
  if (status.error) return <>{head}<Failed message={status.error} onRetry={status.reload} /></>
  if (status.data?.awaiting_project) return <>{head}<NoProject what="features from the saved code" /></>
  if (!status.data) return <>{head}<Loading what="the project" /></>
  if (list.error) return <>{head}<Failed message={list.error} onRetry={list.reload} /></>
  if (!list.data) return <>{head}<Loading what="saved features" detail="Checking access to connected sources. No overview build is needed." /></>
  const body = list.data
  if (!body.available || !body.features.length) return <>{head}<Card><Empty
    title={body.available ? 'No route-based features were found' : 'Read your code to explore features'}
    detail={body.reason || body.unclustered?.note || 'Read a GitHub repository or local folder from Connections. Features become available after a successful scan.'}
    action={<Link className="btn btn-primary" to="/connections">Go to Connections</Link>} /></Card></>
  const chosen = selection || body.features[0].id
  const selected = body.features.find(feature => feature.id === chosen)
  const shown = body.features.filter(feature => `${feature.id} ${feature.name} ${feature.ticket_name || ''}`.toLowerCase().includes(filter.trim().toLowerCase()))
  return <>{head}
    <div className="feature-scope"><span><Icon name="database" size={16} /> {body.features.length} feature groups · Saved scan{body.commit ? ` ${body.commit.slice(0, 7)}` : ''}</span>
      <span>Browsing does not rebuild the overview.</span></div>
    <div className="feature-layout">
      <aside className="feature-browser" aria-label="Find a feature">
        <label className="feature-search"><span>Find a feature</span><div><Icon name="search" size={16} /><input type="search"
          value={filter} onChange={event => setFilter(event.target.value)} placeholder="Name or related ticket" /></div></label>
        <p className="feature-list-count">{shown.length} of {body.features.length} features</p>
        <div className="feature-list" role="group" aria-label="Choose feature">{shown.map(feature => <button type="button" key={feature.id}
          aria-pressed={chosen === feature.id} onClick={() => setParams(previous => { const next = new URLSearchParams(previous); next.set('feature', feature.id); return next })}>
          <span className="feature-list-name">{feature.name}<Icon name="chevron" size={14} /></span>
          <span>{feature.route_count} route{feature.route_count === 1 ? '' : 's'} · {feature.file_count} file{feature.file_count === 1 ? '' : 's'}</span>
          <span className="feature-list-tags"><Chip tone={feature.has_tests ? 'ok' : 'quiet'}>{feature.has_tests ? 'Tests linked' : 'No linked tests'}</Chip>
            {feature.gap_count > 0 && <Chip tone="warn">{feature.gap_count} gaps</Chip>}</span>
        </button>)}</div>
        {!shown.length && <Empty title="No matching features" action={<Button onClick={() => setFilter('')}>Clear search</Button>} />}
        <details className="feature-coverage"><summary>How features are found</summary>
          <p>{body.unclustered?.note}</p><p>Up to 24 route groups and 20 files per group are shown. Import tracing is limited to two steps.</p>
          {body.unclustered && <p>{body.unclustered.files} files and {body.unclustered.routes} routes are outside the displayed groups.</p>}
        </details>
      </aside>
      {selected ? <Feature key={`${chosen}:${status.data.knowledge_revision}`} summary={selected} revision={status.data.knowledge_revision} />
        : <Card><Empty title="This feature is not in the current scan" detail="Choose a feature from the list. The project or saved code may have changed." /></Card>}
    </div>
  </>
}
