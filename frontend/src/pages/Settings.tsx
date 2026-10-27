import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, Failed, Loading, PageHead } from '../components/ui'
import { post } from '../lib/api'
import { useApi } from '../lib/useApi'
import type { AISettings, ConnectionTest, Limits, Routing, Target } from '../lib/ai'
import './settings.css'

const encode = (target: Target) => `${target.provider}|${target.model}`
const decode = (value: string): Target => { const [provider,model] = value.split('|'); return {provider,model} }
const names = {rpm:'Requests / minute',rpd:'Requests / day',tpm:'Tokens / minute',tpd:'Tokens / day'}
function LimitFields({ label, value, change }: {label:string;value:Limits;change:(value:Limits)=>void}) {
  return <fieldset className="ai-limits"><legend>{label}</legend>{(Object.keys(names) as (keyof Limits)[]).map(key =>
    <label key={key}>{names[key]}<input aria-label={`${label}: ${names[key]}`} type="number" min="1" value={value[key]}
      onChange={e => change({...value,[key]:Number(e.target.value)})}/></label>)}</fieldset>
}
export function Settings() {
  const reply = useApi<AISettings>('/api/ai')
  const [config,setConfig] = useState<Routing | null>(null)
  const [keys,setKeys] = useState<Record<string,string>>({})
  const [consent,setConsent] = useState<Record<string,boolean>>({})
  const [tests,setTests] = useState<Record<string,ConnectionTest>>({})
  const [testModels,setTestModels] = useState<Record<string,string>>({})
  const [testing,setTesting] = useState('')
  const testConnection = async (target:Target) => {
    setBusy(true); setTesting(target.provider); setError('')
    try {
      const result = await post('/api/ai/test',target) as ConnectionTest
      setTests(previous=>({...previous,[target.provider]:result}))
    } catch(e) { setError(e instanceof Error ? e.message : 'Connection test failed.') }
    finally { setBusy(false); setTesting('') }
  }
  const [approved,setApproved] = useState<string[]>([])
  const [publicConsent,setPublicConsent] = useState(false)
  const [sourceTypes,setSourceTypes] = useState<string[]>(['github'])
  const [busy,setBusy] = useState(false), [note,setNote] = useState(''), [error,setError] = useState('')
  useEffect(() => { if (reply.data) { setConfig(reply.data.config); setApproved(reply.data.permission.providers); setSourceTypes(reply.data.permission.source_types??['github']); setPublicConsent(false) } },[reply.data])
  const act = async (path:string,value:unknown,message:string) => {
    setBusy(true); setNote(''); setError('')
    try { await post(path,value); setNote(message); reply.reload() }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save AI settings.') }
    finally { setBusy(false) }
  }
  if (reply.error) return <Failed message={reply.error} onRetry={reply.reload}/>
  if (!reply.data || !config) return <Loading what="AI settings"/>
  const data = reply.data
  const dirty = JSON.stringify(config)!==JSON.stringify(data.config)
  const cloudSaved = Object.values(data.config.providers).some(p=>p.enabled)
  const permitted = data.permission.providers.filter(p=>data.config.providers[p]?.enabled)
  const models = [...data.catalog,{provider:'ollama',model:config.local_model,label:`Local ${config.local_model}`}]
  const localModel = (model:string) => setConfig({...config,local_model:model,
    manual:config.manual.provider==='ollama'?{provider:'ollama',model}:config.manual,
    routes:Object.fromEntries(Object.entries(config.routes).map(([feature,route])=>[feature,route.map(t=>t.provider==='ollama'?{provider:'ollama',model}:t)]))})
  const addFallback = (feature:string) => {
    const choice=models.find(m=>!config.routes[feature].some(t=>t.provider===m.provider))
    if(choice) setConfig({...config,routes:{...config.routes,[feature]:[...config.routes[feature],{provider:choice.provider,model:choice.model}]}})
  }
  const select = (label:string,value:Target,change:(target:Target)=>void) => <select aria-label={label} value={encode(value)} onChange={e=>change(decode(e.target.value))}>
    {models.map(m=><option key={encode(m)} value={encode(m)}>{m.label}</option>)}
  </select>
  return <div className="ai-settings">
    <PageHead title="AI settings" lead="Choose models by feature, control cloud permissions, and inspect usage." actions={<Button disabled={busy||dirty} onClick={reply.reload}>Refresh status</Button>}/>
    {dirty&&<div className="ai-unsaved" role="status"><strong>Routing changes are not saved.</strong><p>Generation still uses the last saved settings. Checking Enable alone does not activate a provider.</p>
      <Button kind="primary" disabled={busy} onClick={()=>void act('/api/ai/config',config,'Routing and local limits saved.')}>Save AI routing changes</Button>
      <Button disabled={busy} onClick={()=>setConfig(data.config)}>Discard routing changes</Button></div>}
    <Card title="Current saved setup" aside={<Chip tone={cloudSaved?'info':'warn'}>{cloudSaved?'Cloud routing saved':'Cloud disabled'}</Chip>}>
      <p>{cloudSaved?'At least one cloud provider is enabled in saved routing.':'Gemini and Groq are disabled in your saved settings. A saved key or successful connection test does not enable them.'}</p>
      <p>{permitted.length?`Project permission saved for: ${permitted.join(', ')}. Source access, free-plan confirmation and quotas are checked before every request.`:'This project has no enabled, approved cloud provider. Generation will use Ollama when local fallback is allowed.'}</p>
      <ol><li>Save your own Gemini or Groq key and confirm its free account.</li><li>Check Enable for the provider, then save the routing changes.</li><li>Approve the connected GitHub repository for the selected providers below.</li><li>Return to the feature and retry generation. Failed overview topics can be retried.</li></ol>
      <p>AI keys, saved routing and project permissions belong to the signed-in account. A new member must set up their own AI access.</p>
    </Card>
    <Card title="Free services only">
      <p>{data.policy}</p><p>Model catalog reviewed {data.catalog_reviewed}; review due {data.catalog_expires}. {data.catalog_current?'':'Cloud generation is blocked until the catalog is reviewed.'}</p>
      <p>Gemini's free service may use submitted content to improve products. Approve only content you are authorized to share with the selected provider. This app cannot independently verify an account's billing plan.</p>
    </Card>
    {note && <p role="status">{note}</p>}{error && <Failed message={error}/>}
    <div className="ai-provider-grid">{Object.entries(config.providers).map(([provider,settings])=><Card key={provider} title={provider==='gemini'?'Google Gemini':'Groq'} aside={<Chip>{data.config.providers[provider].enabled?'Enabled in saved settings':'Disabled in saved settings'}</Chip>}>
      <p>{data.providers[provider].key_configured?'Key saved in your secure vault.':'No key configured.'} {data.providers[provider].free_account_confirmed?'Free plan manually confirmed (valid for seven days).':'Free-plan confirmation required before enabling.'}</p>
      <label>API key<input aria-label={`${provider} API key`} type="password" autoComplete="new-password" value={keys[provider]??''} disabled={!data.secure_storage||busy}
        onChange={e=>setKeys({...keys,[provider]:e.target.value})}/></label>
      <Button disabled={busy||!keys[provider]||!data.secure_storage} onClick={()=>{const key=keys[provider];setKeys({...keys,[provider]:''});void act('/api/ai/key',{provider,key},'Key saved. Provider stays disabled until you confirm the account and enable it.')}}>Save {provider} key</Button>
      {!data.secure_storage&&<p>Secure credential storage is unavailable in this session.</p>}
      <label className="ai-check"><input type="checkbox" checked={consent[provider]??false} onChange={e=>setConsent({...consent,[provider]:e.target.checked})}/>I checked this account: free plan, billing disabled, no promotional credits.</label>
      <Button disabled={busy||!consent[provider]||!data.providers[provider].key_configured} onClick={()=>void act('/api/ai/confirmation',{provider,free_plan_without_billing_or_credits:true},'Manual confirmation saved for this key. No API request was sent.')}>Confirm {provider} free plan</Button>
      <p>Test the saved key with a small synthetic prompt. This uses free quota and leaves project cloud access and routing unchanged.</p>
      <label>Connection test model<select aria-label={`${provider} connection model`} disabled={busy} value={testModels[provider]??data.catalog.find(m=>m.provider===provider)?.model}
        onChange={e=>setTestModels({...testModels,[provider]:e.target.value})}>{data.catalog.filter(m=>m.provider===provider).map(m=><option key={m.model} value={m.model}>{m.label}</option>)}</select></label>
      <Button disabled={busy||!data.providers[provider].key_configured||!data.providers[provider].free_account_confirmed||!data.catalog_current}
        onClick={()=>{const model=testModels[provider]??data.catalog.find(m=>m.provider===provider)?.model; if(model) void testConnection({provider,model})}}>{testing===provider?'Testing…':`Test ${provider} connection`}</Button>
      {tests[provider]&&<p role="status">{tests[provider].ok?`Connection passed: ${tests[provider].model} responded in ${tests[provider].generation?.latency_seconds??'?'}s with valid test JSON.`:`Connection unavailable: ${tests[provider].code??'unknown error'}. Check the saved key, free-plan confirmation, quotas and provider status.`} A connection test does not rate answer accuracy.</p>}
      <label className="ai-check"><input type="checkbox" checked={settings.enabled} disabled={!data.providers[provider].free_account_confirmed||!data.catalog_current} onChange={e=>setConfig({...config,providers:{...config.providers,[provider]:{...settings,enabled:e.target.checked}}})}/>Enable {provider} in saved routes</label>
      {settings.enabled!==data.config.providers[provider].enabled&&<p role="status">This {provider} enable/disable change is not saved. Use Save AI routing changes above.</p>}
      <LimitFields label={`${provider} local caps`} value={settings.limits} change={limits=>setConfig({...config,providers:{...config.providers,[provider]:{...settings,limits}}})}/>
      <label>Timeout (seconds)<input aria-label={`${provider} timeout`} type="number" min="5" max="180" value={settings.timeout_seconds} onChange={e=>setConfig({...config,providers:{...config.providers,[provider]:{...settings,timeout_seconds:Number(e.target.value)}}})}/></label>
      <p>{provider==='gemini'?'Default caps are conservative local estimates. Copy your active project limits from AI Studio.':'Configured caps cannot exceed the reviewed Groq free-plan limits.'} <a href={data.catalog.find(m=>m.provider===provider)?.pricing} target="_blank" rel="noreferrer">Provider limits and pricing</a></p>
    </Card>)}</div>
    <Card title="Routing and local fallback">
      <div className="ai-form-grid"><label>Routing mode<select value={config.mode} onChange={e=>setConfig({...config,mode:e.target.value as Routing['mode']})}><option value="automatic">Automatic by feature</option><option value="manual">Manual model for testing</option></select></label>
        <label>Local Ollama model<input value={config.local_model} onChange={e=>localModel(e.target.value)}/></label>
        <label>Overview topic concurrency<input type="number" min="1" max="4" value={config.overview_concurrency} onChange={e=>setConfig({...config,overview_concurrency:Number(e.target.value)})}/></label></div>
      <label className="ai-check"><input type="checkbox" checked={config.local_enabled} onChange={e=>setConfig({...config,local_enabled:e.target.checked})}/>Allow locally installed Ollama models</label>
      <label>Minimum gap between overview requests (seconds)<input type="number" min="0" max="120" value={config.overview_interval_seconds??0} onChange={e=>setConfig({...config,overview_interval_seconds:Number(e.target.value)})}/></label>
      <p>A gap can spread overview requests within free-tier limits. Zero starts them without an added delay. Completed cached topics are reused immediately; waiting can be cancelled.</p>
      {config.mode==='manual'&&<><label>Manual model{select('Manual model',config.manual,manual=>setConfig({...config,manual}))}</label><label className="ai-check"><input type="checkbox" checked={config.manual_fallback} onChange={e=>setConfig({...config,manual_fallback:e.target.checked})}/>Allow fallback during manual tests (leave off for a controlled comparison)</label></>}
      <p>Each cloud provider is attempted at most once per generation. Local fallback is added when allowed. Privacy rules apply to every attempt.</p>
      <div className="ai-table-wrap"><table><thead><tr><th>Feature</th><th>Primary</th><th>Fallback order</th></tr></thead><tbody>{Object.entries(data.features).map(([feature,label])=><tr key={feature}><th>{label}</th><td>{select(`${label} primary`,config.routes[feature][0],target=>{const route=[...config.routes[feature]];route[0]=target;setConfig({...config,routes:{...config.routes,[feature]:route}})})}</td><td>{config.routes[feature].slice(1).map((target,i)=><div key={i}>{select(`${label} fallback ${i+1}`,target,next=>{const route=[...config.routes[feature]];route[i+1]=next;setConfig({...config,routes:{...config.routes,[feature]:route}})})}<Button onClick={()=>setConfig({...config,routes:{...config.routes,[feature]:config.routes[feature].filter((_,n)=>n!==i+1)}})}>Remove fallback {i+1}</Button></div>)}{config.routes[feature].length<3&&<Button onClick={()=>addFallback(feature)}>Add fallback</Button>}</td></tr>)}</tbody></table></div>
      <LimitFields label="Project cloud caps" value={config.project_limits} change={project_limits=>setConfig({...config,project_limits})}/>
      <Button kind="primary" disabled={busy} onClick={()=>void act('/api/ai/config',config,'Routing and local limits saved.')}>Save routing and limits</Button>
    </Card>
    <Card title="Project cloud permission" sub={data.repo||'No project selected'}>
      <p>Public and private GitHub repositories are supported. Approval is separate from enabling a provider. Source access and freshness are checked before and after generation. Jira and Slack stay local unless you approve them below for this project and the selected providers. Local folders and conversation history remain local.</p>
      <p>GitHub code and documentation are included. Saved source approval: {(data.permission.source_types??(data.permission.providers.length?['github']:[])).join(', ')||'none'}.</p>
      {data.permission.classification==='public'&&<p>This project has an older public-only approval. To include a private GitHub repository, review and save the approval below.</p>}
      {['jira','slack'].map(source=><label className="ai-check" key={source}><input type="checkbox" checked={sourceTypes.includes(source)} onChange={e=>setSourceTypes(e.target.checked?[...sourceTypes,source]:sourceTypes.filter(s=>s!==source))}/>{source==='jira'?'Jira ticket excerpts':'Slack message excerpts'} may be sent for this project</label>)}
      {Object.keys(config.providers).map(provider=><label className="ai-check" key={provider}><input type="checkbox" checked={approved.includes(provider)} onChange={e=>setApproved(e.target.checked?[...approved,provider]:approved.filter(p=>p!==provider))}/>{provider} may process this project's selected source excerpts</label>)}
      <label className="ai-check"><input type="checkbox" checked={publicConsent} onChange={e=>setPublicConsent(e.target.checked)}/>I authorize sending the selected sources' retrieved excerpts to the selected cloud providers.</label>
      <Button disabled={busy||!data.repo||(approved.length>0&&!publicConsent)} onClick={()=>void act('/api/ai/permission',{providers:approved,approved_github_content:publicConsent,approved_jira_content:sourceTypes.includes('jira'),approved_slack_content:sourceTypes.includes('slack')},'Project cloud permission saved.')}>Save project permission</Button>
      <Button disabled={busy||!data.repo} onClick={()=>void act('/api/ai/permission',{providers:[]},'Cloud permission revoked for this project.')}>Revoke all project cloud access</Button>
    </Card>
    <Card title="Usage and provider status" sub="This workspace, last 24 hours">
      {data.monitoring&&<p>Activity log: <code>{data.monitoring.file}</code> inside this workspace's data folder. Records requests, background jobs, model routing, fallbacks, quotas and timings. Keys, prompts and source text are excluded. Rotates at {Math.round(data.monitoring.max_bytes/1024/1024)} MB with {data.monitoring.backups} backups. Refresh status after testing to update usage.</p>}
      <p>{data.usage.usage_note}</p><p>{data.usage.quota_scope}</p>
      <details><summary>Shared local quota estimates</summary><ul>{data.usage.shared_local_estimates?.map((u,i)=><li key={i}>{u.provider}, rolling {u.window_seconds===60?'minute':'24 hours'}: {u.requests}/{u.request_cap} requests; {u.tokens}/{u.token_cap} reserved or reported tokens. {u.warning?'Near or above the configured cap; new requests may fall back.':''}</li>)}</ul></details>
      {data.usage.cooldowns.map(c=><p role="status" key={c.provider}>{c.provider}: {c.reason}; unavailable until {new Date(c.until_time*1000).toLocaleString()}.</p>)}
      {!data.usage.last_24_hours.length?<p>No generation requests recorded yet.</p>:<div className="ai-table-wrap"><table><thead><tr><th>Model / feature</th><th>Successful / requests</th><th>Average time</th><th>Reported tokens</th><th>Estimated reservation</th></tr></thead><tbody>{data.usage.last_24_hours.map((u,i)=><tr key={i}><td>{u.provider} / {u.model}<br/>{data.features[u.feature]??u.feature}</td><td>{u.successes} / {u.requests}</td><td>{u.average_seconds.toFixed(2)}s</td><td>{u.input_tokens} in / {u.output_tokens} out<br/>{u.usage_reported_requests} requests reported</td><td>{u.estimated_unreported_tokens} tokens with unknown actual usage</td></tr>)}</tbody></table></div>}
      <details><summary>Recent requests and provider-reported quota headers</summary><ul>{data.usage.recent.map(r=><li key={r.id}>{r.provider} / {r.model} · {r.feature} · {r.status} {r.error&&`(${r.error})`} · {r.elapsed.toFixed(2)}s
        <p>{Object.keys(r.reported).length?Object.entries(r.reported).map(([k,v])=>`${k}: ${v}`).join('; '):'No provider quota headers reported.'}</p></li>)}</ul><p>Groq request headers describe daily request quotas; token headers describe minute quotas. These are observations from that response, not a live balance.</p></details>
      <p>Use <Link to="/quality">Answer quality</Link> to compare identical questions and record human reviews. No cloud quality or speed comparison has been completed automatically.</p>
    </Card>
  </div>
}
