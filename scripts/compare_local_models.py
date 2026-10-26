"""Compare installed Ollama models on identical evidence; no downloads or cloud calls."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pka.service import ollama_answer


async def run(args):
    cases = json.loads(Path(args.cases).read_text(encoding='utf-8'))['cases']
    report = {'note': 'Same evidence for each model; generation-only benchmark. Manual review required.', 'results': []}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    for model in args.models:
        os.environ['OLLAMA_MODEL'] = model
        for case in cases:
            sources = [{**s, 'source_id': f'S{i+1}', 'start': 1,
                        'end': len(s['text'].splitlines())} for i, s in enumerate(case['sources'])]
            started = time.perf_counter()
            row = {'model': model, 'case': case['id'], 'expected': case['expected']}
            try:
                row['answer'] = await ollama_answer(case['question'], sources, history=case.get('history', []))
            except Exception as exc:
                row['error'] = str(exc)
            row['seconds'] = round(time.perf_counter() - started, 2)
            report['results'].append(row)
            target.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(model, case['id'], 'error' if row.get('error') else 'generated', row['seconds'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--cases', default='evals/local_answer_quality.json')
    parser.add_argument('--output', required=True)
    asyncio.run(run(parser.parse_args()))
