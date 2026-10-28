"""Describe recorded imports without reading sources or claiming unmeasured completeness."""
from collections import Counter

from pka.config import LIMITS


def metric(label, value):
    return {'label':label, 'value':value}


def repository(scan, available):
    result = {'source':'github', 'state':'not_read', 'available':available, 'read_at':None,
              'summary':'No repository scan has been recorded.', 'counts':[], 'notes':[], 'details':[]}
    if not scan:
        return result
    result.update(state=scan['status'], read_at=scan.get('finished'),
                  summary=f"{scan.get('read', 0)} files read from {scan.get('total', 0)} listed candidates.")
    result['counts'] = [metric(label, scan.get(key, 0)) for label, key in (
        ('Files read','read'), ('Skipped','skipped'), ('Failed','failed'), ('Listed candidates','total'))]
    result['counts'].append(metric('Not processed', max(0, scan.get('total', 0)-scan.get('processed', 0))))
    for key, label in (('reused', 'Unchanged files reused'), ('fetched', 'Files fetched')):
        if key in scan:
            result['counts'].append(metric(label, scan[key]))
    if scan.get('dependency_files'):
        result['counts'].append(metric('Dependency files excluded before listing', scan['dependency_files']))
    if scan.get('tree_incomplete'):
        result['notes'].append('The file list was truncated. The total number of repository files is unknown.')
    reasons = Counter((f.get('reason') or f['state']) for f in scan.get('files', []) if f['state'] != 'read')
    result['details'] = [{'name':reason.replace('_', ' '), 'summary':f'{count} file(s)', 'notes':[]}
                         for reason, count in sorted(reasons.items())]
    if scan.get('error'):
        result['notes'].append(scan['error'])
    if not available:
        result['notes'].append('This scan is not available for answers. Finish a usable repository scan first.')
    elif scan['status'] == 'partial':
        result['notes'].append('Some supported content was omitted. Answers can only use the files that were read.')
    result['notes'].append('Secret, unsupported and dependency files are excluded by policy. Import history lists individual files and reasons.')
    return result


def external(index, name, available):
    saved = index.source_import(name)
    cfg = (index.settings() or {}).get(name) or {}
    report = (saved or {}).get('report') or {}
    action = 'Read issues' if name == 'jira' else 'Read messages'
    selected = bool(cfg.get('project') if name == 'jira' else cfg.get('channels'))
    result = {'source':name, 'state':'not_read', 'available':bool(saved) and available,
              'read_at':report.get('read_at'), 'counts':[], 'notes':[], 'details':[],
              'summary':f'No saved import. Use {action} after selecting this source.' if selected else 'No source selected.'}
    if not saved:
        return result
    result['counts'].append(metric('Stored excerpts', report.get('blocks', 0)))
    if name == 'jira':
        coverage = report.get('coverage') or {}
        result['state'] = coverage.get('state', 'unknown')
        result['summary'] = f"{report.get('issues', 0)} issues read from {report.get('project', cfg.get('project', ''))}."
        result['counts'].insert(0, metric('Issues read', report.get('issues', 0)))
        if 'comments' in coverage:
            result['counts'].append(metric('Comments received before text limits', coverage['comments']))
        for key, label in (('custom_text_fields','Custom text fields read'), ('comment_pages','Additional comment pages read')):
            if key in coverage:
                result['counts'].append(metric(label, coverage[key]))
        result['notes'].extend(coverage.get('notes') or [])
        result['notes'].append(f'Reads at most {LIMITS.jira_max_issues} issues, {LIMITS.jira_max_comments} comments and {LIMITS.jira_max_comment_pages} comment pages per issue. Issue text up to {LIMITS.jira_max_issue_chars:,} characters is split into searchable excerpts; any further text is reported as omitted.')
        result['notes'].append('Includes visible descriptions and custom text fields such as acceptance criteria. Attachment contents and non-text custom fields are not imported.')
    else:
        channels = report.get('channels') or []
        failed = sum(bool(c.get('error')) for c in channels)
        result['state'] = report.get('coverage_state', 'partial' if failed else 'unknown')
        result['summary'] = f'{len(channels)-failed} of {len(cfg.get("channels", []))} selected channels read.'
        result['counts'] += [metric('Channels read', len(channels)-failed), metric('Failed channels', failed),
                             metric('Messages and replies read', sum(c.get('messages', 0) for c in channels))]
        for key, label in (('reply_pages','Reply pages read'), ('edited_messages','Edited messages read'),
                           ('deleted_events','Deleted-message markers excluded')):
            result['counts'].append(metric(label, sum((c.get('coverage') or {}).get(key, 0) for c in channels)))
        for channel in channels:
            coverage = channel.get('coverage') or {}
            notes = ([channel['error']] if channel.get('error') else []) + (coverage.get('notes') or [])
            if not channel.get('error') and not coverage:
                notes.append('History and thread coverage were not recorded for this read.')
            result['details'].append({'name':'#'+channel['name'],
                'summary':'Failed to read' if channel.get('error') else f"{channel.get('messages', 0)} messages and replies; {channel.get('blocks', 0)} excerpts",
                'notes':notes})
        result['notes'].append(f'Reads at most {LIMITS.slack_max_messages} history messages and {LIMITS.slack_max_threads} threads per channel. Each thread is paginated up to {LIMITS.slack_max_reply_pages} pages or {LIMITS.slack_max_replies} replies, with {LIMITS.slack_max_channel_replies} replies per channel overall.')
        result['notes'].append('Join/leave events and messages without text are excluded.')
        result['notes'].append('Refresh replaces the saved snapshot. Edits and missing messages within the current readable window invalidate saved answers when content is rechecked. This is a bounded read, not a live event subscription; retention, history limits and concurrent edits can affect coverage.')
    if result['state'] == 'unknown':
        result['notes'].append(f'Completeness was not established for this saved import. Use {action} to record current coverage.')
    if result['state'] == 'partial':
        result['notes'].append('Some information is missing. Check the limits or errors below before reading again; retrying cannot bypass a fixed limit.')
    if not available:
        result['notes'].append('Saved import retained, but unavailable for answers until a repository scan is usable.')
    result['notes'].append('Coverage applies only to the selected source and information visible to the connected account.')
    return result


def describe(service):
    index = service.index
    active = index.active_scan()
    available = active is not None
    sources = {'github':repository(service.progress or index.latest(), available),
               **{name:external(index, name, available) for name in ('jira','slack')}}
    # A newer failed attempt is not the snapshot still used by answers.
    sources['github']['snapshot_read_at'] = active.get('finished') if active else None
    for name in ('jira', 'slack'):
        sources[name]['snapshot_read_at'] = sources[name]['read_at'] if sources[name]['available'] else None
    if (index.settings() or {}).get('local'):
        saved = index.source_import('local')
        report = (saved or {}).get('report') or {}
        detail = {'status':report.get('state', 'not_read'), 'finished':report.get('read_at'),
                  'processed':report.get('total', 0), **report}
        sources['local'] = repository(detail, bool(saved) and available)
        sources['local']['source'] = 'local'
        sources['local']['snapshot_read_at'] = report.get('read_at') if saved and available else None
        sources['local']['notes'].append('Local files supplement the GitHub repository. GitHub, Jira and Slack imports are kept when this folder is read again.')
    job = service.job_status()
    if job and job['kind'] in {'scan','jira','slack','local'} and service.job['scope'] == service.job_scope(job['kind']):
        name = 'github' if job['kind'] == 'scan' else job['kind']
        if job['state'] in {'queued','running','cancelling','failed','cancelled','interrupted'}:
            sources[name]['attempt'] = {k:job.get(k) for k in ('state','started_at','finished_at','error')}
    settings = index.settings() or {}
    if settings.get('repo', '').startswith('zip:'):
        sources['zip'] = sources.pop('github')
        sources['zip']['source'] = 'zip'
        archive = settings.get('archive') or {}
        sources['zip']['notes'].append('Reads the uploaded ZIP snapshot. Upload a new ZIP after changing your project files.')
        for reason, count in (archive.get('skipped') or {}).items():
            sources['zip']['details'].append({'name':reason.replace('_', ' '), 'summary':f'{count} file(s) excluded during upload', 'notes':[]})
        if archive.get('skipped', {}).get('scan_size_limit'):
            sources['zip']['state'] = 'partial'
            sources['zip']['notes'].append('Upload extraction reached the file or total text limit; only the retained files were scanned.')
    elif settings.get('repo', '').startswith('local:'):
        sources['local'] = sources.pop('github')
        sources['local']['source'] = 'local'
        sources['local']['notes'].append('Reads the current working folder, including uncommitted and untracked files. Uses built-in exclusions; custom .gitignore patterns are not applied. Symlinks, junctions and private tool directories are not followed.')
    return {'sources':sources}
