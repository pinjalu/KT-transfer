import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { TestSuggestions } from '../src/components/TestSuggestions'
import { conversationContext } from '../src/lib/answer'
import type { Answer, TestSuggestion } from '../src/lib/answer'

const plan: TestSuggestion = {
  title: 'Private image signing', reason: 'A public fallback can hide a broken signing path.',
  setup: ['Use a private fixture with a known object key.'],
  steps: ['Request the signed URL.', 'Fetch the private fixture with that URL.'],
  expected_result: 'The intended private image content should be returned.',
  verification: ['Compare the response bytes with the fixture and record the signing path.'],
  assumptions: ['Supply the actual fixture key before testing.'],
  evidence: [{ source_id: 'S1', quote: 'Private images require a signed URL.', kind: 'discussion' }],
  status: 'suggested_not_run',
}
const sources = [{ source_id: 'S1', path: 'jira/QA-24', start: 1, end: 4, text: plan.evidence[0].quote, url: 'https://example.atlassian.net/browse/QA-24' }]

it('shows actionable test fields and source evidence without implying execution', () => {
  const html = renderToStaticMarkup(<TestSuggestions tests={[plan]} sources={sources} />)
  for (const label of ['Why this matters', 'Setup', 'Steps', 'Expected result to validate', 'How to verify', 'Assumptions and prerequisites', 'Evidence motivating this test']) expect(html).toContain(label)
  expect(html).toContain('Suggested · Not run')
  expect(html).toContain('no project test was executed')
  expect(html).toContain(plan.verification[0])
  expect(html).toContain('jira/QA-24')
  expect(html).not.toContain('Verified from code')
  expect(html).not.toContain('<button')
})

it('renders source text as inert text and does not invent a source link', () => {
  const html = renderToStaticMarkup(<TestSuggestions tests={[{ ...plan, title: '<script>alert(1)</script>' }]} sources={[]} />)
  expect(html).toContain('&lt;script&gt;')
  expect(html).not.toContain('<script>')
  expect(html).toContain('Source unavailable')
  expect(html).not.toContain('href=')
})

it('carries test steps into follow-up context explicitly as unexecuted suggestions', () => {
  const answer = { repo: 'acme/images', commit: 'a'.repeat(40), knowledge_revision: 1, error: null,
    statements: [], test_suggestions: [plan], missing_information: '' } as unknown as Answer
  const history = conversationContext([{ question: 'Suggest one test', asked_at: '', answer, failed: null }], answer.repo, 1)
  expect(history?.turns[0].answer).toContain('Suggested test, not run: Private image signing')
  expect(history?.turns[0].answer).toContain('Fetch the private fixture')
})
