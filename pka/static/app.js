'use strict';

const $ = id => document.getElementById(id);
let state, answerId, answerScan, nextOffset = 0, loadedFiles = false, asking = false, lastScanId, renderedOverview = null, knowledgeRevision;

async function api(path, body) {
  const response = await fetch('/api/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-PKA-Request': '1' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Invalid request. Check your entries.');
  return data;
}

function error(message = '') {
  $('error').textContent = message;
  $('error').hidden = !message;
}

function node(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = text;
  if (className) n.className = className;
  return n;
}

function clearAnswer() {
  answerId = null;
  answerScan = null;
  $('answer').replaceChildren(node('p', 'The repository or scan changed. Ask again to use current sources.', 'muted'));
  $('feedback').hidden = true;
}

function time(s) {
  return s ? new Date(s).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST' : 'Not yet';
}

async function refresh(initial = false) {
  try {
    state = await api('status');
    if (knowledgeRevision !== undefined && knowledgeRevision !== state.knowledge_revision) {
      clearAnswer();
      renderedOverview = null;
      $('overviewBody').replaceChildren();
    }
    knowledgeRevision = state.knowledge_revision;
    $('saveConfig').disabled = state.demo || state.busy;
    $('repo').disabled = state.demo;
    $('branch').disabled = state.demo;
    
    $('modeBanner').hidden = !state.demo && !state.warning;
    $('modeBanner').textContent = state.demo 
      ? '⚡ EXAMPLE MODE — Sample repository and simulated responses active. Restart server without --demo to use GitHub and local Ollama.'
      : state.warning;
      
    $('credential').textContent = state.demo 
      ? 'No external network connections made in example mode.'
      : (state.token_configured ? 'GitHub fine-grained token configured.' : 'No GitHub token configured (public repositories rate-limited).');
      
    $('model').textContent = state.demo ? 'Simulated Response Mode' : state.model + ' (Local Ollama)';
    
    const l = state.limits;
    $('limits').textContent = `Up to ${l.max_files} files, ${l.max_file_bytes / 1024} KB per file, ${l.max_total_bytes / 1024 / 1024} MB text per scan and ${l.max_entries.toLocaleString()} tree entries. Answers use up to ${l.max_sources} excerpts / ${l.context_chars.toLocaleString()} characters.`;
    
    const s = state.scan;
    $('scanButton').disabled = state.busy || !state.settings;
    $('askButton').disabled = state.busy || !state.ready || asking;
    $('cancelButton').hidden = !s || s.status !== 'running';
    
    if (s) {
      $('scanBadge').textContent = s.status;
      $('scanBadge').className = 'badge ' + (s.status === 'complete' ? 'badge-success' : s.status === 'running' ? 'badge-running' : 'badge-warning');
      $('scanPhase').textContent = s.error || (s.status === 'partial' ? 'Partial scan — some content omitted.' : s.phase) + (s.tree_incomplete ? ' Repository tree incomplete.' : '');
      $('scanProgress').max = s.total || 1;
      $('scanProgress').value = s.processed || 0;
      $('readCount').textContent = s.read;
      $('skipCount').textContent = s.skipped;
      $('failCount').textContent = s.failed;
      $('freshness').textContent = 'Last complete scan: ' + time(state.last_successful_scan) + (s.status === 'partial' ? ' · Partial: ' + time(s.finished) : '');
      $('commit').textContent = s.commit ? 'Commit ' + s.commit.slice(0, 12) : '';
      if (lastScanId !== s.id || s.status === 'running') { loadedFiles = false; lastScanId = s.id; }
      if ($('fileDetails').open && !loadedFiles) await loadFiles();
      if (answerScan && (answerScan !== s.id || !state.ready)) clearAnswer();
    } else {
      if (answerScan) clearAnswer();
      $('scanBadge').textContent = 'Not scanned';
      $('scanBadge').className = 'badge';
      $('scanPhase').textContent = 'Save a repository, then start a scan.';
      for (const id of ['readCount', 'skipCount', 'failCount']) $(id).textContent = '0';
      $('scanProgress').value = 0;
      $('commit').textContent = '';
      $('freshness').textContent = 'Last complete scan: Not yet';
    }
  } catch (e) {
    error(e.message);
  }
}

async function loadFiles(reset = true) {
  if (reset) { nextOffset = 0; $('files').replaceChildren(); }
  const result = await api('scan-files?offset=' + nextOffset);
  for (const f of result.files) {
    $('files').append(node('li', `${f.state.toUpperCase()} · ${f.path}${f.reason ? ' — ' + f.reason.replaceAll('_', ' ') : ''}`));
  }
  nextOffset = result.next_offset;
  $('moreFiles').hidden = nextOffset === null;
  loadedFiles = true;
}

function selectedPlatforms() {
  return Array.from(document.querySelectorAll('#platforms input[type=checkbox]:checked')).map(b => b.value);
}

// The flow is three steps: choose platforms, connect one, then read and ask.
// WIZARD_PLATFORMS is what step one offers. The Slack bot placeholder is left out because
// reading is not built for it, so offering it would promise something that does not exist.
const WIZARD_PLATFORMS = ['github', 'slack_user', 'jira'];
let activePlatform = '';
let platformRows = [];

function showView(name) {
  for (const id of ['viewSelect', 'viewConnect', 'viewWorkspace']) {
    $(id).hidden = id !== name;
  }
  window.scrollTo(0, 0);
}

function openConnect(key) {
  activePlatform = key;
  const row = platformRows.find(p => p.key === key);
  $('connectTitle').textContent = 'Connect ' + (row ? row.label : key);
  $('connectReads').textContent = row ? row.reads : '';
  // Each platform only shows the scope picker that belongs to it.
  $('jiraBlock').hidden = key !== 'jira';
  $('slackBlock').hidden = key !== 'slack_user';
  for (const card of document.querySelectorAll('.config-card, .scan-card')) {
    card.hidden = key !== 'github';
  }
  showView('viewConnect');
  refreshPlatforms();
  if (key === 'jira') refreshJira();
  if (key === 'slack_user') refreshSlack();
}

function renderChoices() {
  const box = $('platformChoices');
  const wanted = platformRows.filter(p => WIZARD_PLATFORMS.includes(p.key));
  const signature = JSON.stringify(wanted.map(p => [p.key, p.selected, p.ready, p.pending]));
  if (box.dataset.signature === signature) return;
  box.dataset.signature = signature;
  box.replaceChildren();
  for (const p of wanted) {
    const row = node('div', undefined, 'choice-row' + (p.selected ? ' choice-on' : ''));
    const head = document.createElement('label');
    head.className = 'choice-head';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = p.key;
    cb.checked = p.selected;
    cb.addEventListener('change', saveChoice);
    const name = node('span', undefined, 'choice-name');
    name.append(node('span', p.label, 'choice-title'));
    name.append(node('span', p.reads, 'choice-reads'));
    head.append(cb, name);
    row.append(head);
    if (p.selected) {
      const status = document.createElement('button');
      status.type = 'button';
      status.className = 'btn ' + (p.ready ? 'btn-secondary' : 'btn-primary') + ' choice-status';
      status.append(node('span', p.ready ? 'Connected' : 'Connection pending'));
      status.addEventListener('click', () => openConnect(p.key));
      row.append(status);
      if (!p.ready) row.append(node('p', p.pending, 'small choice-why'));
      else if (p.scope) row.append(node('p', 'Reading ' + p.scope, 'small choice-scope'));
    }
    box.append(row);
  }
  const chosen = wanted.filter(p => p.selected);
  const waiting = chosen.filter(p => !p.ready);
  $('toWorkspace').disabled = !chosen.length || waiting.length > 0;
  $('selectNote').textContent = !chosen.length
    ? 'Choose at least one platform to continue.'
    : waiting.length
      ? 'Still to connect: ' + waiting.map(p => p.label).join(', ') + '.'
      : 'All chosen platforms are connected. Continue to your project.';
}

async function saveChoice() {
  error();
  const keys = Array.from(document.querySelectorAll('#platformChoices input:checked')).map(b => b.value);
  try {
    // The repository scan is what the index is built from, so GitHub is always included.
    await api('config', {
      repo: $('repo').value.trim() || (state && state.settings ? state.settings.repo : ''),
      branch: $('branch').value.trim() || (state && state.settings ? state.settings.branch : 'main'),
      platforms: keys
    });
  } catch (e) {
    if (!/OWNER\/REPOSITORY|repository address/i.test(e.message)) { error(e.message); return; }
    // No repository saved yet, so remember the choice once one is entered.
  }
  $('platformChoices').dataset.signature = '';
  await refreshPlatforms();
}

$('backToSelect').addEventListener('click', () => showView('viewSelect'));
$('backToSelectTwo').addEventListener('click', () => showView('viewSelect'));
$('doneConnecting').addEventListener('click', () => { $('platformChoices').dataset.signature = ''; refreshPlatforms().then(() => showView('viewSelect')); });
$('toWorkspace').addEventListener('click', () => { showView('viewWorkspace'); refreshOverview(); });

async function refreshJira() {
  try {
    if (activePlatform !== 'jira') { $('jiraBlock').hidden = true; return; }
    const r = await api('jira/projects');
    $('jiraBlock').hidden = !r.connected;
    if (!r.connected) return;
    const reading = state && state.jira_reading;
    $('readJira').disabled = reading || !r.projects.length;
    if (reading && state.jira_progress) {
      $('jiraState').textContent = state.jira_progress.phase;
      return;
    }
    const parts = [];
    if (r.reason) parts.push(r.reason);
    else parts.push(`${r.projects.length} projects visible to your account`);
    if (r.blocks) parts.push(`${r.blocks} issues in the index`);
    if (r.read_at) parts.push('last read ' + time(r.read_at));
    $('jiraState').textContent = parts.join(' · ');
    const box = $('jiraProjects');
    const signature = JSON.stringify([r.projects.map(p => p.key), r.chosen]);
    if (box.dataset.signature === signature) return;
    box.dataset.signature = signature;
    box.replaceChildren();
    for (const p of r.projects) {
      const row = document.createElement('label');
      row.className = 'slack-channel';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'jiraProject';
      radio.value = p.key;
      radio.checked = p.key === r.chosen;
      radio.addEventListener('change', async () => {
        try { await api('jira/project', { project: p.key }); } catch (e) { error(e.message); }
      });
      row.append(radio, node('span', p.key + '  ' + p.name, 'slack-name'));
      box.append(row);
    }
  } catch (e) { }
}

async function refreshSlack() {
  try {
    if (activePlatform !== 'slack_user') { $('slackBlock').hidden = true; return; }
    const r = await api('slack/channels');
    const block = $('slackBlock');
    block.hidden = !r.connected;
    if (!r.connected) return;
    if (r.workspace && !$('slackWorkspace').value) $('slackWorkspace').value = r.workspace;
    const reading = state && state.slack_reading;
    const p = state && state.slack_progress;
    $('readSlack').disabled = reading || !r.channels.length;
    $('saveChannels').disabled = reading;
    if (reading && p) {
      $('slackState').textContent = `${p.phase} (${p.done} of ${p.total} done)`;
      return;
    }
    const parts = [];
    if (r.reason) parts.push(r.reason);
    else parts.push(`${r.channels.length} channels visible to your account`);
    if (r.blocks) parts.push(`${r.blocks} message blocks in the index`);
    if (r.read_at) parts.push('last read ' + time(r.read_at));
    $('slackState').textContent = parts.join(' · ');
    const box = $('slackChannels');
    if (box.dataset.signature === JSON.stringify(r.channels.map(c => [c.id, c.chosen]))) return;
    box.dataset.signature = JSON.stringify(r.channels.map(c => [c.id, c.chosen]));
    box.replaceChildren();
    for (const c of r.channels) {
      const row = document.createElement('label');
      row.className = 'slack-channel';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = c.id;
      cb.dataset.name = c.name;
      cb.checked = c.chosen;
      cb.disabled = !c.member;
      row.append(cb, node('span', (c.private ? 'private  ' : '') + '#' + c.name, 'slack-name'));
      if (!c.member) row.append(node('span', 'not a member', 'platform-status'));
      box.append(row);
    }
  } catch (e) { }
}

function chosenChannels() {
  return Array.from(document.querySelectorAll('#slackChannels input:checked'))
    .map(b => ({ id: b.value, name: b.dataset.name }));
}

async function refreshPlatforms() {
  try {
    const r = await api('platforms');
    platformRows = r.platforms;
    renderChoices();
    const box = $('platforms');
    // Rebuilding this on every poll closed any guidance the reader had opened, so only
    // rebuild when something about this platform actually changed.
    const shown = r.platforms.filter(x => x.key === activePlatform);
    const signature = JSON.stringify(shown.map(x => [x.key, x.ready, x.pending, x.connection, x.redirect_uri]))
      + JSON.stringify(r.credentials);
    if (box.dataset.signature === signature) return;
    box.dataset.signature = signature;
    box.replaceChildren();
    for (const p of shown) {
      const row = node('div', undefined, 'platform-row');
      const head = document.createElement('label');
      head.className = 'platform-head';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = p.key;
      cb.checked = p.selected;
      cb.disabled = state && state.demo;
      cb.hidden = true;
      // One status, not two. Saying "credentials found" beside "not connected yet" reads as a
      // contradiction, when it only means the credentials are in and the scope is not chosen.
      head.append(node('span', p.label, 'platform-name'),
                  node('span', p.ready ? 'Connected' : 'Not connected yet',
                       'platform-status ' + (p.ready ? 'status-ok' : 'status-wait')));
      row.append(head);
      if (!p.ready && p.pending) row.append(node('p', 'Next step: ' + p.pending, 'small pending-step'));
      const d = node('details', undefined, 'help-details platform-setup');
      d.append(node('summary', 'How to connect ' + p.label));
      const inner = node('div', undefined, 'details-content');
      inner.append(node('p', 'Permission: ' + p.permission, 'small'));
      const ol = document.createElement('ol');
      for (const step of p.setup) ol.append(node('li', step));
      inner.append(ol);
      const form = document.createElement('form');
      form.className = 'credential-form';
      form.dataset.platform = p.key;
      for (const name of p.credentials) {
        const field = node('div', undefined, 'input-field');
        const lab = document.createElement('label');
        lab.htmlFor = 'cred-' + name;
        lab.append(node('span', name, 'cred-name'));
        // Confirm each value individually. The overall status reports the whole connection, so
        // without this there was no sign that a saved credential had been accepted.
        const held = !!(r.credentials && r.credentials[name]);
        lab.append(node('span', held ? 'saved' : 'not set', 'cred-state ' + (held ? 'cred-on' : 'cred-off')));
        const box = document.createElement('input');
        box.type = 'password';
        box.id = 'cred-' + name;
        box.name = name;
        box.maxLength = 500;
        box.autocomplete = 'off';
        const hint = (p.credential_hints || {})[name];
        box.placeholder = (r.credentials && r.credentials[name]) ? 'Saved. Type to replace.' : (hint || 'Not set');
        field.append(lab, box);
        form.append(field);
      }
      if (p.oauth && p.redirect_uri) {
        inner.append(node('p', 'Redirect URL to register in your ' + p.label + ' app:', 'small'));
        const uri = node('p', p.redirect_uri, 'small mono redirect-uri');
        inner.append(uri);
      }
      if (p.oauth) {
        const connect = document.createElement('button');
        connect.type = 'button';
        connect.className = 'btn btn-primary full-width connect-btn';
        connect.dataset.platform = p.key;
        connect.disabled = !p.credentials_present;
        connect.append(node('span', p.connected ? 'Reconnect ' + p.label : 'Connect ' + p.label));
        form.append(connect);
        form.append(node('p', p.credentials_present
          ? 'Opens ' + p.label + ' so you can approve the reading permissions. The token is stored for you.'
          : 'Add the client id and secret above, then this button becomes available.', 'small muted'));
      }
      const save = document.createElement('button');
      save.type = 'submit';
      save.className = 'btn btn-secondary full-width';
      save.append(node('span', 'Save ' + p.label + ' credentials'));
      form.append(save);
      form.append(node('p', 'Stored in your local .env file, which is never committed. Values are never shown again, never logged and never sent to the model.', 'small muted'));
      inner.append(form);
      d.append(inner);
      row.append(d);
      box.append(row);
    }
    for (const form of document.querySelectorAll('.credential-form')) {
      form.addEventListener('submit', async e => {
        e.preventDefault();
        error();
        const values = {};
        for (const box of form.querySelectorAll('input')) {
          if (box.value) values[box.name] = box.value;
        }
        if (!Object.keys(values).length) { error('Type a value before saving.'); return; }
        try {
          await api('credentials', { values });
          for (const box of form.querySelectorAll('input')) box.value = '';
          await refreshPlatforms();
          await refresh();
        } catch (err) { error(err.message); }
      });
    }
    for (const button of document.querySelectorAll('.connect-btn')) {
      button.addEventListener('click', async () => {
        error();
        try {
          const r = await api('connect/' + button.dataset.platform);
          window.location.href = r.url;
        } catch (err) { error(err.message); }
      });
    }
    $('platformNote').textContent = r.note;
  } catch (e) { }
}

$('readJira').addEventListener('click', async () => {
  error();
  try {
    await api('jira/read', {});
    $('readJira').disabled = true;
    await refreshJira();
  } catch (e) { error(e.message); }
});

$('saveChannels').addEventListener('click', async () => {
  error();
  try {
    await api('slack/channels', { workspace: $('slackWorkspace').value.trim(), channels: chosenChannels() });
    $('slackChannels').dataset.signature = '';
    await refreshSlack();
  } catch (e) { error(e.message); }
});

$('readSlack').addEventListener('click', async () => {
  error();
  try {
    await api('slack/channels', { workspace: $('slackWorkspace').value.trim(), channels: chosenChannels() });
    await api('slack/read', {});
    $('readSlack').disabled = true;
    await refreshSlack();
  } catch (e) { error(e.message); }
});

$('configForm').addEventListener('submit', async e => {
  e.preventDefault();
  error();
  try {
    await api('config', { repo: $('repo').value.trim(), branch: $('branch').value.trim(), platforms: selectedPlatforms() });
    await refreshPlatforms();
    clearAnswer();
    $('files').replaceChildren();
    await refresh(true);
  } catch (e) {
    error(e.message);
  }
});

$('scanButton').addEventListener('click', async () => {
  error();
  try {
    await api('scan', {});
    clearAnswer();
    await refresh();
  } catch (e) {
    error(e.message);
  }
});

$('cancelButton').addEventListener('click', async () => {
  try {
    const d = await api('scan/cancel', {});
    $('scanPhase').textContent = d.message;
  } catch (e) {
    error(e.message);
  }
});

$('fileDetails').addEventListener('toggle', () => {
  if ($('fileDetails').open && !loadedFiles) loadFiles().catch(e => error(e.message));
});

$('moreFiles').addEventListener('click', () => loadFiles(false).catch(e => error(e.message)));

for (const b of document.querySelectorAll('[data-question]')) {
  b.addEventListener('click', () => {
    $('question').value = b.dataset.question;
    $('question').focus();
  });
}

// A citation has two jobs: show the excerpt that was actually sent to the model, and open the
// real file at the real lines. The pill does the first, the arrow beside it does the second.
// Both are needed. The excerpt proves what the answer was built from; the link lets a reader
// read around it, which is the only way to tell whether the excerpt was the whole story.
function citeInto(parent, sid, sources, prefix) {
  const found = (sources || []).find(s => s.source_id === sid);
  const where = found ? `${found.path} lines ${found.start} to ${found.end}` : sid;
  const pill = node('span', `[${sid}]`, 'citation-pill');
  pill.title = 'Show the excerpt: ' + where;
  pill.addEventListener('click', () => {
    const el = document.getElementById(prefix + sid);
    if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  parent.append(pill);
  if (found && found.url) {
    const link = node('a', '↗', 'citation-link');
    link.href = found.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.title = 'Open ' + where;
    parent.append(link);
  }
  parent.append(document.createTextNode(' '));
}

function citationsInto(parent, statement, sources, prefix) {
  if (shows().citations) {
    for (const sid of statement.source_ids) citeInto(parent, sid, sources, prefix);
  }
  if (statement.about_this_project === false) {
    const flag = node('span', 'not about this project', 'support-flag generic-flag');
    flag.title = 'This sentence names nothing from this project, so it would be equally true ' +
      'of any other one. Treat it as filler.';
    parent.append(flag);
  }
  if (statement.support === 'check this') {
    const flag = node('span', 'check this', 'support-flag');
    flag.title = 'Little of this sentence appears in the excerpt it cites. Open the excerpt before relying on it.';
    parent.append(flag);
  }
}

// One excerpt, with its own link out. Used by the answer, by every overview section and by
// anything else that has to show what a citation points at.
function excerpt(s, prefix) {
  const d = node('details', '', 'source');
  d.id = prefix + s.source_id;
  d.append(node('summary', `[${s.source_id}] ${s.path} · lines ${s.start}–${s.end}`));
  if (s.url) {
    const a = node('a', 'Open this file at these lines ↗');
    a.href = s.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    d.append(a);
  }
  if (s.split) d.append(node('p', 'This excerpt is part of a longer block of code.', 'small text-muted'));
  d.append(node('pre', s.text));
  return d;
}

// What the search actually did with the words that were typed. Without this a thin answer
// looks like the project has no answer, when the real reason is usually that one word in the
// question does not occur in the indexed content under that name.
function searchNote(search, checks) {
  if (!search) return null;
  const box = node('div', '', 'search-note');
  const used = (search.terms || []).join(', ');
  if (used) box.append(node('p', 'Searched the project for: ' + used, 'small'));
  const corrections = Object.entries(search.corrections || {});
  if (corrections.length) {
    box.append(node('p', 'Read as words this project uses: ' +
      corrections.map(([from, to]) => `${from} → ${to.join(', ')}`).join('; '), 'small'));
  }
  if ((search.unknown || []).length) {
    box.append(node('p', 'These words were not found in the indexed content: ' +
      search.unknown.join(', ') + '. Unread or skipped content may still cover them. ' +
      'Try another term or check the import coverage.', 'small'));
  }
  if (checks && (checks.dropped_repeats || checks.narrowed_citations)) {
    const parts = [];
    if (checks.dropped_repeats) parts.push(`${checks.dropped_repeats} repeated statement${checks.dropped_repeats > 1 ? 's' : ''} removed`);
    if (checks.narrowed_citations) parts.push(`${checks.narrowed_citations} statement${checks.narrowed_citations > 1 ? 's' : ''} cited every excerpt at once, narrowed to the ones that carry the wording`);
    box.append(node('p', 'Checked before showing: ' + parts.join('; ') + '.', 'small'));
  }
  return box.childElementCount ? box : null;
}

function renderAnswer(r) {
  answerId = r.answer_id;
  answerScan = r.scan_id;
  const out = $('answer');
  out.replaceChildren();

  if (r.warning) out.append(node('p', r.warning, 'banner'));
  if (r.error) out.append(node('p', r.error, 'error'));

  if (r.statements && r.statements.length > 0) {
    const explanationBox = node('div', '', 'explanation-box');

    const firstStatement = r.statements[0];
    const coreAnswerCard = node('div', '', 'core-answer-card');
    const coreHeader = node('div', '', 'core-answer-header');
    coreHeader.append(node('span', '💡 Core Explanation (For New Developers)', 'core-title'));

    const copyBtn = node('button', '📋 Copy Answer', 'btn btn-secondary btn-sm copy-btn');
    copyBtn.type = 'button';
    copyBtn.addEventListener('click', () => {
      const cited = s => s.source_ids.map(id => {
        const found = r.sources.find(x => x.source_id === id);
        return found ? `${found.path}:${found.start}-${found.end}` : id;
      }).join(', ');
      const fullText = r.statements.map((s, i) => `${i + 1}. ${s.text}\n   Source: ${cited(s)}`).join('\n\n');
      navigator.clipboard.writeText(fullText);
      copyBtn.textContent = '✅ Copied!';
      setTimeout(() => { copyBtn.textContent = '📋 Copy Answer'; }, 2000);
    });
    coreHeader.append(copyBtn);
    coreAnswerCard.append(coreHeader);

    const firstP = node('p', '', 'answerText main-answer-text');
    firstP.append(document.createTextNode(firstStatement.text + ' '));
    citationsInto(firstP, firstStatement, r.sources, 'source-');
    coreAnswerCard.append(firstP);
    explanationBox.append(coreAnswerCard);

    if (r.statements.length > 1) {
      const stepsContainer = node('div', '', 'steps-container');
      stepsContainer.append(node('h4', 'Key Steps & Details:', 'steps-title'));
      for (let i = 1; i < r.statements.length; i++) {
        const st = r.statements[i];
        const stepRow = node('div', '', 'step-item');
        const stepContent = node('div', '', 'step-content');
        const stepP = node('p', '', 'step-text');
        stepP.append(document.createTextNode(st.text + ' '));
        citationsInto(stepP, st, r.sources, 'source-');
        stepContent.append(stepP);
        stepRow.append(node('span', `${i + 1}`, 'step-number'));
        stepRow.append(stepContent);
        stepsContainer.append(stepRow);
      }
      explanationBox.append(stepsContainer);
    }
    out.append(explanationBox);
  }

  if (r.missing_information) {
    const missingBox = node('div', '', 'banner warning-callout');
    missingBox.append(node('strong', '⚠️ What is missing or uncertain in these files: '));
    missingBox.append(document.createTextNode(r.missing_information));
    out.append(missingBox);
  }

  const note = searchNote(r.search, r.checks);
  if (note) out.append(note);

  out.append(node('p', `⏱️ Answered in ${r.elapsed_seconds}s · Snapshot ${r.commit.slice(0, 12)} · Scanned ${time(r.scanned_at)}`, 'answerMeta'));
  out.append(node('h4', `Excerpts this answer was built from (${r.sources.length})`, 'mt-2'));
  for (const s of r.sources) out.append(excerpt(s, 'source-'));
  out.append(node('p', r.citation_check, 'small text-muted mt-2'));

  $('rating').value = r.rating || 'not assessed';
  $('sufficiency').value = r.sufficiency || 'not assessed';
  $('feedbackStatus').textContent = '';
  $('feedback').hidden = false;
  out.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

const FACT_ICONS = {
  shape: '📦', documents: '📘', dependencies: '🧩', commands: '⌨️',
  routes: '🔗', stores: '🗄️', environment: '⚙️', services: '🌐',
  delivery: '🚢', gaps: '🚧'
};

// Who the page is talking to. The same evidence underneath, three depths of it: somebody on
// their first morning does not want a list of import lines, and somebody debugging at 2am does
// not want to be told what a dependency is.
const MODES = [
  { key: 'beginner', label: 'New here',
    blurb: 'Plain words and pictures. The detail is hidden until you want it.' },
  { key: 'developer', label: 'Developer',
    blurb: 'Adds the files, the import lines, the excerpts and the citations.' },
  { key: 'architect', label: 'Architect',
    blurb: 'The shape of the system: layers, what uses what, outside services, storage.' }
];
// What each mode is for. A key absent from a mode is not rendered in that mode.
const MODE_SHOWS = {
  beginner: { prose: true, diagrams: true, facts: ['shape', 'documents', 'commands', 'routes',
              'services', 'stores', 'environment', 'delivery', 'gaps'],
              roles: true, excerpts: false, citations: false, readingOrder: true,
              statements: 3, roleDetail: false },
  developer: { prose: true, diagrams: true, facts: null, roles: true, excerpts: true,
               citations: true, readingOrder: true, statements: 4, roleDetail: true },
  architect: { prose: false, diagrams: true, facts: ['shape', 'routes', 'services', 'stores',
               'environment', 'delivery', 'dependencies', 'gaps'],
               roles: true, excerpts: false, citations: false, readingOrder: false,
               statements: 2, roleDetail: true }
};
let overviewRole = 'beginner';

function shows() {
  return MODE_SHOWS[overviewRole] || MODE_SHOWS.developer;
}
const TOPIC_ICONS = {
  purpose: '🎯', technologies: '🛠️', architecture: '🧱', setup: '🚀',
  flows: '⚡', interfaces: '🔌', data: '🗄️', testing: '🧪', decisions: '💬'
};
const FACTS_SHOWN = 8;

// A fact group is a list of things read out of the files, each one openable at the line it was
// read from. Long groups are folded after the first few, because a reader meeting a project
// wants to see that it has thirty-five dependencies before reading all thirty-five.
function factGroup(group) {
  const card = node('div', '', 'overview-section-card facts-card');
  const header = node('div', '', 'overview-section-header');
  header.append(node('h4', `${FACT_ICONS[group.key] || '📋'} ${group.title}`, 'overview-section-title'));
  header.append(node('span', `${group.items.length}${group.truncated ? '+' : ''}`, 'badge'));
  card.append(header);
  card.append(node('p', group.plain, 'small text-muted'));

  const list = node('ul', '', 'fact-list');
  const overflow = node('ul', '', 'fact-list');
  group.items.forEach((item, position) => {
    const li = document.createElement('li');
    if (item.url) {
      const a = node('a', item.text, 'fact-name');
      a.href = item.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = item.line ? `Open ${item.path} at line ${item.line}` : `Open ${item.path}`;
      li.append(a);
    } else {
      li.append(node('span', item.text, 'fact-name'));
    }
    if (item.detail) li.append(node('span', ' — ' + item.detail, 'fact-detail'));
    (position < FACTS_SHOWN ? list : overflow).append(li);
  });
  card.append(list);
  if (overflow.childElementCount) {
    const more = node('details', '', 'help-details');
    more.append(node('summary', `Show the remaining ${overflow.childElementCount}`));
    const holder = node('div', '', 'details-content');
    holder.append(overflow);
    more.append(holder);
    card.append(more);
  }
  if (group.truncated) {
    card.append(node('p', `${group.truncated} more were found and not listed here.`, 'small text-muted'));
  }
  return card;
}

const SVG = 'http://www.w3.org/2000/svg';
const BOX_W = 168, BOX_H = 48, GAP_X = 56, GAP_Y = 14, PAD = 14;
const LABEL_MAX = 24;
const STATEMENTS_SHOWN = 3;

let stepKey = '';
let overviewMode = 'walk';

function shape(name, attrs) {
  const n = document.createElementNS(SVG, name);
  for (const key in attrs) n.setAttribute(key, attrs[key]);
  return n;
}

function clipped(text) {
  return text.length > LABEL_MAX ? text.slice(0, LABEL_MAX - 1) + '…' : text;
}

// A box is a link when the thing it stands for is a real file, and plain text when it stands
// for something that has no single line, such as "a browser" or a collapsed folder.
function diagramBox(item, x, y) {
  const group = shape('g', { class: 'dg-node dg-' + item.kind });
  const body = item.url ? shape('a', { href: item.url, target: '_blank', rel: 'noopener noreferrer' }) : group;
  const rect = shape('rect', { x, y, width: BOX_W, height: BOX_H, rx: 7, class: 'dg-box' });
  body.append(rect);
  const label = shape('text', { x: x + BOX_W / 2, y: y + (item.sublabel ? 20 : 28), class: 'dg-label' });
  label.textContent = clipped(item.label);
  body.append(label);
  if (item.sublabel) {
    const sub = shape('text', { x: x + BOX_W / 2, y: y + 34, class: 'dg-sub' });
    sub.textContent = clipped(item.sublabel);
    body.append(sub);
  }
  const hover = shape('title');
  hover.textContent = [item.label, item.sublabel, item.path && (item.path + (item.line ? ':' + item.line : ''))]
    .filter(Boolean).join(' · ');
  body.append(hover);
  if (body !== group) group.append(body);
  return group;
}

function diagramGraph(d) {
  const columns = Math.max(...d.nodes.map(n => n.column)) + 1;
  const tall = [];
  for (let c = 0; c < columns; c++) tall.push(d.nodes.filter(n => n.column === c).length);
  const rows = Math.max(...tall, 1);
  const loops = d.edges.some(e => e.back);
  const width = PAD * 2 + columns * BOX_W + (columns - 1) * GAP_X;
  const height = PAD * 2 + rows * (BOX_H + GAP_Y) - GAP_Y + (loops ? 46 : 0);

  const where = {};
  for (const item of d.nodes) {
    // Each column is centred against the tallest one, so a chain of single boxes reads as a
    // straight line rather than hugging the top edge.
    const offset = (rows - tall[item.column]) * (BOX_H + GAP_Y) / 2;
    where[item.id] = {
      x: PAD + item.column * (BOX_W + GAP_X),
      y: PAD + offset + item.row * (BOX_H + GAP_Y)
    };
  }

  const svg = shape('svg', {
    viewBox: `0 0 ${width} ${height}`, width, height,
    class: 'dg', role: 'img', 'aria-label': d.title
  });
  const marker = shape('marker', {
    id: 'dg-arrow-' + d.key, viewBox: '0 0 8 8', refX: 7, refY: 4,
    markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse'
  });
  marker.append(shape('path', { d: 'M 0 0 L 8 4 L 0 8 z', class: 'dg-head' }));
  const defs = shape('defs');
  defs.append(marker);
  svg.append(defs);

  for (const edge of d.edges) {
    const from = where[edge.from], to = where[edge.to];
    if (!from || !to) continue;
    let path, cls = 'dg-edge';
    if (edge.back) {
      // Two files importing each other cannot sit left of one another, so this arrow travels
      // under every box instead of back through them. Dashed, because it is the odd one out.
      const x1 = from.x + BOX_W / 2, x2 = to.x + BOX_W / 2;
      const floor = height - PAD - 8;
      path = `M ${x1} ${from.y + BOX_H} C ${x1} ${floor}, ${x2} ${floor}, ${x2} ${to.y + BOX_H}`;
      cls += ' dg-edge-back';
    } else {
      const x1 = from.x + BOX_W, y1 = from.y + BOX_H / 2;
      const x2 = to.x, y2 = to.y + BOX_H / 2;
      const bend = Math.max(22, (x2 - x1) / 2);
      path = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
    }
    const line = shape('path', {
      d: path, class: cls, 'marker-end': `url(#dg-arrow-${d.key})`
    });
    const why = shape('title');
    why.textContent = edge.back
      ? 'these two files import each other' + (edge.line ? ', at line ' + edge.line : '')
      : edge.count > 1
      ? `${edge.count} imports cross here`
      : edge.line ? 'declared at line ' + edge.line : 'a request arrives here';
    line.append(why);
    svg.append(line);
    if (edge.count > 1 && !edge.back) {
      const count = shape('text', {
        x: (from.x + BOX_W + to.x) / 2,
        y: (from.y + to.y) / 2 + BOX_H / 2 - 5, class: 'dg-count'
      });
      count.textContent = edge.count;
      svg.append(count);
    }
  }
  for (const item of d.nodes) svg.append(diagramBox(item, where[item.id].x, where[item.id].y));

  const holder = node('div', '', 'dg-holder');
  holder.append(svg);
  return holder;
}

// Bands have no arrows, so they are plain elements rather than drawing. That keeps the text
// selectable and the layout able to wrap on a narrow screen, which a fixed drawing cannot.
function diagramBands(d) {
  const wrap = node('div', '', 'dg-bands');
  for (const band of d.bands) {
    const row = node('div', '', 'dg-band');
    const head = node('div', '', 'dg-band-head');
    head.append(node('span', String(band.column + 1), 'dg-band-number'));
    const names = node('div', '', 'dg-band-names');
    names.append(node('h5', band.title, 'dg-band-title'));
    names.append(node('p', band.plain, 'dg-band-plain'));
    head.append(names);
    head.append(node('span', `${band.count} ${band.count === 1 ? 'file' : 'files'}`, 'badge'));
    row.append(head);

    const boxes = node('div', '', 'dg-band-boxes');
    for (const item of d.nodes.filter(n => n.column === band.column)) {
      if (item.kind === 'more') {
        boxes.append(node('span', item.label, 'dg-chip dg-chip-more'));
        continue;
      }
      let chip;
      if (item.url) {
        chip = node('a', item.label, 'dg-chip');
        chip.href = item.url;
        chip.target = '_blank';
        chip.rel = 'noopener noreferrer';
      } else {
        chip = node('span', item.label, 'dg-chip');
      }
      chip.title = item.path || item.label;
      if (item.sublabel) chip.append(node('span', ' ' + item.sublabel, 'dg-chip-where'));
      boxes.append(chip);
    }
    row.append(boxes);
    wrap.append(row);
  }
  return wrap;
}

function diagramCard(d) {
  const card = node('div', '', 'overview-section-card diagram-card');
  const header = node('div', '', 'overview-section-header');
  header.append(node('h4', '🗺️ ' + d.title, 'overview-section-title'));
  header.append(node('span', 'drawn from the files', 'badge'));
  card.append(header);
  card.append(node('p', d.plain, 'small text-muted'));
  card.append(d.kind === 'bands' ? diagramBands(d) : diagramGraph(d));
  if (d.note) card.append(node('p', d.note, 'small text-muted dg-note'));
  return card;
}

// Prose inside a step is kept to the first few statements. The point of a walkthrough is that
// a person reads it, and nobody reads eight paragraphs per step; the rest stay one click away.
function linkTo(where, label, title) {
  if (!where.url) {
    const plain = node('span', label, 'fact-name');
    plain.title = title || '';
    return plain;
  }
  const a = node('a', label, 'fact-name');
  a.href = where.url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.title = title || '';
  return a;
}

// One card per important file, in the shape a new developer actually asks about it: what is
// this, who uses it, what does it use. Who-uses-what comes from the import lines, so it is
// exact; a wrong answer there sends somebody editing the wrong file.
function roleCard(group) {
  const card = node('div', '', 'overview-section-card facts-card');
  const header = node('div', '', 'overview-section-header');
  header.append(node('h4', '\u{1F4C4} ' + group.title, 'overview-section-title'));
  header.append(node('span', group.cards.length + ' files', 'badge'));
  card.append(header);
  card.append(node('p', group.plain, 'small text-muted'));

  for (const file of group.cards) {
    const row = node('div', '', 'role-card');
    const top = node('div', '', 'role-top');
    top.append(linkTo(file, file.name, file.path));
    if (file.tested) top.append(node('span', 'has tests', 'badge badge-success'));
    row.append(top);
    row.append(node('p', file.purpose || 'This file does not say what it is for.',
      'role-purpose' + (file.purpose ? '' : ' role-purpose-none')));
    for (const held of file.holds) row.append(node('p', held, 'role-holds'));

    if (shows().roleDetail) {
      const wires = [
        ['Used by', file.used_by, 'nothing in this project imports it'],
        ['Uses', file.calls, 'nothing else in this project']
      ];
      for (const [label, list, empty] of wires) {
        const line = node('p', '', 'role-wires');
        line.append(node('span', label + ': ', 'role-wire-label'));
        if (!list.length) {
          line.append(node('span', empty, 'fact-detail'));
        } else {
          list.forEach((other, position) => {
            const where = label === 'Used by'
              ? other.path + ' line ' + other.line
              : 'imported at line ' + other.line;
            line.append(linkTo(other, other.name, where));
            if (position < list.length - 1) line.append(document.createTextNode(', '));
          });
        }
        row.append(line);
      }
    }
    card.append(row);
  }
  if (group.truncated) {
    card.append(node('p', group.truncated + ' more files were read and are in the reading order.',
      'small text-muted'));
  }
  if (group.note) card.append(node('p', group.note, 'small text-muted dg-note'));
  return card;
}

function modeBar(o) {
  const bar = node('div', '', 'mode-bar');
  bar.append(node('span', 'Explain it for:', 'mode-label'));
  const group = node('div', '', 'mode-group');
  for (const mode of MODES) {
    const button = node('button', mode.label,
      'mode-button' + (mode.key === overviewRole ? ' mode-button-on' : ''));
    button.type = 'button';
    button.title = mode.blurb;
    button.addEventListener('click', () => { overviewRole = mode.key; renderOverview(o); });
    group.append(button);
  }
  bar.append(group);
  const here = MODES.find(m => m.key === overviewRole);
  bar.append(node('p', here ? here.blurb : '', 'small text-muted mode-blurb'));
  return bar;
}

function proseCard(sec, short) {
  const card = node('div', '', 'overview-section-card');
  const header = node('div', '', 'overview-section-header');
  header.append(node('h4', `${TOPIC_ICONS[sec.key] || '📋'} ${sec.title}`, 'overview-section-title'));
  if (sec.sources.length) header.append(node('span', `${sec.sources.length} excerpts`, 'badge'));
  card.append(header);
  if (sec.error) card.append(node('p', sec.error, 'error'));

  const statements = sec.statements || [];
  const limit = shows().statements || STATEMENTS_SHOWN;
  const head = short ? statements.slice(0, limit) : statements;
  const tail = short ? statements.slice(limit) : [];
  const list = node('div', '', 'overview-statements');
  for (const st of head) {
    const p = node('p', '', 'answerText overview-text');
    p.append(document.createTextNode(st.text + ' '));
    citationsInto(p, st, sec.sources, `overview-src-${sec.key}-`);
    list.append(p);
  }
  card.append(list);

  if (tail.length) {
    const more = node('details', '', 'help-details');
    more.append(node('summary', `${tail.length} more ${tail.length === 1 ? 'point' : 'points'} on this`));
    const holder = node('div', '', 'details-content');
    for (const st of tail) {
      const p = node('p', '', 'answerText overview-text');
      p.append(document.createTextNode(st.text + ' '));
      citationsInto(p, st, sec.sources, `overview-src-${sec.key}-`);
      holder.append(p);
    }
    more.append(holder);
    card.append(more);
  }

  if (sec.missing_information) {
    card.append(node('p', `⚠️ Not shown by these excerpts: ${sec.missing_information}`, 'small missing-note'));
  }
  if (sec.checks && sec.checks.unsupported) {
    card.append(node('p', `${sec.checks.unsupported} statement${sec.checks.unsupported > 1 ? 's' : ''} here ` +
      'could not be matched to the excerpt cited. Each one is marked, and the excerpt is below.',
      'small missing-note'));
  }
  if (sec.checks && sec.checks.generic) {
    card.append(node('p', sec.checks.generic + ' statement' + (sec.checks.generic > 1 ? 's' : '') +
      ' here named nothing from this project and would be equally true of any other one. ' +
      'Each one is marked.', 'small missing-note'));
  }
  if (shows().excerpts && sec.sources && sec.sources.length > 0) {
    const holder = node('details', '', 'source overview-sources-details');
    holder.append(node('summary', `The ${sec.sources.length} excerpts behind this`));
    for (const s of sec.sources) holder.append(excerpt(s, `overview-src-${sec.key}-`));
    card.append(holder);
  }
  return card;
}

function readingOrderCard(o) {
  const r = node('div', '', 'overview-section-card reading-order-card');
  const header = node('div', '', 'overview-section-header');
  header.append(node('h4', '📚 Suggested reading order', 'overview-section-title'));
  header.append(node('span', `${o.reading_order.length} files`, 'badge'));
  r.append(header);
  r.append(node('p', 'Taken from the indexed file paths, not from the model. Each one opens at the scanned commit.', 'small text-muted'));
  const ul = document.createElement('ul');
  ul.className = 'fileList reading-file-list';
  for (const f of o.reading_order) {
    const li = node('li', '');
    if (f.url) {
      const a = node('a', f.path, 'mono fact-name');
      a.href = f.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = 'Open ' + f.path;
      li.append(a);
    } else {
      li.append(node('strong', f.path, 'mono'));
    }
    li.append(node('span', ` — ${f.why}`, 'text-muted'));
    ul.append(li);
  }
  r.append(ul);
  return r;
}

function stepRail(o, body, at) {
  const rail = node('div', '', 'step-rail');
  o.steps.forEach((step, position) => {
    const pill = node('button', String(position + 1),
      'step-pill' + (position === at ? ' step-pill-on' : '') +
      (position < at ? ' step-pill-done' : '') +
      (step.ready ? '' : ' step-pill-waiting'));
    pill.type = 'button';
    pill.title = step.ready ? step.title : step.title + ' (still being written)';
    pill.addEventListener('click', () => { stepKey = step.key; renderWalk(o, body, true); });
    rail.append(pill);
  });
  return rail;
}

function renderWalk(o, body, moved) {
  body.replaceChildren();
  let at = o.steps.findIndex(s => s.key === stepKey);
  if (at < 0) at = 0;
  const step = o.steps[at];
  stepKey = step.key;
  const sections = Object.fromEntries(o.sections.map(s => [s.key, s]));
  const facts = Object.fromEntries((o.facts || []).map(g => [g.key, g]));
  const drawings = Object.fromEntries((o.diagrams || []).map(d => [d.key, d]));

  body.append(modeBar(o));
  const bar = node('div', '', 'walk-bar');
  bar.append(stepRail(o, body, at));
  const toggle = node('button', 'Show everything on one page', 'btn btn-secondary btn-sm');
  toggle.type = 'button';
  toggle.addEventListener('click', () => { overviewMode = 'all'; renderOverview(o); });
  bar.append(toggle);
  body.append(bar);

  const waiting = o.steps.filter(s => !s.ready).length;
  const head = node('div', '', 'walk-head');
  head.append(node('p', `Walkthrough step ${at + 1} of ${o.steps.length}` +
    (waiting ? ` · ${waiting} later ${waiting === 1 ? 'step is' : 'steps are'} still being written` : ''),
    'eyebrow walk-count'));
  head.append(node('h3', step.title, 'walk-title'));
  head.append(node('p', step.kt, 'walk-kt'));
  body.append(head);

  const allowed = shows();
  for (const key of step.diagrams) {
    if (allowed.diagrams && drawings[key]) body.append(diagramCard(drawings[key]));
  }
  if (step.roles && allowed.roles && o.roles && o.roles.cards && o.roles.cards.length) {
    body.append(roleCard(o.roles));
  }
  if (allowed.prose) {
    for (const key of step.topics) if (sections[key]) body.append(proseCard(sections[key], true));
  }
  for (const key of step.facts) {
    if (!facts[key]) continue;
    if (allowed.facts && !allowed.facts.includes(key)) continue;
    body.append(factGroup(facts[key]));
  }
  if (step.reading_order && allowed.readingOrder && o.reading_order && o.reading_order.length) {
    body.append(readingOrderCard(o));
  }
  if (!allowed.prose && step.topics.length) {
    body.append(node('p', 'The written explanation for this step is hidden in this view. ' +
      'Switch to New here or Developer to read it.', 'small text-muted'));
  }

  if (step.waiting_for && step.waiting_for.length) {
    body.append(node('p', 'The written explanation for this step is still being produced by the ' +
      'local model. Everything already on this step is finished and will not change.', 'banner'));
  }
  if (!o.complete && o.topics_total) {
    body.append(node('p', `Across the whole walkthrough, ${o.topics_done} of ${o.topics_total} ` +
      'written sections are done. Every diagram and every group of facts was finished before ' +
      'the first one started, so only the prose is still arriving.', 'small text-muted'));
  }

  const moves = node('div', '', 'walk-moves');
  const back = node('button', '← Back', 'btn btn-secondary');
  back.type = 'button';
  back.disabled = at === 0;
  back.addEventListener('click', () => { stepKey = o.steps[at - 1].key; renderWalk(o, body, true); });
  moves.append(back);
  if (at < o.steps.length - 1) {
    const next = node('button', 'Next: ' + o.steps[at + 1].title + ' →', 'btn btn-primary');
    next.type = 'button';
    next.addEventListener('click', () => { stepKey = o.steps[at + 1].key; renderWalk(o, body, true); });
    moves.append(next);
  } else {
    const done = node('button', 'Back to the start', 'btn btn-secondary');
    done.type = 'button';
    done.addEventListener('click', () => { stepKey = o.steps[0].key; renderWalk(o, body, true); });
    moves.append(done);
  }
  body.append(moves);
  if (moved) body.scrollTop = 0;
}

function renderEverything(o, body) {
  body.replaceChildren();
  const bar = node('div', '', 'walk-bar');
  bar.append(node('p', o.walkthrough_note || '', 'small text-muted'));
  if (o.steps && o.steps.length) {
    const toggle = node('button', 'Walk me through it step by step', 'btn btn-primary btn-sm');
    toggle.type = 'button';
    toggle.addEventListener('click', () => { overviewMode = 'walk'; renderOverview(o); });
    bar.append(toggle);
  }
  body.append(bar);
  body.append(modeBar(o));
  body.append(node('p', o.scope_note, 'small text-muted'));

  if (o.diagrams && o.diagrams.length) {
    const head = node('div', '', 'overview-group-head');
    head.append(node('h4', 'Drawn from the files', 'overview-group-title'));
    head.append(node('p', 'An arrow or a box exists because a line in a file put it there.', 'small text-muted'));
    body.append(head);
    for (const d of o.diagrams) body.append(diagramCard(d));
  }

  if (o.roles && o.roles.cards && o.roles.cards.length && shows().roles) {
    body.append(roleCard(o.roles));
  }

  if (o.facts && o.facts.length) {
    const head = node('div', '', 'overview-group-head');
    head.append(node('h4', 'Read straight out of the files', 'overview-group-title'));
    head.append(node('p', 'Nothing in this part was written by the model. Every line opens at the ' +
      'file and line it came from.', 'small text-muted'));
    body.append(head);
    for (const group of o.facts) {
    if (shows().facts && !shows().facts.includes(group.key)) continue;
    body.append(factGroup(group));
  }
  }

  const head = node('div', '', 'overview-group-head');
  head.append(node('h4', 'Explained by the local model', 'overview-group-title'));
  head.append(node('p', 'Each section was retrieved and explained on its own. The excerpts behind ' +
    'each one are underneath it, so any sentence can be checked.', 'small text-muted'));
  body.append(head);
  if (shows().prose) {
    for (const sec of o.sections) body.append(proseCard(sec, false));
  } else {
    body.append(node('p', 'The written sections are hidden in this view. Switch to New here ' +
      'or Developer to read them.', 'small text-muted'));
  }

  if (!o.complete && o.topics_total) {
    body.append(node('p', `Still working: ${o.topics_done} of ${o.topics_total} sections finished. ` +
      'The rest appear here as they are written.', 'banner'));
  }
  if (o.reading_order && o.reading_order.length) body.append(readingOrderCard(o));
  body.append(node('p', `Built in ${o.elapsed_seconds}s · Snapshot ${o.commit.slice(0, 12)} · ${o.built_at ? time(o.built_at) : ''}`, 'answerMeta'));
}

function renderOverview(o) {
  const body = $('overviewBody');
  if (!o) { body.replaceChildren(); return; }
  if (overviewMode === 'walk' && o.steps && o.steps.length) renderWalk(o, body, false);
  else renderEverything(o, body);
}

async function refreshOverview() {
  try {
    const r = await api('overview');
    const building = r.building || (state && state.overview_building);
    const p = r.progress || (state && state.overview_progress);
    $('overviewButton').disabled = building || !state || !state.ready || state.busy;

    // While building, the payload on disk already holds the facts and every finished section,
    // so it is rendered rather than hidden behind a progress line. Waiting several minutes to
    // see anything at all was the single worst part of using this page.
    if (r.overview) {
      const done = r.overview.topics_done || 0;
      const total = r.overview.topics_total || r.overview.sections.length;
      const failed = r.overview.sections.filter(s => s.error).length;
      if (building) {
        // The badge used to read "3 of 8" directly above a walkthrough rail reading "7 of 7",
        // two different counts in the same shape, side by side. The badge counts written
        // sections, the rail counts walkthrough steps, and only one of them should look like
        // a position, so this one says what it is counting instead.
        $('overviewBadge').textContent = `Writing ${Math.min(done + 1, total)}/${total}`;
        $('overviewState').textContent = p
          ? `Writing the ${total} explanations the walkthrough uses. On number ${Math.min(done + 1, total)} now: ${p.phase}. Every diagram and fact is already done, and finished explanations appear below as they arrive.`
          : 'Building. Finished parts are shown below as they arrive.';
      } else if (!r.overview.complete) {
        $('overviewBadge').textContent = 'Incomplete';
        $('overviewState').textContent = `Stopped after ${done} of ${total} sections. Build again to finish it.`;
      } else {
        $('overviewBadge').textContent = failed ? 'Partial' : 'Ready';
        $('overviewState').textContent = failed
          ? `${failed} of ${r.overview.sections.length} sections have no explanation. The facts and excerpts are still there.`
          : 'Ready. Every line can be opened at its source.';
      }
      const key = [r.overview.commit, r.overview.built_at, done, building].join('|');
      if (key !== renderedOverview) { renderedOverview = key; renderOverview(r.overview); }
      return;
    }

    if (building) {
      $('overviewBadge').textContent = 'Building';
      $('overviewState').textContent = p
        ? `Reading the files and drawing the diagrams, then writing explanation 1 of ${p.total}: ${p.phase}.`
        : 'Building.';
      return;
    }

    $('overviewBadge').textContent = 'Not built';
    $('overviewState').textContent = r.reason || 'No overview yet.';
    if (renderedOverview !== null) { renderedOverview = null; $('overviewBody').replaceChildren(); }
  } catch (e) {
    renderedOverview = null;
    $('overviewBody').replaceChildren();
    $('overviewBadge').textContent = 'Unavailable';
    $('overviewState').textContent = e.message;
  }
}

$('overviewButton').addEventListener('click', async () => {
  error();
  try {
    await api('overview', {});
    $('overviewBadge').textContent = 'Building';
    $('overviewButton').disabled = true;
    await refreshOverview();
  } catch (e) {
    error(e.message);
  }
});

$('askForm').addEventListener('submit', async e => {
  e.preventDefault();
  error();
  asking = true;
  $('askButton').disabled = true;
  $('feedback').hidden = true;
  answerId = null;

  $('answer').replaceChildren(node('p', 'Checking source access, finding relevant excerpts and preparing your answer. Local CPU inference can take a few minutes.', 'muted'));
  
  const began = performance.now();
  const timer = setInterval(() => {
    $('model').textContent = `Working locally · ${Math.round((performance.now() - began) / 1000)}s elapsed`;
  }, 1000);

  try {
    const r = await api('ask', { question: $('question').value.trim() });
    renderAnswer(r);
  } catch (e) {
    $('answer').replaceChildren(node('p', e.message, 'error'));
  } finally {
    clearInterval(timer);
    asking = false;
    await refresh();
  }
});

$('feedbackButton').addEventListener('click', async () => {
  try {
    await api('feedback', { answer_id: answerId, rating: $('rating').value, sufficiency: $('sufficiency').value });
    $('feedbackStatus').textContent = 'Saved locally.';
  } catch (e) {
    error(e.message);
  }
});

$('question').value = '';
$('repo').value = '';
$('branch').value = '';

const connectResult = new URLSearchParams(window.location.search).get('connect');
if (connectResult) {
  const reason = new URLSearchParams(window.location.search).get('reason');
  if (connectResult !== 'ok') error('Connecting did not finish' + (reason ? ': ' + reason : '') + '. Check the credentials in the platform panel and try again.');
  history.replaceState({}, '', '/');
}
showView('viewSelect');
refresh(true).then(() => { refreshPlatforms(); refreshSlack(); refreshJira(); return refreshOverview(); })
  .then(() => { if (connectResult === 'ok') openConnect('slack_user'); });
setInterval(() => refresh().then(() => { refreshPlatforms(); refreshSlack(); refreshJira(); return refreshOverview(); }), 2500);
