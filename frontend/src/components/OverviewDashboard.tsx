import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import { Statements } from './Statements'
import { GenerationDetails } from './GenerationDetails'
import { PlainLanguageGuide } from './PlainLanguageGuide'
import { Button, Chip, Empty, Failed, Loading, Missing, SourceLink } from './ui'
import { originOf, sourcePath } from '../lib/answer'
import { factsOf } from '../lib/overview'
import { projectName } from '../lib/project'
import type { FactGroup, Overview, Section } from '../lib/overview'
import type { Load } from '../lib/useApi'
import type { FeatureList } from '../lib/features'

export type OverviewMode = 'Beginner' | 'Developer' | 'Architect'
export type FeatureReply = FeatureList

const TOPIC: Record<string, { label: string; icon: string; hint: string }> = {
  purpose: { label: 'Start here', icon: 'home', hint: 'The whole project, with an example input, its journey and the result.' },
  technologies: { label: 'Technology', icon: 'grid', hint: 'The tools it uses and the role of each one.' },
  architecture: { label: 'Code structure', icon: 'nodes', hint: 'The main parts, what each does and how they connect.' },
  setup: { label: 'Getting started', icon: 'wrench', hint: 'Tools, settings and startup commands from this project’s files.' },
  flows: { label: 'Step by step', icon: 'send', hint: 'A real example: what the user sends, how this system handles it, and what comes back.' },
  interfaces: { label: 'Ways to use it', icon: 'link', hint: 'How people and other programs ask it to do something.' },
  data: { label: 'Data & settings', icon: 'database', hint: 'What the project remembers and which settings change how it works.' },
  testing: { label: 'Testing', icon: 'check', hint: 'Understand what the existing checks cover.' },
  decisions: { label: 'Team context', icon: 'people', hint: 'What the imported tickets and discussions say.' },
}

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

function Explanation({ section, mode }: { section: Section; mode: OverviewMode }) {
  return <>
    {section.error && <Failed message={`This section could not be written. ${section.error}`} />}
    {section.generation && (mode === 'Beginner' ? <details className="ov-disclosure"><summary>How this explanation was written</summary>
      <GenerationDetails value={section.generation} cached={section.cache_hit}/></details>
      : <GenerationDetails value={section.generation} cached={section.cache_hit}/>)}
    {section.statements.length > 0 ? <Statements statements={section.statements} sources={section.sources} />
      : !section.error && <Missing what={section.missing_information || 'No evidence was found for this topic.'}
        checked="The excerpts retrieved for this system and topic" />}
    {!!section.statements.length && section.missing_information && <Missing what={section.missing_information} />}
  </>
}

function TopicContent({ section, body, mode }: { section: Section; body: Overview; mode: OverviewMode }) {
  const content = useRef<HTMLDivElement>(null)
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
    {section.system_sections?.length ? section.system_sections.map(part => <section className="ov-system" key={part.system_id} aria-label={part.system_name}>
      <h3>{part.system_name}</h3><Explanation section={part} mode={mode} />
    </section>) : <Explanation section={section} mode={mode} />}
    {section.key === 'setup' && <p className="ov-hint">These instructions come from the project documentation. Nothing here was run.</p>}
    {supportingFacts && <FactDetails group={supportingFacts} open={mode !== 'Beginner' || section.key === 'setup'} />}
    {section.key === 'setup' && factsOf(body, 'environment') && <FactDetails group={factsOf(body, 'environment')!} />}
    {section.key === 'architecture' && <Link className="ov-inline-link" to="/architecture">
      Explore the interactive architecture map <Icon name="chevron" size={15} /></Link>}
    <div className="ov-evidence">
      <div className="ov-section-label"><Icon name="link" size={16} /><h3>Evidence behind this topic</h3>
        <span className="ov-count">{section.sources.length}</span></div>
      <p className="ov-hint">Open an excerpt to check the original context.</p>
      {section.sources.map((source, i) => <details className="ov-source" id={`src-${source.source_id}`} key={source.source_id}>
        <summary><span className="ov-source-number">{i + 1}</span><span className="ov-source-path">{sourcePath(source.path)}</span>
          <Chip tone="quiet">{source.system_name || originOf(source.path, source.url)}</Chip></summary>
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

export function OverviewDashboard({ body, features, mode, building, project }: {
  body: Overview; features: Load<FeatureReply>; mode: OverviewMode; building: boolean; project?: string
}) {
  const [picked, setPicked] = useState('purpose')
  const sourceKind = body.source_kind || (body.repo.startsWith('zip:') ? 'zip' : body.repo.startsWith('local:') ? 'local' : 'github')
  const [query, setQuery] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const review = body.sections.filter(needsReview)
  const written = body.successful_topics ?? body.sections.filter(section => !section.error).length
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
  const featureMismatch = features.data?.available && (features.data.repo !== body.repo
    || features.data.branch !== body.branch || features.data.scan_id !== body.scan_id || features.data.commit !== body.commit)
  const featureError = features.error || (featureMismatch ? 'Features do not match this overview’s project files. Refresh to load the current features.' : null)
  const featureRows = !featureError && features.data?.available ? features.data.features : []
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
        <h2>{project || projectName(null, body.repo)}</h2>
        {body.systems && body.systems.length > 1 && <p>Separate systems: {body.systems.map(system => system.name).join(' · ')}</p>}
        <p>Start with what the project does. Then learn its parts, follow one action, and see how to use it. Open source links when you want to check a detail.</p>
        <div className="ov-hero-meta">{sourceKind === 'github' ? <>
          <span><Icon name="nodes" size={14} />{body.branch}</span>
          <span className="mono">{body.commit?.slice(0, 7)}</span><span>{body.repo}</span>
        </> : <span><Icon name="doc" size={14} />{sourceKind === 'zip' ? 'ZIP project' : 'Local folder'}</span>}</div>
      </div>
      <div className="ov-hero-aside">
        <span className="ov-saved-state"><span className="ov-status-dot" />
          {body.demo ? 'Demo overview' : building ? 'Build in progress' : body.plain_language_update_available
            ? 'Explanation update available' : body.complete ? 'Saved overview' : 'Partial overview'}</span>
        <Link to="/ask" className="ov-hero-action"><Icon name="chat" size={17} />Ask about this project<Icon name="chevron" size={16} /></Link>
        <Link to="/architecture" className="ov-hero-secondary">Explore architecture <Icon name="external" size={13} /></Link>
      </div>
    </section>

    <div className="ov-metrics" aria-label="Overview shortcuts">
      {[
        { label: 'Topics written', value: `${written}/${body.topics_total}`, icon: 'doc', to: sections[0]?.id ?? '_facts', hint: 'Explore the overview', tone: 'teal' },
        { label: 'Files indexed', value: body.files_indexed, icon: 'database', to: '_facts', hint: `${body.files_skipped} files skipped`, tone: 'blue' },
        { label: 'Feature groups', value: features.loading ? '…' : featureError || !features.data?.available ? '—' : featureRows.length,
          icon: 'grid', to: '_features', hint: featureError ? 'Read unavailable' : 'Explore grouped routes', tone: 'violet' },
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
          {selected && <TopicContent key={`${selected.key}:${mode}`} section={selected} body={body} mode={mode} />}
          {mode === 'Beginner' && <PlainLanguageGuide topic={active.id} />}
          {active.id === '_features' && <>
            <p className="ov-hint">Grouped from routes, the files they reach and tickets that name them.</p>
            {features.loading ? <Loading what="features" detail="Finding features in this project’s files. Results appear after the current read finishes." /> : featureError
              ? <Failed message={featureError} onRetry={features.reload} /> : featureRows.length
              ? <div className="ov-feature-grid">{featureRows.map(feature => <div className="ov-feature" key={feature.id}>
                <span className="ov-feature-icon"><Icon name="grid" size={18} /></span><h3>{feature.name}</h3>
                <p>{feature.route_count} route{feature.route_count === 1 ? '' : 's'} <span>·</span> {feature.file_count} file{feature.file_count === 1 ? '' : 's'}</p>
                {feature.gap_count > 0 && <Chip tone="warn">{feature.gap_count} known gap{feature.gap_count === 1 ? '' : 's'}</Chip>}
                {body.overview_scope?.startsWith('local://')
                  ? <p className="ov-hint">Found in this local folder.</p>
                  : <Link to={`/features?feature=${encodeURIComponent(feature.id)}`}>Explore {feature.name} →</Link>}
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
              <dl><div><dt>{sourceKind === 'github' ? 'Repository' : 'Project'}</dt><dd>{sourceKind === 'github' ? body.repo : project || projectName(null, body.repo)}</dd></div>
                {sourceKind === 'github' && <div><dt>Commit</dt><dd className="mono">{body.commit?.slice(0, 7)}</dd></div>}
                <div><dt>Files</dt><dd>{body.files_indexed} indexed · {body.files_skipped} skipped</dd></div>
                <div><dt>Topics written</dt><dd>{written} of {body.topics_total}</dd></div>
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
