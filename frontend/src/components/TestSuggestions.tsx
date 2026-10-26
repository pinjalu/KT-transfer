import { Chip } from './ui'
import type { Source, TestSuggestion } from '../lib/answer'
import './test-suggestions.css'

export function TestSuggestions({ tests, sources }: { tests: TestSuggestion[]; sources: Source[] }) {
  if (!tests.length) return null
  return <section className="test-suggestions" aria-label="Suggested test plan">
    <p className="answer-label">Suggested tests</p>
    <p className="test-plan-note"><Chip tone="warn">Suggested · Not run</Chip> These are proposed checks. Expected results and assumptions need review; no project test was executed.</p>
    <ol className="test-plan-list">{tests.map((test, index) => <li key={index}>
      <h3>{index + 1}. {test.title}</h3>
      <p><strong>Why this matters:</strong> {test.reason}</p>
      <div className="test-plan-grid">
        <div><h4>Setup</h4><ul>{test.setup.map((item, i) => <li key={i}>{item}</li>)}</ul></div>
        <div><h4>Steps</h4><ol>{test.steps.map((item, i) => <li key={i}>{item}</li>)}</ol></div>
        <div><h4>Expected result to validate</h4><p>{test.expected_result}</p></div>
        <div><h4>How to verify</h4><ul>{test.verification.map((item, i) => <li key={i}>{item}</li>)}</ul></div>
      </div>
      {test.assumptions.length > 0 && <div className="test-plan-assumptions"><h4>Assumptions and prerequisites</h4><ul>{test.assumptions.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
      <details className="test-plan-evidence"><summary>Evidence motivating this test ({test.evidence.length})</summary>
        <p className="test-plan-note">These excerpts motivate the suggestion; they do not establish a passing test result.</p>
        {test.evidence.map((item, i) => {
          const source = sources.find(s => s.source_id === item.source_id)
          return <div key={i}><p><strong>{source?.path ?? 'Source unavailable'}</strong>{source && ` · Lines ${source.start}–${source.end}`}</p>
            <blockquote>{item.quote}</blockquote>
            {source?.url && <a href={source.url} target="_blank" rel="noreferrer">View source</a>}
          </div>
        })}
      </details>
    </li>)}</ol>
  </section>
}
