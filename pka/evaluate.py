"""Measure retrieval against a labelled question set.

The point of this module is to make a change to retrieval arguable. Before it existed there
were five answer records in the whole log, so no change to chunking, ranking or embeddings
could be shown to have helped or hurt.

Retrieval is measured without calling the model at all. That is deliberate on two counts: it
is deterministic, so the same index gives the same number every run, and it takes seconds
rather than the minute and a half a generated answer costs on a CPU. If the right file never
comes back, no model can rescue the answer, so this is the number that matters first.

    python -m pka.evaluate                      measure the active scan
    python -m pka.evaluate --compare            word matching alone, then with embeddings
    python -m pka.evaluate --band paraphrase    only the band that tests meaning
    python -m pka.evaluate --failures           list every miss with what came back instead
    python -m pka.evaluate --save before.json   write the run, to diff against a later one
    python -m pka.evaluate --diff before.json   compare this run against a saved one
"""
import argparse
import asyncio
import json
from pathlib import Path

from pka import embed
from pka import index as index_module
from pka.config import ROOT
from pka.index import Index

DEFAULT_SET = ROOT / 'evals/retrieval.json'
DEFAULT_DB = ROOT / 'data/index.sqlite3'


def hit_rank(expect: list[str], got: list[str]) -> int:
    """1-based rank of the first returned path that matches an expected one, or 0 for a miss.

    Matching is by suffix so the question set can name `core/database.py` without repeating
    the `src/mcp_project/` prefix that every path in this repository carries.

    A question that expects nothing is scored the other way up: coming back empty is the right
    answer and counts as rank 1, and returning anything at all is the failure. Finding things
    is only half of what this promises, and a set that only measured retrieval would score a
    system that answers everything confidently as perfect.
    """
    if not expect:
        return 0 if got else 1
    for i, path in enumerate(got, 1):
        if any(path.endswith(want) for want in expect):
            return i
    return 0


def measure(index: Index, scan: dict, questions: list[dict], vectors: bool) -> dict:
    """Run every question and score where the expected file landed."""
    rows = []
    for q in questions:
        found = None
        if vectors:
            # One vector per question. If the model is unreachable this returns nothing and the
            # run falls back to word matching, which is what the application does too.
            try:
                found = asyncio.run(embed.vectors([q['ask']]))
            except Exception:
                found = None
        info = {}
        sources = index.search(q['ask'], scan, info, query_vectors=found)
        got = [s['path'] for s in sources]
        rank = hit_rank(q['expect'], got)
        rows.append({**q, 'rank': rank, 'got': got,
                     'terms': info.get('terms', []), 'unknown': info.get('unknown', [])})
    return {'rows': rows, **totals(rows)}


def totals(rows: list[dict]) -> dict:
    """Hit rates and mean reciprocal rank, overall and per band."""
    def score(subset):
        n = len(subset) or 1
        return {'n': len(subset),
                'hit@1': round(sum(1 for r in subset if r['rank'] == 1) / n, 3),
                'hit@3': round(sum(1 for r in subset if 0 < r['rank'] <= 3) / n, 3),
                'hit@5': round(sum(1 for r in subset if 0 < r['rank'] <= 5) / n, 3),
                'mrr': round(sum(1 / r['rank'] for r in subset if r['rank']) / n, 3)}
    bands = sorted({r['band'] for r in rows})
    return {'overall': score(rows),
            'bands': {b: score([r for r in rows if r['band'] == b]) for b in bands}}


def line(label: str, s: dict) -> str:
    return (f"  {label:<12} n={s['n']:<3} hit@1={s['hit@1']:<6} "
            f"hit@3={s['hit@3']:<6} hit@5={s['hit@5']:<6} mrr={s['mrr']}")


def report(name: str, result: dict) -> None:
    print(f'\n{name}')
    print(line('overall', result['overall']))
    for band, s in result['bands'].items():
        print(line(band, s))


def failures(result: dict) -> None:
    misses = [r for r in result['rows'] if not r['rank']]
    if not misses:
        print('\nNo misses. Every question surfaced an expected file inside the returned set.')
        return
    print(f'\n{len(misses)} miss(es):')
    for r in misses:
        print(f"\n  {r['id']} [{r['band']}] {r['ask']}")
        print(f"    wanted  : {', '.join(r['expect'])}")
        print(f"    got     : {', '.join(r['got']) or 'nothing at all'}")
        print(f"    searched: {', '.join(r['terms']) or 'no usable terms'}"
              + (f"  (unknown: {', '.join(r['unknown'])})" if r['unknown'] else ''))


def diff(old: dict, new: dict) -> None:
    """What moved between two runs, question by question. Regressions first."""
    was = {r['id']: r['rank'] for r in old['rows']}
    moved = []
    for r in new['rows']:
        before = was.get(r['id'])
        if before is None or before == r['rank']:
            continue
        # A miss is rank 0, which sorts as better than rank 1 without this.
        kind = 'gained' if (r['rank'] and (not before or r['rank'] < before)) else 'lost'
        moved.append((kind, r['id'], before, r['rank'], r['ask']))
    print('\nAgainst the saved run:')
    for s, label in (('overall', 'overall'), *[(b, b) for b in new['bands']]):
        a = old['bands'].get(s, old['overall']) if s != 'overall' else old['overall']
        b = new['bands'].get(s, new['overall']) if s != 'overall' else new['overall']
        delta = round(b['mrr'] - a['mrr'], 3)
        sign = '+' if delta > 0 else ''
        print(f"  {label:<12} mrr {a['mrr']} -> {b['mrr']}  ({sign}{delta})")
    if not moved:
        print('\n  No individual question changed rank.')
        return
    for kind in ('lost', 'gained'):
        for k, qid, before, after, ask in [m for m in moved if m[0] == kind]:
            shown = lambda r: ('miss' if not r else f'#{r}')
            print(f"  {k:<7} {qid}  {shown(before)} -> {shown(after)}   {ask}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='python -m pka.evaluate',
                                description='Measure retrieval against a labelled question set.')
    p.add_argument('--set', default=str(DEFAULT_SET), help='Question set JSON. Default evals/retrieval.json.')
    p.add_argument('--db', default=str(DEFAULT_DB), help='Index database. Default data/index.sqlite3.')
    p.add_argument('--band', default='', help='Only one band: lexical, paraphrase or conceptual.')
    p.add_argument('--embed', action='store_true', help='Add meaning-based candidates. Needs PKA_EMBED_MODEL.')
    p.add_argument('--compare', action='store_true', help='Run word matching alone, then with embeddings, and show both.')
    p.add_argument('--sweep', action='store_true', help='Try a range of semantic weights and print the score at each.')
    p.add_argument('--sweep-reject', action='store_true', help='Try a range of off-topic strictness settings.')
    p.add_argument('--failures', action='store_true', help='List every miss with what came back instead.')
    p.add_argument('--save', default='', help='Write this run to a file.')
    p.add_argument('--diff', default='', help='Compare this run against a saved one.')
    args = p.parse_args(argv)

    spec = json.loads(Path(args.set).read_text(encoding='utf-8'))
    questions = [q for q in spec['questions'] if not args.band or q['band'] == args.band]
    if not questions:
        print(f'No questions in band {args.band!r}.')
        return 1

    index = Index(args.db)
    scan = index.active_scan()
    if not scan:
        print(f'No completed scan in {args.db}. Run a scan before measuring.')
        return 1
    print(f"Scan {scan['id']}  {scan['repo']}  {scan['commit'][:8]}  {len(questions)} questions")

    embedded = index.embedded(scan['id'])
    if (args.embed or args.compare) and not embedded:
        print('\nThis scan has no stored vectors, so there is nothing to compare word matching against.\n'
              'Set PKA_EMBED_MODEL to an installed embedding model and scan again, then re-run.')
        if args.compare:
            args.compare = False
        else:
            return 1

    if args.sweep:
        if not embedded:
            print('\nNothing to sweep: this scan has no vectors.')
            return 1
        # Weight 0 is word matching alone, so the sweep carries its own baseline and the
        # comparison is against the same questions and the same index.
        print('\nSemantic weight sweep. Weight 0 is word matching alone.')
        print(f"  {'weight':<8} {'overall':<8} {'lexical':<8} {'paraphr':<8} {'concept':<8}")
        for w in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 5.0):
            index_module.SEMANTIC_WEIGHT = w
            r = measure(index, scan, questions, vectors=w > 0)
            b = r['bands']
            cell = lambda k: f"{b[k]['mrr']:<8}" if k in b else f"{'-':<8}"
            print(f"  {w:<8} {r['overall']['mrr']:<8} {cell('lexical')}{cell('paraphrase')}{cell('conceptual')}")
        print('\nHigher is better. The column that matters is paraphrase, because that is the\n'
              'band word matching cannot do. Pick the weight that lifts it without costing lexical.')
        return 0

    if args.sweep_reject:
        if not embedded:
            print('\nNothing to sweep: this scan has no vectors.')
            return 1
        # The trade is visible only with both kinds of question in the set: strictness that
        # refuses every off-topic question is worthless if it also refuses real ones.
        print('\nOff-topic strictness. 0 refuses whenever meaning-based retrieval found nothing;')
        print('higher values additionally require that much of the question be words the project never uses.')
        print(f"  {'ratio':<8} {'answerable':<12} {'reject':<9} {'overall':<8}")
        for r in (0.0, 0.25, 0.5, 0.75, 1.0):
            index_module.OFF_TOPIC_UNKNOWN_RATIO = r
            res = measure(index, scan, questions, vectors=True)
            real = [x for x in res['rows'] if x['band'] != 'reject']
            rej = [x for x in res['rows'] if x['band'] == 'reject']
            print(f"  {r:<8} {totals(real)['overall']['mrr']:<12} "
                  f"{(totals(rej)['overall']['mrr'] if rej else '-'):<9} {res['overall']['mrr']:<8}")
        print('\nanswerable is every band except reject, so it must not fall as reject rises.')
        return 0

    if args.compare:
        base = measure(index, scan, questions, vectors=False)
        with_vec = measure(index, scan, questions, vectors=True)
        report('Word matching only', base)
        report('Word matching plus embeddings', with_vec)
        diff(base, with_vec)
        result = with_vec
    else:
        result = measure(index, scan, questions, vectors=args.embed and embedded)
        report('Embeddings on' if (args.embed and embedded) else 'Word matching only', result)

    if args.failures:
        failures(result)
    if args.diff:
        diff(json.loads(Path(args.diff).read_text(encoding='utf-8')), result)
    if args.save:
        Path(args.save).write_text(json.dumps(result, indent=1), encoding='utf-8')
        print(f'\nSaved to {args.save}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
