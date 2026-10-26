"""Saved answer evaluations, scoped to one workspace and exact source revision."""
import json
import os

from pka import answer_evaluation as evaluation
from pka.config import ROOT, now
from pka.connectors.base import SourceError


SETS = {
    'bsa_basics': ('BSA project basics', 'answers_bsa.json'),
    'bsa_boundaries': ('BSA thresholds and evidence boundaries', 'answers_bsa_boundaries.json'),
    'bsa_followups': ('BSA model and retrieval questions', 'answers_bsa_followups.json'),
}


def spec_for(set_id):
    if set_id not in SETS:
        raise SourceError('evaluation', 'Choose a saved question set.')
    try:
        return evaluation.validate_spec(json.loads((ROOT / 'evals' / SETS[set_id][1]).read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError, KeyError):
        raise SourceError('evaluation', 'This question set is unavailable or invalid.') from None


def validate_target(service, set_id):
    spec = spec_for(set_id)
    scan = service.index.active_scan() or {}
    if service.demo:
        raise SourceError('evaluation', 'Evaluation requires a live project, not sample data.')
    if scan.get('status') not in {'complete', 'partial'} or (scan.get('repo'), scan.get('commit')) != (spec['repo'], spec['commit']):
        raise SourceError('evaluation', 'The question set requires its exact repository and commit. Select and scan that version first.')
    return spec


def catalog(service):
    result = []
    for set_id, (title, _) in SETS.items():
        spec = spec_for(set_id)
        reason = ''
        try:
            validate_target(service, set_id)
        except SourceError as exc:
            reason = str(exc)
        result.append({'id': set_id, 'title': title, 'repo': spec['repo'], 'commit': spec['commit'],
                       'cases': len(spec['cases']), 'available': not reason, 'reason': reason})
    return result


def save(index, run_id, report):
    evaluation.summarize(report)
    with index.db() as db:
        db.execute('BEGIN IMMEDIATE')
        revision = db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()[0]
        if revision != report['knowledge_revision']:
            raise SourceError('stale', 'Sources changed during this evaluation. Run the questions again.')
        db.execute('INSERT OR REPLACE INTO evaluation_runs VALUES(?,?)', (run_id, json.dumps(report)))
        db.execute('DELETE FROM evaluation_runs WHERE id NOT IN (SELECT id FROM evaluation_runs ORDER BY id DESC LIMIT 20)')


def runs(index, run_id=None):
    with index.db() as db:
        rows = db.execute('SELECT e.id,e.payload,j.detail FROM evaluation_runs e JOIN jobs j ON j.id=e.id '
                          + ('WHERE e.id=? ' if run_id is not None else '') + 'ORDER BY e.id DESC LIMIT 20',
                          (run_id,) if run_id is not None else ()).fetchall()
    return [{**json.loads(r['payload']), 'id': r['id'], 'state': json.loads(r['detail'])['state']} for r in rows]


def retained(index, run_id, case_id):
    found = runs(index, run_id)
    if not found:
        raise SourceError('evaluation', 'This evaluation is no longer available. Run a new evaluation.')
    report = found[0]
    spec = spec_for(report['set_id'])
    if report['knowledge_revision'] != index.revision or report['dataset_hash'] != evaluation.digest(spec):
        raise SourceError('stale', 'The sources or question set changed. Run a new evaluation.')
    case = next((c for c in spec['cases'] if c['id'] == case_id), None)
    row = next((r for r in report['results'] if r['case_id'] == case_id), None)
    if not case or not row or not row.get('answer_id'):
        raise SourceError('evaluation', 'No retained answer is available for this case.')
    with index.db() as db:
        saved = db.execute('SELECT response FROM answers WHERE id=? AND scan_id=(SELECT scan_id FROM active WHERE id=1)',
                           (row['answer_id'],)).fetchone()
    if saved:
        answer = {**json.loads(saved[0]), 'answer_id': row['answer_id']}
        if evaluation.digest(answer) == row['response_hash']:
            return report, case, row, answer
    raise SourceError('stale', 'The exact answer is no longer retained. Run a new evaluation.')


async def inspect(service, run_id, case_id):
    scan = service.index.active_scan()
    if not scan:
        raise SourceError('scan', 'Run a successful scan first.')
    checked = await service.check_external_access(scan)
    report, case, row, answer = retained(service.index, run_id, case_id)
    service.ensure_current(checked)
    return {'run_id': run_id, 'dataset_hash': report['dataset_hash'], 'case': case, 'result': row, 'answer': answer}


async def review(service, run_id, case_id, item, reviewer):
    await inspect(service, run_id, case_id)
    report = runs(service.index, run_id)[0]
    if report['state'] in {'queued', 'running', 'cancelling'}:
        raise SourceError('busy', 'Wait for this evaluation to finish before saving a review.')
    # Identity comes from the signed-in account, never a caller-supplied reviewer name.
    try:
        evaluation.apply_reviews(report, {'dataset_hash': item.dataset_hash, 'reviews': [{
            'case_id': case_id, 'response_hash': item.response_hash, 'reviewer_type': 'human',
            'reviewer': reviewer, 'correctness': item.correctness, 'source_sufficiency': item.source_sufficiency}]})
    except ValueError:
        raise SourceError('stale', 'This review does not match the displayed answer. Open the case again.') from None
    row = next(r for r in report['results'] if r['case_id'] == case_id)
    row['human_review']['reviewed_at'] = now()
    save(service.index, run_id, report)
    return {'saved': True, 'review': row['human_review']}


async def run(service, set_id):
    service.begin_work()
    spec = validate_target(service, set_id)
    scan, revision = service.index.active_scan(), service.index.revision
    report = {'task_id': '5.2', 'version': 1, 'set_id': set_id, 'title': SETS[set_id][0],
              'started_at': now(), 'repo': spec['repo'], 'commit': spec['commit'],
              'dataset_hash': evaluation.digest(spec), 'cases_planned': len(spec['cases']),
              'label_provenance': spec.get('label_provenance', 'unspecified'),
              'model': os.getenv('OLLAMA_MODEL', 'qwen3:1.7b'), 'scan_id': scan['id'], 'scan_status': scan['status'],
              'knowledge_revision': revision, 'results': []}
    run_id = service.job['id']
    save(service.index, run_id, report)
    for case in spec['cases']:
        service.check_cancelled()
        service.evaluation_progress = {'phase': 'Checking ' + case['id'], 'done': len(report['results']), 'total': len(spec['cases'])}
        answer = await service.ask(case['question'])
        if answer.get('knowledge_revision') != revision:
            raise SourceError('stale', 'Sources changed during this evaluation. Run the questions again.')
        row = evaluation.score_answer(case, answer, spec)
        report['results'].append(row)
        save(service.index, run_id, report)
        service.check_cancelled()
        if row['generation_error'] or not row['scope_matches']:
            service.job_error = 'Evaluation stopped because an answer could not be generated for this source version. Retry starts a fresh run.'
            break
    report['finished_at'] = now()
    save(service.index, run_id, report)
    return report
