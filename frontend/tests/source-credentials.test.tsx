import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SourceCredentials } from '../src/components/SourceCredentials'
import { PageActive } from '../src/lib/pageState'
import { get, post } from '../src/lib/api'
vi.mock('../src/components/AuthGate',()=>({useAccount:()=>({user:{username:'new-member',role:'member'}})}))
vi.mock('../src/lib/api',async original=>({...await original<typeof import('../src/lib/api')>(),get:vi.fn(),post:vi.fn()}))
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
let saved:Record<string,boolean>
beforeEach(()=>{
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true); saved={}
  vi.mocked(get).mockReset().mockImplementation(async path=>path==='/api/platforms'?{credentials:saved}:{connected:true,reason:''})
  vi.mocked(post).mockReset().mockImplementation(async(_path,payload)=>{
    for(const [key,value] of Object.entries((payload as {values:Record<string,string>}).values)) saved[key]=!!value
    return {status:{...saved}}
  })
  node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(async()=>{await act(async()=>root.unmount());node.remove();vi.unstubAllGlobals()})
async function render(active=true){await act(async()=>root.render(<PageActive.Provider value={active}><SourceCredentials/></PageActive.Provider>))}
async function pick(name:string){await act(async()=>Array.from(node.querySelectorAll('button')).find(b=>b.textContent?.startsWith(name))!.click())}
async function input(label:string,value:string){await act(async()=>{
  const field=node.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(field,value)
  field.dispatchEvent(new Event('input',{bubbles:true}))
})}
async function submit(){await act(async()=>node.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})))}
it('shows all token providers and account ownership without sharing the owner keys',async()=>{
  await render()
  expect(node.textContent).toContain('Saved only for new-member')
  expect(node.querySelectorAll('[aria-label="Token provider"] button')).toHaveLength(3)
  expect(node.querySelector('input')?.type).toBe('password')
  expect(node.textContent).toContain("the owner's tokens are not shared")
  expect(post).not.toHaveBeenCalled()
})
it('saves Jira details and checks project access, clearing the typed values',async()=>{
  await render();await pick('Jira')
  expect(node.querySelector('[aria-label="Jira site URL"]')?.getAttribute('type')).toBe('url')
  expect(node.querySelector('[aria-label="Atlassian email"]')?.getAttribute('type')).toBe('email')
  await input('Jira site URL','https://example.atlassian.net');await input('Atlassian email','member@example.test');await input('Jira API token','synthetic-jira-key')
  await submit()
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/credentials',{values:{JIRA_SITE:'https://example.atlassian.net',JIRA_EMAIL:'member@example.test',JIRA_API_TOKEN:'synthetic-jira-key'}})
  expect(get).toHaveBeenCalledWith('/api/jira/projects')
  expect(node.textContent).toContain('Jira access checked successfully')
  expect(Array.from(node.querySelectorAll('input')).every(f=>!f.value)).toBe(true)
})
it('checks a Slack user token and does not silently start browser OAuth',async()=>{
  await render();await pick('Slack');await input('Slack user token','synthetic-slack-key');await submit()
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/credentials',{values:{SLACK_USER_TOKEN:'synthetic-slack-key'}})
  expect(get).toHaveBeenCalledWith('/api/slack/channels')
  expect(get).not.toHaveBeenCalledWith('/api/connect/slack_user')
  expect(node.textContent).toContain('Slack access checked successfully')
})
it('does not claim invalid credentials connected and keeps stored values hidden',async()=>{
  saved={JIRA_SITE:true,JIRA_EMAIL:true,JIRA_API_TOKEN:true}
  vi.mocked(get).mockImplementation(async path=>path==='/api/platforms'?{credentials:saved}:{connected:true,reason:'Access denied by Jira.'})
  await render();await pick('Jira');await input('Jira API token','replacement-fixture');await submit()
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/credentials',{values:{JIRA_API_TOKEN:'replacement-fixture'}})
  expect(node.textContent).toContain('access could not be confirmed')
  expect(node.textContent).not.toContain('access checked successfully')
  expect(node.querySelector<HTMLInputElement>('[aria-label="Jira API token"]')!.value).toBe('')
})
it('clears secret drafts when changing provider or navigating away',async()=>{
  await render();await input('GitHub token','do-not-retain');await pick('Slack');await pick('GitHub')
  expect(node.querySelector<HTMLInputElement>('[aria-label="GitHub token"]')!.value).toBe('')
  await input('GitHub token','do-not-retain');await render(false);await render(true)
  expect(node.querySelector<HTMLInputElement>('[aria-label="GitHub token"]')!.value).toBe('')
  expect(post).not.toHaveBeenCalled()
})
it('keeps unedited saved fields and permits explicitly clearing a credential',async()=>{
  saved={JIRA_SITE:true,JIRA_EMAIL:true,JIRA_API_TOKEN:true}
  await render();await pick('Jira');await input('Jira API token','edited');await input('Jira API token','');await submit()
  expect(post).toHaveBeenCalledExactlyOnceWith('/api/credentials',{values:{JIRA_API_TOKEN:''}})
  expect(get).not.toHaveBeenCalledWith('/api/jira/projects')
  expect(node.textContent).toContain('Add the missing fields')
})
