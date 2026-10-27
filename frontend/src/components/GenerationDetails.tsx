import type { Generation } from '../lib/ai'

export function GenerationDetails({ value, cached = false }: { value?: Generation; cached?: boolean }) {
  if (!value) return null
  const errors = value.attempts?.filter(a=>a.provider!=='ollama').map(a=>a.error)??[]
  const help = value.model ? '' : errors.includes('disabled')
    ? 'Cloud providers were disabled for this request. Enable a provider and save routing in AI settings; a saved key or successful connection test alone does not enable it. Project cloud permission is also required.'
    : errors.includes('private_source_requires_local')
    ? 'This request included sources without cloud approval. Start local Ollama, or review this project’s Jira and Slack source permissions in AI settings. Local folders remain local.'
    : errors.includes('privacy_not_approved') || errors.includes('public_repository_unconfirmed')
    ? 'Cloud processing was not approved for this project. Review its source permissions in AI settings.'
    : errors.includes('repository_access_unconfirmed') ? 'Access to the selected GitHub snapshot could not be confirmed. Check your source connection and refresh the repository before retrying.'
    : errors.includes('missing_key') || errors.includes('free_account_unconfirmed')
    ? 'This account needs its own saved API key and current free-plan confirmation in AI settings.' : ''
  const localTimeout = !value.model && value.attempts?.some(a=>a.provider==='ollama'&&a.error==='timeout')
  const localOffline = !value.model && value.attempts?.some(a=>a.provider==='ollama'&&a.error==='connection')
  return <>{help&&<p className="generation-setup" role="status">{help} {localTimeout?'The local Ollama fallback also timed out. ':''}<a href="/settings">Open AI settings</a></p>}
  {localOffline&&<p role="status">The last attempt could not connect to Ollama. Start it with <code>ollama serve</code>, then retry the failed topics.</p>}
  {localTimeout&&!help&&<p role="status">The local model did not finish within its time limit. Review the model and source permissions before retrying.</p>}
  <details className="generation-details"><summary>
    {value.model ? `${value.provider} / ${value.model}` : 'Generation unavailable'}
    {cached ? ' · Saved topic reused' : value.latency_seconds !== undefined ? ` · ${value.latency_seconds}s` : ''}
  </summary>
    <p>{value.usage_source === 'provider' ? `Provider-reported usage: ${value.input_tokens} input, ${value.output_tokens} output tokens.` : 'Token usage was not reported.'} Model choice does not verify factual correctness.</p>
    {!!value.attempts?.length && <ul>{value.attempts.map((a,i) => <li key={i}>{a.provider} / {a.model}: {a.status}{a.error ? ` (${a.error.replaceAll('_',' ')})` : ''}</li>)}</ul>}
  </details></>
}
