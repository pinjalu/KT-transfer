import type { ReactNode } from 'react'
import { Icon } from './Icon'

export function PageHead({ title, lead, actions }:
  { title: string; lead?: string; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {lead && <p className="page-lead">{lead}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

export function Card({ title, sub, aside, children, pad = true }:
  { title?: string; sub?: string; aside?: ReactNode; children: ReactNode; pad?: boolean }) {
  return (
    <section className="card">
      {(title || aside) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p className="card-sub">{sub}</p>}
          </div>
          {aside && <div className="card-aside">{aside}</div>}
        </div>
      )}
      <div className={pad ? 'card-body' : ''}>{children}</div>
    </section>
  )
}

type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'violet' | 'quiet' | 'accent'

export function Chip({ tone = 'quiet', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>
}

export function Dot({ tone = 'ok' }: { tone?: Tone }) {
  return <span className={`dot dot-${tone}`} aria-hidden="true" />
}

export function Button({ kind = 'secondary', icon, children, ...rest }:
  { kind?: 'primary' | 'secondary' | 'ghost' | 'danger'; icon?: string; children: ReactNode }
  & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`btn btn-${kind}`} type="button" {...rest}>
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  )
}

export function Tabs({ items, active, onPick }:
  { items: string[]; active: string; onPick: (t: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {items.map((t) => (
        <button key={t} role="tab" type="button" aria-selected={t === active}
                className={'tab' + (t === active ? ' is-active' : '')}
                onClick={() => onPick(t)}>{t}</button>
      ))}
    </div>
  )
}

export function Segmented({ items, active, onPick }:
  { items: string[]; active: string; onPick: (t: string) => void }) {
  return (
    <div className="segmented" role="group">
      {items.map((t) => (
        <button key={t} type="button" aria-pressed={t === active}
                className={'segment' + (t === active ? ' is-active' : '')}
                onClick={() => onPick(t)}>{t}</button>
      ))}
    </div>
  )
}

/** Confidence is shown, never dropped. `possible` means similarity only, with no line behind it. */
export function Confidence({ level }: { level: 'confirmed' | 'possible' }) {
  return level === 'confirmed'
    ? <Chip tone="ok">Confirmed</Chip>
    : <Chip tone="warn">Possible, needs checking</Chip>
}

/** The one way this application says it does not know something, with what it checked. */
export function Missing({ what, checked }: { what: string; checked?: string }) {
  return (
    <div className="missing">
      <span className="missing-icon"><Icon name="warn" size={16} /></span>
      <div>
        <p className="missing-what">{what}</p>
        {checked && <p className="missing-checked">Checked: {checked}</p>}
      </div>
    </div>
  )
}

export function Empty({ title, detail, action }:
  { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {detail && <p className="empty-detail">{detail}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  )
}

export function Loading({ what }: { what: string }) {
  return <div className="loading"><span className="spinner" aria-hidden="true" />Reading {what}…</div>
}

export function Failed({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="failed" role="alert">
      <span className="failed-icon"><Icon name="warn" size={16} /></span>
      <p>{message}</p>
      {onRetry && <Button kind="ghost" onClick={onRetry}>Try again</Button>}
    </div>
  )
}

/** A pointer into real code. Everything that claims something links to the line behind it. */
export function SourceLink({ path, line, url }: { path: string; line?: number; url?: string }) {
  const label = line ? `${path}:${line}` : path
  if (!url) return <span className="source-link mono">{label}</span>
  return (
    <a className="source-link mono" href={url} target="_blank" rel="noreferrer">
      {label}<Icon name="external" size={12} />
    </a>
  )
}
