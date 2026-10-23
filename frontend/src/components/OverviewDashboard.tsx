import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import { Statements } from './Statements'
import { Button, Chip, Empty, Failed, Loading, Missing, SourceLink } from './ui'
import { originOf, sourcePath } from '../lib/answer'
import { factsOf } from '../lib/overview'
import type { FactGroup, Overview, Section } from '../lib/overview'
import type { Load } from '../lib/useApi'

export type OverviewMode = 'Beginner' | 'Developer' | 'Architect'
export type FeatureReply = {
  available: boolean
  features: { id: string; name: string; route_count: number; file_count: number; gap_count: number }[]
  unclustered: { note: string }
}

const TOPIC: Record<string, { label: string; icon: string; hint: string }> = {
  purpose: { label: 'Start here', icon: 'home', hint: 'What the project does and why it exists.' },
  technologies: { label: 'Technology', icon: 'grid', hint: 'The tools it uses and the role of each one.' },
  architecture: { label: 'Code structure', icon: 'nodes', hint: 'Find your way around the codebase.' },
  setup: { label: 'Getting started', icon: 'wrench', hint: 'Set up and run the project.' },
  flows: { label: 'Runtime flow', icon: 'send', hint: 'Follow what happens when the project runs.' },
  interfaces: { label: 'APIs & interfaces', icon: 'link', hint: 'How the outside world interacts with it.' },
  data: { label: 'Data & settings', icon: 'database', hint: 'Where information and configuration live.' },
  testing: { label: 'Testing', icon: 'check', hint: 'Understand what the existing checks cover.' },
  decisions: { label: 'Team context', icon: 'people', hint: 'What the imported tickets and discussions say.' },
}
const PREVIEW: Record<OverviewMode, number> = { Beginner: 3, Developer: 8, Architect: 2 }

function needsReview(section: Section) {
  return !!section.error || !!section.missing_information || !section.statements.length
    || section.statements.some(s => s.support === 'check this' || s.support === 'partly supported'
      || !s.about_this_project || (s.files_not_read?.length ?? 0) > 0)
}

function Facts({ group }: { group: FactGroup }) {
  return <div className="fg">
    <p className="fg-plain">{group.plain}</p>
    <ul className="fg-list">{group.items.map((item, i) => <li key={i}>
      <span className="fg-text">{item.text}</span>
      {item.detail && <span className="fg-detail">{item.detail}</span>}
      {item.path && <SourceLink path={item.path} line={item.line} url={item.url} />}
    </li>)}</ul>
    {group.truncated > 0 && <p className="fg-more">{group.truncated} more not shown in the saved overview.</p>}
    {group.note && <p className="fg-note">{group.note}</p>}
  </div>
}

function FactDetails({ group, open = false }: { group: FactGroup; open?: boolean }) {
  return <details className="ov-disclosure" open={open || undefined}>
    <summary><span>{group.title}</span><span className="ov-count">{group.items.length}</span></summary>
    <div className="ov-disclosure-body"><Facts group={group} /></div>
  </details>
}

function TopicContent({ section, mode, body }: { section: Section; mode: OverviewMode; body: Overview }) {
  const [expanded, setExpanded] = useState(false)
  const content = useRef<HTMLDivElement>(null)
  const limit = PREVIEW[mode]
  const more = section.statements.length > limit
  const supportingFacts = section.key === 'setup' ? factsOf(body, 'commands')
    : section.key === 'technologies' ? factsOf(body, 'dependencies') : undefined

  return <div ref={content} onClick={event => {
    const link = event.target instanceof Element ? event.target.closest('a.cite') : null
    if (!link) return
    const target = link.getAttribute('href')?.slice(1)
    // Reveal the excerpt before the browser follows its native citation anchor.
    const excerpt = Array.from(content.current?.querySelectorAll('details') ?? []).find(item => item.id === target)
    if (excerpt) excerpt.open = true
  }}>
    {section.error && <Failed message={`This section could not be written. ${section.error}`} />}
    {section.statements.length > 0 ? <>
      <Statements statements={expanded ? section.statements : section.statements.slice(0, limit)}
        sources={section.sources} />
      {more && <Button kind="ghost" onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}>{expanded ? 'Show less' : `Read ${section.statements.length - limit} more point${section.statements.length - limit === 1 ? '' : 's'}`}</Button>}
    </> : !section.error && <Missing what={section.missing_information || 'No evidence was found for this topic.'}
      checked="The excerpts retrieved for this topic" />}
    {!!section.statements.length && section.missing_information && <Missing what={section.missing_information} />}
    {section.key === 'setup' && <p className="ov-hint">These instructions come from the project documentation. Nothing here was run.</p>}
    {supportingFacts && <FactDetails group={supportingFacts} open />}
    {section.key === 'architecture' && <Link className="ov-inline-link" to="/architecture">
      Explore the interactive architecture map <Icon name="chevron" size={15} /></Link>}
    <div className="ov-evidence">
      <div className="ov-section-label"><Icon name="link" size={16} /><h3>Evidence behind this topic</h3>
        <span className="ov-count">{section.sources.length}</span></div>
      <p className="ov-hint">Open an excerpt to check the original context.</p>
      {section.sources.map((source, i) => <details className="ov-source" id={`src-${source.source_id}`} key={source.source_id}>
        <summary><span className="ov-source-number">{i + 1}</span><span className="ov-source-path">{sourcePath(source.path)}</span>
          <Chip tone="quiet">{originOf(source.path, source.url)}</Chip></summary>
        <div className="ov-disclosure-body">
          <SourceLink path={source.path} line={source.start} url={source.url ?? undefined} />
          <pre>{source.text}</pre>
        </div>
      </details>)}
      {!section.sources.length && <p className="ov-hint">No source excerpts were saved for this topic.</p>}
    </div>
  </div>
}

function ReadingList({ body }: { body: Overview }) {
  const [read, setRead] = useState<string[]>([])
  return <>
    <div className="ov-reading-progress"><p><strong>{read.length} of {body.reading_order.length}</strong> marked as read</p>
      {read.length > 0 && <Button kind="ghost" onClick={() => setRead([])}>Reset checklist</Button>}
    </div>
    <p className="ov-hint">Your checklist lasts while this overview is open. The order comes from indexed file paths.</p>
    {body.reading_order.length ? <ol className="ov-reading-list">{body.reading_order.map((item, i) => <li
      key={item.path} className={read.includes(item.path) ? 'is-read' : ''}>
      <span className="read-n">{String(i + 1).padStart(2, '0')}</span>
      <div className="read-body"><SourceLink path={item.path} url={item.url} />
        <p className="read-why">{item.why}</p></div>
      <label className="ov-read-check"><input type="checkbox" checked={read.includes(item.path)}
        aria-label={`Mark ${item.path} as read`} onChange={e => setRead(e.target.checked
          ? [...read, item.path] : read.filter(path => path !== item.path))} /><span>Read</span></label>
    </li>)}</ol> : <Empty title="Nothing was indexed to order." />}
  </>
}

export function OverviewDashboard({ body, features, mode, building }: {
  body: Overview; features: Load<FeatureReply>; mode: OverviewMode; building: boolean
}) {
  const [picked, setPicked] = useState('purpose')
  const [query, setQuery] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const review = body.sections.filter(needsReview)
  const gaps = factsOf(body, 'gaps')
  const issueCount = review.length + (gaps?.items.length ?? 0)
  const sections = body.sections.map(s => ({ id: s.key, title: s.title,
    ...(TOPIC[s.key] ?? { label: s.title, icon: 'doc', hint: 'Explore the saved overview for this topic.' }),
    review: needsReview(s) }))
  const extras = [
    { id: '_features', label: 'Main features', icon: 'grid', hint: 'Feature groups found in the imported code.' },
    { id: '_facts', label: 'Facts from files', icon: 'doc', hint: 'Routes, dependencies, commands and other extracted facts.' },
    { id: '_reading', label: 'Reading checklist', icon: 'check', hint: 'A suggested path through the codebase.' },
    { id: '_review', label: 'Gaps & coverage', icon: 'warn', hint: 'See what needs checking and what this overview covers.' },
  ].map(item => ({ ...item, title: item.label, review: item.id === '_review' && issueCount > 0 }))
  const items = [...sections, ...extras]
  const active = items.find(item => item.id === picked) ?? items[0]
  const selected = body.sections.find(s => s.key === active.id)
  const visible = items.filter(item => `${item.id} ${item.label} ${item.title} ${item.hint}`.toLowerCase().includes(query.toLowerCase().trim()))
  const featureRows = features.data?.available ? features.data.features : []
  const currentIndex = sections.findIndex(s => s.id === active.id)
  const select = (id: string) => {
    setPicked(id)
    heading.current?.focus({ preventScroll: true })
    heading.current?.scrollIntoView({ block: 'nearest' })
  }

  return <div className="ov-dashboard">
    <section className="ov-hero" aria-label="Project snapshot">
      <div className="ov-hero-main">
        <span className="ov-eyebrow">Your project at a glance</span>
        <h2>{body.repo.split('/').pop() || body.repo}</h2>
        <p>Start with the big picture. Follow a topic, inspect its evidence, or work through the reading list.</p>
        <div className="ov-hero-meta"><span><Icon name="nodes" size={14} />{body.branch}</span>
          <span className="mono">{body.commit?.slice(0, 7)}</span><span>{body.repo}</span></div>
      </div>
      <div className="ov-hero-aside">
        <span className="ov-saved-state"><span className="ov-status-dot" />
          {body.demo ? 'Demo overview' : building ? 'Build in progress' : body.complete ? 'Saved overview' : 'Partial overview'}</span>
        <Link to="/ask" className="ov-hero-action"><Icon name="chat" size={17} />Ask about this project<Icon name="chevron" size={16} /></Link>
        <Link to="/architecture" className="ov-hero-secondary">Explore architecture <Icon name="external" size={13} /></Link>
      </div>
    </section>

    <div className="ov-metrics" aria-label="Overview shortcuts">
      {[
        { label: 'Topics written', value: `${body.topics_done}/${body.topics_total}`, icon: 'doc', to: sections[0]?.id ?? '_facts', hint: 'Explore the overview', tone: 'teal' },
        { label: 'Files indexed', value: body.files_indexed, icon: 'database', to: '_facts', hint: `${body.files_skipped} files skipped`, tone: 'blue' },
        { label: 'Feature groups', value: features.loading ? '…' : features.error || !features.data?.available ? '—' : featureRows.length,
          icon: 'grid', to: '_features', hint: features.error ? 'Read unavailable' : 'Explore grouped routes', tone: 'violet' },
        { label: 'Review items', value: issueCount, icon: 'warn', to: '_review', hint: 'Topic flags & known gaps', tone: 'amber' },
      ].map(metric => <button type="button" className={`ov-metric ov-metric-${metric.tone}`} key={metric.label}
        onClick={() => select(metric.to)} aria-controls="ov-panel">
        <span className="ov-metric-top"><span className="ov-metric-icon"><Icon name={metric.icon} size={19} /></span>
          <Icon name="chevron" size={15} /></span>
        <strong>{metric.value}</strong><span className="ov-metric-label">{metric.label}</span>
        <span className="ov-metric-hint">{metric.hint}</span>
      </button>)}
    </div>

    <div className="ov-workspace">
      <nav className="ov-explorer" aria-label="Overview topics">
        <div className="ov-explorer-head"><h2>Explore</h2><span className="ov-count">{items.length}</span></div>
        <label className="ov-search"><Icon name="search" size={15} />
          <input type="search" aria-label="Find a topic" placeholder="Find a topic…" value={query}
            onChange={e => setQuery(e.target.value)} /></label>
        <div className="ov-topic-list">{visible.map(item => <button type="button" key={item.id}
          className={`ov-topic ${item.id === active.id ? 'is-active' : ''} ${item.id === '_features' ? 'ov-topic-divider' : ''}`}
          aria-current={item.id === active.id ? 'true' : undefined} aria-controls="ov-panel" onClick={() => select(item.id)}>
          <Icon name={item.icon} size={16} /><span>{item.label}</span>
          {item.review && <span className="ov-review-dot" title="Contains gaps or items to check" aria-label="Needs review" />}
        </button>)}</div>
        {!visible.length && <div className="ov-search-empty"><p>No matching topics.</p>
          <Button kind="ghost" onClick={() => setQuery('')}>Clear search</Button></div>}
        <p className="ov-explorer-foot"><Icon name="lock" size={13} />Exploring uses saved content.</p>
      </nav>

      <section id="ov-panel" className="ov-panel" aria-labelledby="ov-topic-heading">
        <header className="ov-panel-head"><div>
          <span className="ov-eyebrow">{selected ? `Topic ${currentIndex + 1} / ${sections.length}` : 'Project resources'}</span>
          <h2 ref={heading} tabIndex={-1} id="ov-topic-heading">{active.title}</h2>
          <p>{active.hint}</p></div>
          <span className="ov-panel-icon"><Icon name={active.icon} size={24} /></span>
        </header>
        <div className="ov-panel-body">
          {selected && <TopicContent key={`${selected.key}:${mode}`} section={selected} mode={mode} body={body} />}
          {active.id === '_features' && <>
            <p className="ov-hint">Grouped from routes, the files they reach and tickets that name them.</p>
            {features.loading ? <Loading what="features" /> : features.error
              ? <Failed message={features.error} onRetry={features.reload} /> : featureRows.length
              ? <div className="ov-feature-grid">{featureRows.map(feature => <div className="ov-feature" key={feature.id}>
                <span className="ov-feature-icon"><Icon name="grid" size={18} /></span><h3>{feature.name}</h3>
                <p>{feature.route_count} route{feature.route_count === 1 ? '' : 's'} <span>·</span> {feature.file_count} file{feature.file_count === 1 ? '' : 's'}</p>
                {feature.gap_count > 0 && <Chip tone="warn">{feature.gap_count} known gap{feature.gap_count === 1 ? '' : 's'}</Chip>}
                <Link to={`/features?feature=${encodeURIComponent(feature.id)}`}>Explore {feature.name} →</Link>
              </div>)}</div> : <Empty title="No features were derived."
                detail={features.data?.unclustered?.note || 'No feature groups are available for the current information.'} />}
          </>}
          {active.id === '_facts' && <>
            <p className="ov-hint">Extracted directly from the imported files. Open a group to see its details and source lines.</p>
            {body.facts.map(group => <FactDetails key={group.key} group={group} />)}
            {!body.facts.length && <Empty title="No extracted facts are available." />}
          </>}
          {/* Keep the checklist across topic changes without persisting source data in browser storage. */}
          <div hidden={active.id !== '_reading'}><ReadingList body={body} /></div>
          {active.id === '_review' && <>
            <div className="ov-coverage"><h3>What this overview covers</h3><p>{body.scope_note}</p>
              <dl><div><dt>Repository</dt><dd>{body.repo}</dd></div>
                <div><dt>{body.repo.startsWith('local:') ? 'Snapshot' : 'Commit'}</dt><dd className="mono">{body.commit?.slice(0, 7)}</dd></div>
                <div><dt>Files</dt><dd>{body.files_indexed} indexed · {body.files_skipped} skipped</dd></div>
                <div><dt>Topics written</dt><dd>{body.topics_done} of {body.topics_total}</dd></div>
                {body.scanned_at && <div><dt>Sources read</dt><dd>{new Date(body.scanned_at).toLocaleString()}</dd></div>}
              </dl>
            </div>
            <h3>Topics to review</h3>
            <p className="ov-hint">Flags include missing information, failed sections and claims that need checking.</p>
            {review.map(s => <button className="ov-review-item" key={s.key} type="button" onClick={() => select(s.key)}>
              <Icon name="warn" size={17} /><span><strong>{s.title}</strong><span>{s.error
                ? `Build failed: ${s.error}` : s.missing_information || 'Open this topic to inspect its evidence and qualifications.'}</span></span>
              <Icon name="chevron" size={16} /></button>)}
            {!review.length && <p className="ov-hint">No topic flags were recorded. This is not a completeness or accuracy score.</p>}
            {gaps && <FactDetails group={gaps} open />}
          </>}
        </div>
        {selected && <footer className="ov-panel-footer">
          <Button kind="ghost" disabled={currentIndex === 0} onClick={() => select(sections[currentIndex - 1].id)}>Previous topic</Button>
          <Button kind="secondary" onClick={() => select(sections[currentIndex + 1]?.id ?? '_reading')}>
            {sections[currentIndex + 1] ? `Next: ${sections[currentIndex + 1].label}` : 'Open reading checklist'}<Icon name="chevron" size={14} />
          </Button>
        </footer>}
      </section>
    </div>
  </div>
}
