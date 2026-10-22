"""Evaluate generated answers through the local app; phrase checks are not accuracy scores."""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

import httpx

from pka.config import now, source_url


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_spec(spec):
    require(isinstance(spec, dict) and spec.get('version') == 1, 'Expected a version 1 answer evaluation set.')
    require(isinstance(spec.get('repo'), str) and bool(re.fullmatch(r'[\w.-]+/[\w.-]+', spec['repo'])),
            'The set needs a repository.')
    require(isinstance(spec.get('commit'), str) and bool(re.fullmatch(r'[0-9a-f]{40}', spec['commit'])),
            'The set needs an exact commit.')
    cases = spec.get('cases')
    require(isinstance(cases, list) and 1 <= len(cases) <= 100, 'The set needs 1 to 100 cases.')
    seen = set()
    for case in cases:
        require(isinstance(case, dict), 'Each case must be an object.')
        cid = case.get('id', '')
        require(isinstance(cid, str) and bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', cid)) and cid not in seen,
                'Case IDs must be unique and non-empty.')
        seen.add(cid)
        require(isinstance(case.get('question'), str) and 1 <= len(case['question'].strip()) <= 600,
                'Each case needs a question of at most 600 characters.')
        require(case.get('behavior') in {'answer', 'abstain', 'disclose_missing'}, 'Unknown expected behavior.')
        facts = case.get('facts', [])
        require(isinstance(facts, list), 'Facts must be a list.')
        require(case['behavior'] != 'answer' or bool(facts), 'Answer cases need reference facts.')
        fact_ids = set()
        for fact in facts:
            require(isinstance(fact, dict) and isinstance(fact.get('id'), str) and
                    bool(fact['id']) and fact['id'] not in fact_ids, 'Fact IDs must be unique within a case.')
            fact_ids.add(fact['id'])
            groups = fact.get('phrases')
            require(isinstance(groups, list) and bool(groups) and all(isinstance(g, list) and g and
                    all(isinstance(p, str) and p.strip() for p in g) for g in groups),
                    'Each fact needs non-empty phrase alternatives.')
            refs = fact.get('references')
            require(isinstance(refs, list) and bool(refs), 'Each fact needs source references.')
            for ref in refs:
                require(isinstance(ref, dict) and isinstance(ref.get('path'), str) and bool(ref['path']) and
                        type(ref.get('start')) is int and type(ref.get('end')) is int and
                        0 < ref['start'] <= ref['end'], 'Invalid reference path or line range.')
    return spec


def local_url(value):
    parsed = urlsplit(value)
    require(parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'} and
            not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and
            parsed.path in {'', '/'}, 'Use the local app HTTP address, without a path or credentials.')
    _ = parsed.port  # reject malformed ports before any request
    return value.rstrip('/')


def phrase_in(phrase, text):
    normalize = lambda s: ' '.join(re.findall(r'[a-z0-9]+', s.lower()))
    return (' ' + normalize(phrase) + ' ') in (' ' + normalize(text) + ' ')


def overlaps(source, reference):
    return (source.get('path') == reference['path'] and type(source.get('start')) is int and
            type(source.get('end')) is int and source['start'] <= reference['end'] and
            source['end'] >= reference['start'])


def score_answer(case, answer, spec):
    """Keep retrieval, mechanical citation checks, phrase coverage, and human judgement distinct."""
    require(isinstance(answer, dict) and isinstance(answer.get('statements'), list) and
            isinstance(answer.get('sources'), list), 'The app returned an invalid answer shape.')
    statements, sources = answer['statements'], answer['sources']
    require(all(isinstance(s, dict) and isinstance(s.get('text'), str) and
                isinstance(s.get('source_ids'), list) and all(isinstance(i, str) for i in s['source_ids'])
                for s in statements), 'Invalid answer statements.')
    require(all(isinstance(s, dict) and isinstance(s.get('source_id'), str) and
                isinstance(s.get('path'), str) for s in sources), 'Invalid source records.')
    by_id = {s['source_id']: s for s in sources}
    cited = [sid for s in statements for sid in s['source_ids']]
    duplicate_ids = len(by_id) != len(sources)
    invalid = sum(sid not in by_id for sid in cited)
    uncited = sum(not s['source_ids'] for s in statements)
    github = [s for s in sources if not s['path'].startswith(('jira/', 'slack/'))]
    bad_links = sum(type(s.get('start')) is not int or type(s.get('end')) is not int or
                    s['start'] < 1 or s['end'] < s['start'] or
                    s.get('url') != source_url(spec['repo'], spec['commit'], s['path'], s['start'], s['end'])
                    for s in github)
    references = [r for f in case.get('facts', []) for r in f['references']]
    retrieved = any(overlaps(s, r) for s in sources for r in references) if references else None
    checks = []
    for fact in case.get('facts', []):
        eligible = [s['text'] for s in statements if any(
            sid in by_id and overlaps(by_id[sid], r) for sid in s['source_ids'] for r in fact['references'])]
        phrase_match = all(any(phrase_in(p, ' '.join(eligible)) for p in group) for group in fact['phrases'])
        # Phrase overlap cannot decide whether a claim is affirmed, negated or correctly explained.
        checks.append({'id': fact['id'], 'cited_reference_phrase_match': phrase_match})
    require(isinstance(answer.get('missing_information', ''), str), 'Invalid missing-information statement.')
    missing = bool(answer.get('missing_information', '').strip())
    behavior = {'answer': bool(statements), 'abstain': not statements and missing,
                'disclose_missing': missing}[case['behavior']]
    scope_ok = (answer.get('repo'), answer.get('commit')) == (spec['repo'], spec['commit'])
    error = bool(answer.get('error'))
    passed = scope_ok and not error and behavior and not (duplicate_ids or invalid or uncited or bad_links)
    passed = passed and all(c['cited_reference_phrase_match'] for c in checks)
    return {'case_id': case['id'], 'behavior': case['behavior'], 'response_hash': digest(answer),
            'answer_id': answer.get('answer_id'), 'status': 'passed_checks' if passed else 'failed_checks',
            'scope_matches': scope_ok, 'generation_error': error, 'behavior_check': behavior,
            'retrieval': {'reference_excerpt_found': retrieved, 'sources_returned': len(sources)},
            'citations': {'references': len(cited), 'unknown_ids': invalid, 'uncited_statements': uncited,
                          'duplicate_source_ids': duplicate_ids, 'invalid_github_links': bad_links,
                          'external_links_not_checked': len(sources) - len(github)},
            'reference_phrase_checks': checks, 'statements': len(statements),
            'missing_information_present': missing, 'elapsed_seconds': answer.get('elapsed_seconds'),
            'human_review': None}


def summarize(report):
    rows = report['results']
    scored = [r for r in rows if 'retrieval' in r]
    answerable = [r for r in scored if r['behavior'] == 'answer']
    rate = lambda numerator, denominator: round(numerator / denominator, 3) if denominator else None
    references = [c for r in scored for c in r['reference_phrase_checks']]
    reviews = [r['human_review'] for r in rows if r.get('human_review')]
    report['summary'] = {
        'cases_planned': report['cases_planned'], 'cases_run': len(rows),
        'automatic_checks_passed': sum(r['status'] == 'passed_checks' for r in rows),
        'reference_retrieval_rate': rate(sum(r['retrieval']['reference_excerpt_found'] is True for r in answerable), len(answerable)),
        'cited_reference_phrase_rate': rate(sum(c['cited_reference_phrase_match'] for c in references), len(references)),
        'human_reviewed': len(reviews),
        'human_correctness': {label: sum(r['correctness'] == label for r in reviews)
                              for label in ('correct', 'partially correct', 'incorrect')},
        'human_source_sufficiency': {label: sum(r['source_sufficiency'] == label for r in reviews)
                                    for label in ('sufficient', 'partly sufficient', 'insufficient')},
        'human_review_complete': len(reviews) == report['cases_planned'] == len(rows),
    }
    report['run_complete'] = len(rows) == report['cases_planned']
    report['automatic_checks_passed'] = report['run_complete'] and all(r['status'] == 'passed_checks' for r in rows)
    report['quality_acceptance'] = 'human_review_complete' if report['summary']['human_review_complete'] else 'pending_human_review'
    return report


def apply_reviews(report, reviews):
    """Reviews bind to a dataset and exact responses so they cannot silently score a later run."""
    require(isinstance(report, dict) and isinstance(report.get('results'), list) and
            isinstance(reviews, dict) and isinstance(reviews.get('reviews'), list), 'Invalid review document.')
    require(reviews.get('dataset_hash') == report['dataset_hash'], 'Reviews belong to a different question set.')
    rows = {r['case_id']: r for r in report['results']}
    seen = set()
    for review in reviews.get('reviews', []):
        require(isinstance(review, dict), 'Each review must be an object.')
        cid = review.get('case_id')
        require(isinstance(cid, str), 'A reviewed case needs an ID.')
        require(cid in rows and cid not in seen and 'response_hash' in rows[cid], 'Invalid or duplicate reviewed case.')
        require(review.get('response_hash') == rows[cid]['response_hash'], 'Review belongs to a different answer.')
        require(review.get('reviewer_type') == 'human' and isinstance(review.get('reviewer'), str) and
                bool(review['reviewer'].strip()),
                'A human reviewer must be identified; do not label automated checks as human review.')
        require(review.get('correctness') in {'correct', 'partially correct', 'incorrect'}, 'Invalid correctness rating.')
        require(review.get('source_sufficiency') in {'sufficient', 'partly sufficient', 'insufficient'}, 'Invalid source sufficiency rating.')
        seen.add(cid)
    for review in reviews.get('reviews', []):
        rows[review['case_id']]['human_review'] = {k: review[k] for k in
            ('reviewer_type', 'reviewer', 'correctness', 'source_sufficiency')}
    return summarize(report)


def save_report(path, report):
    summarize(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def inspect_case(report, case_id, db_path):
    """Read an exact retained answer for review without creating an excerpt export."""
    row = next((r for r in report['results'] if r['case_id'] == case_id), None)
    require(row is not None and type(row.get('answer_id')) is int, 'No retained answer is identified for this case.')
    with sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        saved = db.execute('SELECT scan_id,question,response FROM answers WHERE id=?', (row['answer_id'],)).fetchone()
        active = db.execute('SELECT scan_id FROM active WHERE id=1').fetchone()
    require(saved is not None and active is not None and saved[0] == active[0],
            'This answer is no longer retained for the active scan. Run a fresh evaluation.')
    answer = json.loads(saved[2])
    answer['answer_id'] = row['answer_id']  # assigned after record_answer stores the response
    require(digest(answer) == row['response_hash'], 'The retained answer does not match this report.')
    return {'case_id': case_id, 'question': saved[1], 'statements': answer['statements'],
            'missing_information': answer.get('missing_information', ''),
            'generation_error': bool(answer.get('error')), 'sources': answer['sources']}


async def run_live(spec, output, url='http://127.0.0.1:8000', timeout=240, transport=None):
    validate_spec(spec)
    url = local_url(url)
    report = {'task_id': '5.2', 'version': 1, 'started_at': now(), 'repo': spec['repo'],
              'commit': spec['commit'], 'dataset_hash': digest(spec), 'cases_planned': len(spec['cases']),
              'label_provenance': spec.get('label_provenance', 'unspecified'),
              'limitations': ['Phrase checks and citation validity do not establish factual correctness.',
                             'Human correctness and source sufficiency are reviewed separately.',
                             'This report excludes questions, generated prose and source excerpts. The app retains its normal answer records.'],
              'results': []}
    async with httpx.AsyncClient(base_url=url, transport=transport, trust_env=False, follow_redirects=False,
                                 timeout=timeout, headers={'X-PKA-Request': '1'}) as client:
        response = await client.get('/api/status')
        response.raise_for_status()
        status = response.json()
        # last_successful_scan is only a timestamp. The displayed scan contains the
        # scope; a partial scan is usable but must remain labelled partial in the report.
        scan = status.get('scan') or {}
        require(not status.get('demo') and status.get('ready') and not status.get('busy'),
                'The live app must have an active scan and be idle.')
        require(scan.get('status') in {'complete', 'partial'}, 'The latest scan must be complete or partial.')
        require((scan.get('repo'), scan.get('commit')) == (spec['repo'], spec['commit']),
                'The active repository or commit does not match this evaluation set.')
        report.update(model=status.get('model'), scan_id=scan.get('id'), scan_status=scan.get('status'),
                      knowledge_revision=status.get('knowledge_revision'))
        save_report(output, report)
        for case in spec['cases']:
            try:
                response = await client.post('/api/ask', json={'question': case['question']})
                response.raise_for_status()
                row = score_answer(case, response.json(), spec)
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                # Never copy an upstream body, exception, question, or source text into the report.
                row = {'case_id': case['id'], 'status': 'request_failed', 'human_review': None,
                       'message': 'The app request failed or its answer could not be evaluated.'}
            report['results'].append(row)
            save_report(output, report)
            print(case['id'] + ': ' + row['status'], flush=True)
            # A timed-out request may still hold the app lock. Do not queue more model work.
            if row['status'] == 'request_failed' or row.get('scope_matches') is False:
                break
    report['finished_at'] = now()
    save_report(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--set', type=Path, help='Source-checked answer reference set, pinned to a repository and commit.')
    parser.add_argument('--output', type=Path, help='Metrics-only JSON report; required except when inspecting.')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--timeout', type=float, default=240)
    parser.add_argument('--review-report', type=Path, help='Existing report to annotate instead of making live requests.')
    parser.add_argument('--reviews', type=Path, help='Human reviews bound to the report dataset and response hashes.')
    parser.add_argument('--inspect-report', type=Path, help='Print one exact retained answer and its excerpts for review, without saving them.')
    parser.add_argument('--case', help='Case ID to inspect.')
    parser.add_argument('--db', type=Path, default=Path('data/index.sqlite3'), help='Local answer database, opened read-only for inspection.')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 5 <= args.timeout <= 600:
        parser.error('--timeout must be between 5 and 600 seconds.')
    if (sum(bool(v) for v in (args.set, args.review_report, args.inspect_report)) != 1 or
            bool(args.review_report) != bool(args.reviews) or bool(args.inspect_report) != bool(args.case) or
            bool(args.output) == bool(args.inspect_report)):
        parser.error('Use --set and --output; --review-report, --reviews and --output; or --inspect-report and --case.')
    try:
        read = lambda path: json.loads(path.read_text(encoding='utf-8'))
        if args.inspect_report:
            print(json.dumps(inspect_case(read(args.inspect_report), args.case, args.db), indent=2, ensure_ascii=False))
            return 0
        if args.review_report:
            report = apply_reviews(read(args.review_report), read(args.reviews))
            save_report(args.output, report)
        else:
            report = asyncio.run(run_live(read(args.set), args.output, args.url, args.timeout))
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, httpx.HTTPError):
        print('Evaluation could not start or save. Check the set, app scope, connection and output path.')
        return 1
    print('Report:', args.output)
    print('Human review:', report['quality_acceptance'])
    return 0 if report['run_complete'] and all(r['status'] != 'request_failed' for r in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
