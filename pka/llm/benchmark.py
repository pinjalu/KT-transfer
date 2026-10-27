"""Opt-in, pinned-model comparison with built-in synthetic data only.

No CLI text or repository content can be submitted as a synthetic fixture.
Uses existing feature prompts, validators, credential vault and shared quota ledger.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path
from pka import credentials, decisions, jira_tasks, test_plans
from pka.config import data_dir, now
from pka.connectors.base import SourceError
from pka.index import Index
from pka.llm.config import CATALOG, PROMPT_VERSION, Target, digest
from pka.llm.router import Router, using
from pka.llm.types import metadata
from pka.service import ollama_answer
from pka.overview import tidy

CODE = 'def can_refund(days_since_purchase, used):\n    return days_since_purchase <= 30 and not used\n'
README = '# Synthetic Refund Service\nA Python library that checks refund eligibility. A refund is allowed within 30 days only when the item is unused. No web API or database is defined.\n'
def source(path,text,sid='S1',**extra):
    return {'source_id':sid,'path':path,'start':1,'end':len(text.splitlines()),'text':text,**extra}
CASES = [
    ('ask','What conditions allow a refund?',[source('refund.py',CODE)]),
    ('overview','Explain the purpose, code structure and known limitations of this project.',[source('README.md',README),source('refund.py',CODE,'S2')]),
    ('business_logic','Explain the refund eligibility rule, including the boundary and rejected cases.',[source('refund.py',CODE)]),
    ('tests','Suggest 2 tests for can_refund.',[source('refund.py',CODE)]),
    ('jira','',[source('jira/SYN-1','[Description]\nAdd a refund check. Permit refunds when days_since_purchase <= 30 and used is false.\n[Acceptance criteria]\nReject used items and purchases older than 30 days.')]),
    ('slack','',[source('slack/SYN/1','[Message]\nWe agreed to use a 30 day refund window for unused items. Deployment is not approved yet.',message_id='1',message_ts='1',thread_ts='1',partial=False,author='Synthetic reviewer')]),
]


def presented(feature,value,sources,question):
    if feature=='jira': return jira_tasks.checked_points(value,sources)
    if feature=='slack': return {'items':decisions.checked_points(value,sources)}
    if feature=='tests': return test_plans.prepare(value,question,sources)
    statements,checks=tidy(value.get('statements',[]),sources,paths={s['path'] for s in sources})
    return {**value,'statements':statements,'checks':checks}

async def run(router,targets):
    report={'version':1,'started_at':now(),'synthetic_only':True,'prompt_version':PROMPT_VERSION,
            'fixture_hash':digest(CASES),'fallback':False,'results':[],
            'note':'Synthetic schema and evidence checks do not establish production accuracy. Human reviews are pending. No billing or providers are enabled by this command.'}
    async def guard(): pass
    for target in targets:
        for feature,question,sources in CASES:
            started=time.perf_counter()
            row={'feature':feature,'requested':target.model_dump(),'input_hash':digest([feature,question,sources,PROMPT_VERSION]),
                 'human_review':None}
            try:
                with using(router,feature,guard,synthetic=True,override=target):
                    if feature=='jira': value=await jira_tasks.generate(sources,1,1)
                    elif feature=='slack': value=await decisions.generate(sources,1,1)
                    elif feature=='tests': value=await test_plans.generate(question,sources)
                    else: value=await ollama_answer(question,sources)
                row.update(status='validated_response',response=presented(feature,value,sources,question),generation=metadata(value),sources=sources)
            except SourceError as error:
                info=metadata(error) or {}
                row.update(status='unavailable' if not any(a['status']=='failed' for a in info.get('attempts',[])) else 'failed',
                           error=error.code,generation=info,sources=sources)
            row['elapsed_seconds']=round(time.perf_counter()-started,3)
            report['results'].append(row)
    report['finished_at']=now()
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=data_dir()/'index.sqlite3')
    parser.add_argument('--provider',choices=['all','ollama','gemini','groq'],default='all')
    parser.add_argument('--model',help='Pin one allowed model; requires a single provider')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.model and args.provider=='all': parser.error('--model requires one provider')
    index=Index(args.db)
    with credentials.owner_credentials(index.path):
        router=Router(index,Path(index.path).with_suffix('.auth.sqlite3'))
        targets=[Target(provider=m['provider'],model=m['model']) for m in CATALOG]
        targets.append(Target(provider='ollama',model=router.store.config().local_model))
        if args.provider!='all': targets=[t for t in targets if t.provider==args.provider]
        if args.model: targets=[Target(provider=args.provider,model=args.model)]
        report=asyncio.run(run(router,targets))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'cases':len(report['results']),
        'validated':sum(r['status']=='validated_response' for r in report['results']),
        'failed':sum(r['status']=='failed' for r in report['results']),
        'unavailable':sum(r['status']=='unavailable' for r in report['results']),'human_reviewed':0}))

if __name__=='__main__': main()
