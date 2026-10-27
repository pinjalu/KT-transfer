import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Settings } from '../src/pages/Settings'
import { GenerationDetails } from '../src/components/GenerationDetails'
import { get,post } from '../src/lib/api'
vi.mock('../src/lib/api',async original=>({...await original<typeof import('../src/lib/api')>(),get:vi.fn(),post:vi.fn()}))
let root:ReturnType<typeof createRoot>,node:HTMLDivElement,fixture:any
beforeEach(()=>{
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);vi.mocked(get).mockReset();vi.mocked(post).mockReset()
  const limits={rpm:2,rpd:10,tpm:8000,tpd:20000}
  fixture={config:{mode:'automatic',local_enabled:true,local_model:'qwen3:1.7b',manual:{provider:'ollama',model:'qwen3:1.7b'},manual_fallback:false,overview_concurrency:2,
    providers:{gemini:{enabled:false,limits,timeout_seconds:45},groq:{enabled:false,limits,timeout_seconds:45}},project_limits:limits,
    routes:{ask:[{provider:'groq',model:'openai/gpt-oss-120b'},{provider:'gemini',model:'gemini-3.8-flash'}]}},features:{ask:'Ask assistant'},
    catalog:[{provider:'groq',model:'openai/gpt-oss-120b',label:'Groq GPT-OSS 120B'},{provider:'gemini',model:'gemini-3.8-flash',label:'Gemini Flash'}],
    catalog_reviewed:'2026-10-27',catalog_expires:'2026-11-26',catalog_current:true,secure_storage:true,repo:'sample/public',permission:{providers:[]},
    providers:{gemini:{key_configured:false,free_account_confirmed:false},groq:{key_configured:false,free_account_confirmed:false}},policy:'Cloud is off by default.',
    usage:{usage_note:'Token reservations are local estimates.',quota_scope:'Shared quotas.',cooldowns:[],last_24_hours:[],recent:[]}}
  vi.mocked(get).mockResolvedValue(fixture);vi.mocked(post).mockResolvedValue({saved:true})
  node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(async()=>{await act(async()=>root.unmount());node.remove();vi.unstubAllGlobals()})
async function render(){await act(async()=>root.render(<MemoryRouter><Settings/></MemoryRouter>))}
const button=(text:string)=>Array.from(node.querySelectorAll('button')).find(b=>b.textContent===text)!
it('starts with cloud off, masked key fields and separate project approval',async()=>{
  await render()
  expect(node.textContent).toContain('Cloud disabled')
  expect(node.querySelectorAll('input[type=password]')).toHaveLength(2)
  expect(button('Confirm groq free plan').disabled).toBe(true)
  expect(button('Test groq connection').disabled).toBe(true)
  expect(node.textContent).toContain('cannot independently verify')
  expect(post).not.toHaveBeenCalled()
  await act(async()=>button('Save routing and limits').click())
  expect(post).toHaveBeenCalledWith('/api/ai/config',expect.objectContaining({providers:fixture.config.providers}))
})
it('tests a saved confirmed key with synthetic data while cloud stays disabled',async()=>{
  fixture.providers.groq={key_configured:true,free_account_confirmed:true}
  vi.mocked(post).mockResolvedValue({ok:true,provider:'groq',model:'openai/gpt-oss-120b',synthetic_only:true,generation:{latency_seconds:1.25}})
  await render()
  await act(async()=>button('Test groq connection').click())
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/ai/test',{provider:'groq',model:'openai/gpt-oss-120b'})
  expect(node.textContent).toContain('Connection passed: openai/gpt-oss-120b responded in 1.25s')
  expect(node.textContent).toContain('Cloud disabled')
})
it('reports failed provider tests without claiming fallback succeeded',async()=>{
  fixture.providers.groq={key_configured:true,free_account_confirmed:true}
  vi.mocked(post).mockResolvedValue({ok:false,provider:'groq',model:'openai/gpt-oss-120b',synthetic_only:true,code:'quota'})
  await render()
  await act(async()=>button('Test groq connection').click())
  expect(node.textContent).toContain('Connection unavailable: quota')
  expect(node.textContent).not.toContain('Connection passed')
})
it('allows a different diagnostic model without changing feature routing',async()=>{
  fixture.providers.gemini={key_configured:true,free_account_confirmed:true}
  fixture.catalog.push({provider:'gemini',model:'gemini-3.5-flash-lite',label:'Gemini Flash-Lite'})
  vi.mocked(post).mockResolvedValue({ok:true,provider:'gemini',model:'gemini-3.5-flash-lite',synthetic_only:true})
  await render()
  const select=node.querySelector('[aria-label="gemini connection model"]') as HTMLSelectElement
  await act(async()=>{select.value='gemini-3.5-flash-lite';select.dispatchEvent(new Event('change',{bubbles:true}))})
  await act(async()=>button('Test gemini connection').click())
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/ai/test',{provider:'gemini',model:'gemini-3.5-flash-lite'})
})
it('manual model testing stays pinned unless fallback is explicitly enabled',async()=>{
  await render()
  const mode=Array.from(node.querySelectorAll('select')).find(s=>s.value==='automatic')!
  await act(async()=>{mode.value='manual';mode.dispatchEvent(new Event('change',{bubbles:true}))})
  expect(node.querySelector('[aria-label="Manual model"]')).not.toBeNull()
  await act(async()=>button('Save routing and limits').click())
  expect(post).toHaveBeenCalledWith('/api/ai/config',expect.objectContaining({mode:'manual',manual_fallback:false}))
})
it('shows cooldowns and separates reported usage from estimates',async()=>{
  fixture.usage.cooldowns=[{provider:'groq',reason:'quota',until_time:1793000000}]
  fixture.usage.last_24_hours=[{provider:'groq',model:'model',feature:'ask',successes:1,requests:2,average_seconds:2.1,input_tokens:30,output_tokens:20,usage_reported_requests:1,estimated_unreported_tokens:500}]
  await render()
  expect(node.textContent).toContain('groq: quota')
  expect(node.textContent).toContain('30 in / 20 out')
  expect(node.textContent).toContain('500 tokens with unknown actual usage')
})
it('old answers need no fabricated metadata; fallback details do not imply accuracy',async()=>{
  await act(async()=>root.render(<GenerationDetails/>));expect(node.textContent).toBe('')
  await act(async()=>root.render(<GenerationDetails cached value={{provider:'gemini',model:'flash',usage_source:'not_reported',attempts:[{provider:'groq',model:'oss',status:'failed',error:'quota'}]}}/>))
  expect(node.textContent).toContain('Saved topic reused')
  expect(node.textContent).toContain('failed (quota)')
  expect(node.textContent).toContain('does not verify factual correctness')
})
it('distinguishes an unsaved enable checkbox from saved routing',async()=>{
  fixture.providers.groq={key_configured:true,free_account_confirmed:true}
  await render()
  const enable=Array.from(node.querySelectorAll('label')).find(l=>l.textContent?.includes('Enable groq in saved routes'))!.querySelector('input')!
  await act(async()=>enable.click())
  expect(node.textContent).toContain('Routing changes are not saved')
  expect(node.textContent).toContain('Cloud disabled')
  expect(post).not.toHaveBeenCalled()
  await act(async()=>button('Save AI routing changes').click())
  expect(post).toHaveBeenCalledWith('/api/ai/config',expect.objectContaining({providers:expect.objectContaining({groq:expect.objectContaining({enabled:true})})}))
})
it('shows an actionable explanation for disabled cloud and timed-out local fallback',async()=>{
  await act(async()=>root.render(<GenerationDetails value={{provider:null,model:null,attempts:[
    {provider:'gemini',model:'flash',status:'skipped',error:'disabled'},
    {provider:'groq',model:'oss',status:'skipped',error:'disabled'},
    {provider:'ollama',model:'local',status:'failed',error:'timeout'},
  ]}}/>))
  expect(node.querySelector('[role="status"]')?.textContent).toContain('Cloud providers were disabled for this request')
  expect(node.textContent).toContain('local Ollama fallback also timed out')
  expect(node.querySelector('a')?.getAttribute('href')).toBe('/settings')
})
it('requires explicit provider-specific GitHub consent and supports private repositories',async()=>{
  await render()
  const provider=Array.from(node.querySelectorAll('label')).find(l=>l.textContent?.includes("groq may process this project's selected source excerpts"))!.querySelector('input')!
  await act(async()=>provider.click())
  expect(button('Save project permission').disabled).toBe(true)
  const consent=Array.from(node.querySelectorAll('label')).find(l=>l.textContent?.includes('I authorize sending the selected sources'))!.querySelector('input')!
  await act(async()=>consent.click())
  await act(async()=>button('Save project permission').click())
  expect(post).toHaveBeenCalledWith('/api/ai/permission',{providers:['groq'],approved_github_content:true,approved_jira_content:false,approved_slack_content:false})
  expect(node.textContent).toContain('Public and private GitHub repositories are supported')
})

it('requires separate Jira and Slack choices and displays saved source scope',async()=>{
  fixture.permission={providers:['groq','gemini'],source_types:['github'],classification:'github'}
  await render()
  for(const name of ['Jira ticket excerpts','Slack message excerpts']){
    const checkbox=Array.from(node.querySelectorAll('label')).find(l=>l.textContent?.includes(name))!.querySelector('input')!
    expect(checkbox.checked).toBe(false)
    await act(async()=>checkbox.click())
  }
  expect(button('Save project permission').disabled).toBe(true)
  const consent=Array.from(node.querySelectorAll('label')).find(l=>l.textContent?.includes('I authorize sending the selected sources'))!.querySelector('input')!
  await act(async()=>consent.click())
  await act(async()=>button('Save project permission').click())
  expect(post).toHaveBeenCalledWith('/api/ai/permission',{providers:['groq','gemini'],approved_github_content:true,approved_jira_content:true,approved_slack_content:true})
  expect(node.textContent).toContain('Saved source approval: github')
})

it('explains unapproved source scopes and an offline local model',async()=>{
  await act(async()=>root.render(<GenerationDetails value={{provider:null,model:null,attempts:[
    {provider:'groq',model:'oss',status:'skipped',error:'private_source_requires_local'},
    {provider:'ollama',model:'local',status:'failed',error:'connection'},
  ]}}/>))
  expect(node.textContent).toContain('Jira and Slack source permissions')
  expect(node.textContent).toContain('Local folders remain local')
  expect(node.textContent).toContain('ollama serve')
})
