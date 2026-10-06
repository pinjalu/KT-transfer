'use strict';
const $ = id => document.getElementById(id);
let state, answerId, answerScan, nextOffset=0, loadedFiles=false, asking=false, lastScanId;
async function api(path, body) {
  const response = await fetch('/api/'+path, {method:body===undefined?'GET':'POST',
    headers:{'Content-Type':'application/json','X-PKA-Request':'1'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Invalid request. Check your entries.');
  return data;
}
function error(message='') { $('error').textContent=message; $('error').hidden=!message; }
function node(tag, text, className) {const n=document.createElement(tag); n.textContent=text; if(className)n.className=className; return n;}
function clearAnswer() { answerId=null; answerScan=null; $('answer').replaceChildren(node('p','The repository or scan changed. Ask again to use current sources.','muted')); $('feedback').hidden=true; }
function time(s) {return s ? new Date(s).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST':'Not yet';}
async function refresh(initial=false) {
  try {
    state=await api('status');
    if(initial && state.settings){$('repo').value=state.settings.repo;$('branch').value=state.settings.branch;}
    $('saveConfig').disabled=state.demo || state.busy;
    $('repo').disabled=state.demo; $('branch').disabled=state.demo;
    $('modeBanner').hidden=!state.demo && !state.warning;
    $('modeBanner').textContent=state.demo?'EXAMPLE MODE — sample repository and simulated responses. Restart without --demo to use your GitHub repository and Ollama.':state.warning;
    $('credential').textContent=state.demo?'No external connection in example mode.':state.token_configured?'GitHub token configured locally.':'No GitHub token configured — public repositories only.';
    $('model').textContent=state.demo?'Simulated response · no model call':state.model+' · local Ollama';
    const l=state.limits;
    $('limits').textContent=`Up to ${l.max_files} files, ${l.max_file_bytes/1024} KB per file, ${l.max_total_bytes/1024/1024} MB text per scan and ${l.max_entries.toLocaleString()} tree entries. Answers use up to ${l.max_sources} excerpts / ${l.context_chars.toLocaleString()} characters. Refresh is manual.`;
    const s=state.scan;
    $('scanButton').disabled=state.busy || !state.settings;
    $('askButton').disabled=state.busy || !state.ready || asking;
    $('cancelButton').hidden=!s || s.status!=='running';
    if(s){
      $('scanBadge').textContent=s.status;
      $('scanPhase').textContent=s.error || (s.status==='partial'?'Partial scan — some content was omitted.':s.phase)+(s.tree_incomplete?' Repository tree is incomplete.':'');
      $('scanProgress').max=s.total||1; $('scanProgress').value=s.processed||0;
      $('readCount').textContent=s.read; $('skipCount').textContent=s.skipped; $('failCount').textContent=s.failed;
      $('freshness').textContent='Last complete scan: '+time(state.last_successful_scan)+(s.status==='partial'?' · Partial snapshot: '+time(s.finished):'');
      $('commit').textContent=s.commit?'Commit: '+s.commit:'';
      if(lastScanId!==s.id || s.status==='running') {loadedFiles=false;lastScanId=s.id;}
      if($('fileDetails').open && !loadedFiles)await loadFiles();
      if(answerScan && (answerScan!==s.id || !state.ready))clearAnswer();
    } else {
      if(answerScan)clearAnswer();
      $('scanBadge').textContent='Not scanned';$('scanPhase').textContent='Save a repository, then start a scan.';
      for(const id of ['readCount','skipCount','failCount'])$(id).textContent='0';
      $('scanProgress').value=0;$('commit').textContent='';$('freshness').textContent='Last complete scan: Not yet';
    }
  }catch(e){error(e.message);}
}
async function loadFiles(reset=true){
  if(reset){nextOffset=0;$('files').replaceChildren();}
  const result=await api('scan-files?offset='+nextOffset);
  for(const f of result.files)$('files').append(node('li',`${f.state.toUpperCase()} · ${f.path}${f.reason?' — '+f.reason.replaceAll('_',' '):''}`));
  nextOffset=result.next_offset;$('moreFiles').hidden=nextOffset===null;loadedFiles=true;
}
$('configForm').addEventListener('submit',async e=>{e.preventDefault();error();try{await api('config',{repo:$('repo').value.trim(),branch:$('branch').value.trim()});clearAnswer();$('files').replaceChildren();await refresh(true);}catch(e){error(e.message);}});
$('scanButton').addEventListener('click',async()=>{error();try{await api('scan',{});clearAnswer();await refresh();}catch(e){error(e.message);}});
$('cancelButton').addEventListener('click',async()=>{try{const d=await api('scan/cancel',{});$('scanPhase').textContent=d.message;}catch(e){error(e.message);}});
$('fileDetails').addEventListener('toggle',()=>{if($('fileDetails').open && !loadedFiles)loadFiles().catch(e=>error(e.message));});
$('moreFiles').addEventListener('click',()=>loadFiles(false).catch(e=>error(e.message)));
for(const b of document.querySelectorAll('[data-question]')) b.addEventListener('click',()=>{$('question').value=b.dataset.question;$('question').focus();});
$('askForm').addEventListener('submit',async e=>{
  e.preventDefault();error();asking=true;$('askButton').disabled=true;$('feedback').hidden=true;answerId=null;
  $('answer').replaceChildren(node('p','Checking source access, finding relevant excerpts and preparing your answer. Local CPU inference can take a few minutes.','muted'));
  const began=performance.now();const timer=setInterval(()=>{$('model').textContent=`Working locally · ${Math.round((performance.now()-began)/1000)} seconds`;},1000);
  try {
    const r=await api('ask',{question:$('question').value.trim()}); answerId=r.answer_id;answerScan=r.scan_id;
    const out=$('answer');out.replaceChildren();
    if(r.warning)out.append(node('p',r.warning,'banner'));
    if(r.error)out.append(node('p',r.error,'error'));
    for(const s of r.statements)out.append(node('p',s.text+' '+s.source_ids.map(id=>'['+id+']').join(' '),'answerText'));
    if(r.missing_information){out.append(node('h3','Missing or uncertain'));out.append(node('p',r.missing_information));}
    out.append(node('p',`${r.elapsed_seconds}s · Snapshot ${r.commit.slice(0,12)} · Scanned ${time(r.scanned_at)} · Access checked ${time(r.access_checked_at)}`,'answerMeta'));
    out.append(node('h3',`Sources used (${r.sources.length})`));
    for(const s of r.sources){
      const d=node('details','','source');d.append(node('summary',`[${s.source_id}] ${s.path} · lines ${s.start}–${s.end}`));
      if(s.url){const a=node('a','Open this commit on GitHub ↗');a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';d.append(a);}
      if(s.split)d.append(node('p','This excerpt is part of a longer section.','small'));
      d.append(node('pre',s.text));out.append(d);
    }
    out.append(node('p',r.citation_check+' No measured accuracy or confidence percentage is available.','small'));
    $('rating').value='not assessed';$('sufficiency').value='not assessed';$('feedbackStatus').textContent='';$('feedback').hidden=false;
  } catch(e){$('answer').replaceChildren(node('p',e.message,'error'));}
  finally{clearInterval(timer);asking=false;await refresh();}
});
$('feedbackButton').addEventListener('click',async()=>{try{await api('feedback',{answer_id:answerId,rating:$('rating').value,sufficiency:$('sufficiency').value});$('feedbackStatus').textContent='Saved locally.';}catch(e){error(e.message);}});
refresh(true);setInterval(()=>refresh(),2500);
