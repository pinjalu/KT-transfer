'use strict';

const $ = id => document.getElementById(id);
let state, answerId, answerScan, nextOffset = 0, loadedFiles = false, asking = false, lastScanId, renderedOverview = null;

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

function renderAnswer(r) {
  answerId = r.answer_id;
  answerScan = r.scan_id;
  const out = $('answer');
  out.replaceChildren();

  if (r.warning) out.append(node('p', r.warning, 'banner'));
  if (r.error) out.append(node('p', r.error, 'error'));

  // Main Explanation Container
  if (r.statements && r.statements.length > 0) {
    const explanationBox = node('div', '', 'explanation-box');
    
    // Top Core Direct Answer Statement
    const firstStatement = r.statements[0];
    const coreAnswerCard = node('div', '', 'core-answer-card');
    const coreHeader = node('div', '', 'core-answer-header');
    coreHeader.append(node('span', '💡 Core Explanation (For New Developers)', 'core-title'));
    
    // Copy Answer Action
    const copyBtn = node('button', '📋 Copy Answer', 'btn btn-secondary btn-sm copy-btn');
    copyBtn.type = 'button';
    copyBtn.addEventListener('click', () => {
      const fullText = r.statements.map((s, idx) => `${idx + 1}. ${s.text}`).join('\n\n');
      navigator.clipboard.writeText(fullText);
      copyBtn.textContent = '✅ Copied!';
      setTimeout(() => { copyBtn.textContent = '📋 Copy Answer'; }, 2000);
    });
    coreHeader.append(copyBtn);
    coreAnswerCard.append(coreHeader);

    const firstP = node('p', '', 'answerText main-answer-text');
    firstP.append(document.createTextNode(firstStatement.text + ' '));
    for (const sid of firstStatement.source_ids) {
      const badge = node('span', `[${sid}]`, 'citation-pill');
      badge.addEventListener('click', () => {
        const el = document.getElementById(`source-${sid}`);
        if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      });
      firstP.append(badge);
      firstP.append(document.createTextNode(' '));
    }
    coreAnswerCard.append(firstP);
    explanationBox.append(coreAnswerCard);

    // Step-by-Step Breakdown for Remaining Statements
    if (r.statements.length > 1) {
      const stepsContainer = node('div', '', 'steps-container');
      stepsContainer.append(node('h4', 'Key Steps & Details:', 'steps-title'));

      for (let i = 1; i < r.statements.length; i++) {
        const st = r.statements[i];
        const stepRow = node('div', '', 'step-item');
        const stepNum = node('span', `${i + 1}`, 'step-number');
        const stepContent = node('div', '', 'step-content');
        const stepP = node('p', '', 'step-text');
        stepP.append(document.createTextNode(st.text + ' '));
        
        for (const sid of st.source_ids) {
          const badge = node('span', `[${sid}]`, 'citation-pill');
          badge.addEventListener('click', () => {
            const el = document.getElementById(`source-${sid}`);
            if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
          });
          stepP.append(badge);
          stepP.append(document.createTextNode(' '));
        }
        stepContent.append(stepP);
        stepRow.append(stepNum);
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

  out.append(node('p', `⏱️ Generated in ${r.elapsed_seconds}s · Snapshot ${r.commit.slice(0, 12)} · Scanned ${time(r.scanned_at)}`, 'answerMeta'));
  out.append(node('h4', `Sources used in explanation (${r.sources.length})`, 'mt-2'));

  for (const s of r.sources) {
    const d = node('details', '', 'source');
    d.id = `source-${s.source_id}`;
    d.append(node('summary', `[${s.source_id}] ${s.path} · lines ${s.start}–${s.end}`));
    if (s.url) {
      const a = node('a', 'View File on GitHub ↗');
      a.href = s.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      d.append(a);
    }
    if (s.split) d.append(node('p', 'This excerpt is part of a longer code block.', 'small text-muted'));
    d.append(node('pre', s.text));
    out.append(d);
  }

  out.append(node('p', r.citation_check, 'small text-muted mt-2'));

  $('rating').value = r.rating || 'not assessed';
  $('sufficiency').value = r.sufficiency || 'not assessed';
  $('feedbackStatus').textContent = '';
  $('feedback').hidden = false;

  out.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderOverview(o) {
  const body = $('overviewBody');
  body.replaceChildren();
  if (!o) return;

  const topicIcons = {
    purpose: '🎯',
    technologies: '🛠️',
    setup: '🚀',
    flows: '⚡',
    data: '🗄️'
  };

  body.append(node('p', o.scope_note, 'small text-muted'));

  for (const sec of o.sections) {
    const card = node('div', '', 'overview-section-card');
    const icon = topicIcons[sec.key] || '📋';
    
    const cardHeader = node('div', '', 'overview-section-header');
    cardHeader.append(node('h4', `${icon} ${sec.title}`, 'overview-section-title'));
    if (sec.sources.length) {
      cardHeader.append(node('span', `${sec.sources.length} sources`, 'badge'));
    }
    card.append(cardHeader);

    if (sec.error) {
      card.append(node('p', sec.error, 'error'));
    }

    if (sec.statements && sec.statements.length > 0) {
      const stmtList = node('div', '', 'overview-statements');
      for (const st of sec.statements) {
        const p = node('p', st.text + ' ', 'answerText overview-text');
        for (const sid of st.source_ids) {
          const badge = node('span', `[${sid}]`, 'citation-pill');
          badge.addEventListener('click', () => {
            const el = document.getElementById(`overview-src-${sec.key}-${sid}`);
            if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
          });
          p.append(badge);
          p.append(document.createTextNode(' '));
        }
        stmtList.append(p);
      }
      card.append(stmtList);
    }

    if (sec.missing_information) {
      const gap = node('p', `⚠️ Missing: ${sec.missing_information}`, 'small text-muted missing-note');
      card.append(gap);
    }

    if (sec.sources && sec.sources.length > 0) {
      const srcDetails = node('details', '', 'source overview-sources-details');
      srcDetails.append(node('summary', `View Excerpts (${sec.sources.length})`));
      for (const s of sec.sources) {
        const e = node('details', '', 'source');
        e.id = `overview-src-${sec.key}-${s.source_id}`;
        e.append(node('summary', `[${s.source_id}] ${s.path} · lines ${s.start}-${s.end}`));
        if (s.url) {
          const a = node('a', 'Open this commit on GitHub ↗');
          a.href = s.url;
          a.target = '_blank';
          a.rel = 'noopener noreferrer';
          e.append(a);
        }
        e.append(node('pre', s.text));
        srcDetails.append(e);
      }
      card.append(srcDetails);
    }

    body.append(card);
  }

  if (o.reading_order && o.reading_order.length) {
    const r = node('div', '', 'overview-section-card reading-order-card');
    const rHeader = node('div', '', 'overview-section-header');
    rHeader.append(node('h4', '📚 Suggested Reading Order', 'overview-section-title'));
    rHeader.append(node('span', `${o.reading_order.length} files`, 'badge'));
    r.append(rHeader);
    r.append(node('p', 'Derived from indexed repository file structure:', 'small text-muted'));
    
    const ul = document.createElement('ul');
    ul.className = 'fileList reading-file-list';
    for (const f of o.reading_order) {
      const li = node('li', '');
      li.append(node('strong', f.path, 'mono'));
      li.append(node('span', ` — ${f.why}`, 'text-muted'));
      ul.append(li);
    }
    r.append(ul);
    body.append(r);
  }

  body.append(node('p', `Built in ${o.elapsed_seconds}s · Snapshot ${o.commit.slice(0, 12)} · ${o.built_at ? time(o.built_at) : ''}`, 'answerMeta'));
}

async function refreshOverview() {
  try {
    const r = await api('overview');
    const building = r.building || (state && state.overview_building);
    const p = r.progress || (state && state.overview_progress);
    $('overviewButton').disabled = building || !state || !state.ready || state.busy;

    if (building && p) {
      $('overviewBadge').textContent = 'Building';
      $('overviewState').textContent = `Working through topic ${p.done + 1} of ${p.total}: ${p.phase}. Local CPU inference takes a few minutes.`;
      return;
    }

    if (r.available && r.overview) {
      const failed = r.overview.sections.filter(s => s.error).length;
      $('overviewBadge').textContent = failed ? 'Partial' : 'Ready';
      $('overviewState').textContent = failed ? `${failed} of ${r.overview.sections.length} topics had no answer.` : 'Overview ready. Inspect topics below.';
      const key = r.overview.commit + '|' + r.overview.built_at;
      if (key !== renderedOverview) { renderedOverview = key; renderOverview(r.overview); }
    } else {
      $('overviewBadge').textContent = 'Not built';
      $('overviewState').textContent = r.reason || 'No overview yet.';
      if (renderedOverview !== null) { renderedOverview = null; $('overviewBody').replaceChildren(); }
    }
  } catch (e) {}
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
