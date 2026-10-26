"""Compare lexical and hybrid evidence coverage on a disposable copy of a saved index."""
import argparse
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pka import embed
from pka.answer_evaluation import overlaps, validate_spec
from pka.index import Index
from pka.service import Service, focused_question


async def run(args):
    spec = validate_spec(json.loads(Path(args.cases).read_text(encoding='utf-8')))
    os.environ['PKA_EMBED_MODEL'] = args.model
    with tempfile.TemporaryDirectory(prefix='pka-retrieval-') as folder:
        copy = Path(folder) / 'index.sqlite3'
        with closing(sqlite3.connect(Path(args.index).resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(copy)) as target:
                source.backup(target)
        index = Index(copy)
        scan = index.active_scan()
        if not scan or (scan['repo'], scan['commit']) != (spec['repo'], spec['commit']):
            raise ValueError('Evaluation repository and commit must match the saved snapshot.')
        # Do not inherit vectors made by another model or preprocessing version.
        index.prepare_vectors(scan['id'], embed.signature())
        cases = [case for case in spec['cases'] if case.get('facts')]
        def retrieve(case, vectors=None):
            detailed = not focused_question(case['question'])
            return index.search(case['question'], scan, query_vectors=vectors,
                max_sources=8 if detailed else 5, context_chars=14000 if detailed else 7200)
        baseline = [retrieve(case) for case in cases]
        print('Preparing disposable semantic index:', len(index.unembedded(scan['id'])), 'chunks', flush=True)
        await Service(index).embed_snapshot(scan['id'])
        vectors = await embed.vectors(embed.query_texts([case['question'] for case in cases]))
        if not vectors or not index.embedded(scan['id']):
            raise RuntimeError('Embedding model unavailable; no comparison was made.')
        rows = []
        for case, lexical, vector in zip(cases, baseline, vectors):
            hybrid = retrieve(case, [vector])
            hit = lambda sources, fact: any(overlaps(s, ref) for s in sources for ref in fact['references'])
            rows.append({'case': case['id'], 'facts': len(case['facts']),
                'lexical_facts_found': sum(hit(lexical, f) for f in case['facts']),
                'hybrid_facts_found': sum(hit(hybrid, f) for f in case['facts'])})
        report = {'repo': scan['repo'], 'commit': scan['commit'], 'embedding_model': embed.model(),
            'note': 'Reference-excerpt coverage only; not generated-answer correctness.', 'results': rows,
            'totals': {key: sum(row[key] for row in rows) for key in
                       ('facts', 'lexical_facts_found', 'hybrid_facts_found')}}
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report['totals']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True)
    parser.add_argument('--cases', required=True)
    parser.add_argument('--model', default='nomic-embed-text')
    parser.add_argument('--output', required=True)
    asyncio.run(run(parser.parse_args()))
