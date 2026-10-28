import asyncio
from copy import deepcopy

import pytest

from pka.index import Index
from pka.llm.config import FEATURES
from pka.llm.router import Router
from pka.llm.types import Request, Reply
from pka.plain_language import GUIDANCE, explain_simply


@pytest.mark.parametrize('repo', ['acme/shop', 'local:D:/Projects/shop', 'zip:D:/managed/source'])
@pytest.mark.parametrize('feature', FEATURES)
def test_every_source_and_feature_receives_simple_style_without_changing_evidence(tmp_path, repo, feature):
    index = Index(tmp_path/'index.sqlite3')
    index.configure({'repo':repo, 'branch':'main'})
    seen = []
    class Adapter:
        async def generate(self, request, target, key='', timeout=180):
            seen.append(request)
            return Reply('{"text":"A short explanation."}')
    router = Router(index, adapters={'ollama':Adapter()}, key_reader=lambda provider:'')
    request = Request(messages=[{'role':'system','content':'Cite the exact source IDs. Return JSON only.'},
        {'role':'user','content':'Explain the supplied files.'}], schema={'type':'object'},
        sources=[{'path':'app.py', 'text':'def login(): return True', 'source_id':'S1'}])
    original = deepcopy(request)
    async def guard():
        pass
    result = asyncio.run(router.generate(request, lambda value:value, feature, guard))
    assert result['text'] == 'A short explanation.'
    assert len(seen) == 1 and GUIDANCE in seen[0].messages[0]['content']
    assert seen[0].sources == original.sources and seen[0].schema == original.schema
    assert seen[0].messages[1] == original.messages[1]
    assert request == original


def test_standalone_generation_gets_the_same_style(monkeypatch):
    from pka.llm import router
    seen = []
    async def generate(self, request, target):
        seen.append(request)
        return Reply('{"text":"Simple words."}')
    monkeypatch.setattr(router.Ollama, 'generate', generate)
    request = Request([{'role':'user','content':'Explain this.'}], {}, [])
    result = asyncio.run(router.generate(request, lambda value:value))
    assert result['text'] == 'Simple words.'
    assert seen[0].messages[0] == {'role':'system', 'content':GUIDANCE}
    assert request.messages == [{'role':'user','content':'Explain this.'}]


def test_style_does_not_accumulate_on_retries():
    request = Request([{'role':'system','content':'Keep the output schema.'}], {}, [])
    prepared = explain_simply(explain_simply(request))
    assert prepared.messages[0]['content'].count(GUIDANCE) == 1
