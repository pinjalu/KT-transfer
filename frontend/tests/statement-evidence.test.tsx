import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { Said } from '../src/components/Statements'
import type { Statement } from '../src/lib/answer'

const base: Statement = { text: 'The request returns a session token.', source_ids: ['S1'],
  support: 'supported', support_share: 1, about_this_project: true }
const sources = [{ source_id: 'S1', path: 'app.py', text: base.text, start: 1, end: 3, url: '' }]
const render = (statement: Statement) => renderToStaticMarkup(<Said statement={statement} sources={sources} citations={false} showContextMark={false} />)

it('shows suggestions even in the beginner mode with citations and context marks hidden', () => {
  const html = render({ ...base, evidence: { kind: 'suggestion', reason: 'Not proof of implementation.' } })
  expect(html).toContain('Suggested behaviour')
  expect(html).toContain('Not proof of implementation.')
  expect(html).not.toContain('Verified from code')
})

it('does not promote legacy answers or high word overlap to verified behaviour', () => {
  const html = render(base)
  expect(html).toContain('Behaviour not verified')
  expect(html).toContain('predates behaviour labels')
  expect(html).not.toContain('Verified from code')
})

it('shows the limits of a deterministic code check alongside its label', () => {
  const html = render({ ...base, evidence: { kind: 'verified_code', reason: 'Computed from code. The running application was not tested.' } })
  expect(html).toContain('Verified from code')
  expect(html).toContain('The running application was not tested.')
})

it('keeps test definitions separate from test execution and labels overlap honestly', () => {
  const html = render({ ...base, support: 'partly supported', evidence: { kind: 'test', reason: 'This test was not run.' } })
  expect(html).toContain('Test definition, not a test result')
  expect(html).toContain('Some text overlap')
  expect(html).not.toContain('Only part of this is in the excerpt')
})

it('puts repetitive code and mixed-evidence explanations in a closed disclosure', () => {
  for (const kind of ['code', 'mixed'] as const) {
    const html = render({ ...base, evidence: { kind, reason: 'Long provenance explanation.' } })
    const container = document.createElement('div')
    container.innerHTML = html
    const details = container.querySelector('details')!
    expect(details.open).toBe(false)
    expect(details.querySelector('summary')?.textContent).toBe('Source details')
    expect(details.textContent).toContain('Long provenance explanation.')
    details.remove()
    expect(container.textContent).not.toContain('Long provenance explanation.')
    expect(container.textContent).not.toContain('Code-based explanation')
    expect(container.textContent).not.toContain('Mixed evidence')
  }
})

it('renders headings and paragraphs without raw entities, empty list numbers or executable HTML', () => {
  const html = render({ ...base, text: '**What happens**&#x20;A request enters `app.py`.\n\n1.\n\n**Example:** A sample input.\n\n&#60;script&#62;alert(1)&#60;/script&#62;' })
  const container = document.createElement('div')
  container.innerHTML = html
  expect(container.querySelector('strong')?.textContent).toBe('What happens ')
  expect(container.querySelector('code')?.textContent).toBe('app.py')
  expect(container.querySelectorAll('.said-text p')).toHaveLength(3)
  expect(container.textContent).not.toContain('&#x20;')
  expect(container.textContent).not.toContain('1.')
  expect(container.querySelector('script')).toBeNull()
  expect(container.textContent).toContain('<script>alert(1)</script>')
})
