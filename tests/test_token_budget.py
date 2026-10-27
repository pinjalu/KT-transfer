"""Offline token counting must preserve evidence and quota enforcement."""
from dataclasses import replace
import json
import math
import pytest
from pka.llm import token_budget
from pka.llm.config import Target
from pka.llm.types import Request


def request():
    return Request([{'role':'system','content':'Use only the supplied evidence.'},
                    {'role':'user','content':'Synthetic code evidence. '*1800}],
                   {'type':'object','properties':{'answer':{'type':'string'}},'required':['answer']},
                   [{'source_id':'S1','path':'app.py','text':'Synthetic code evidence.'}],2000)


def test_offline_o200k_uses_full_request_and_output_without_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('Token counting must be offline'))
    token_budget.encoding.cache_clear()
    tokenizer=token_budget.encoding()
    assert len(tokenizer.encode_ordinary('hello world'))==2
    assert len(tokenizer.encode_ordinary('<|start|>'))>1
    assert tokenizer.encode_ordinary('ગુજરાતી 中文')
    value=request(); before=json.dumps(value.__dict__,sort_keys=True)
    estimate,method=token_budget.estimate(value,Target(provider='groq',model='openai/gpt-oss-120b'))
    assert method=='o200k_with_margin' and estimate>value.max_output_tokens
    smaller,_=token_budget.estimate(replace(value,max_output_tokens=512),Target(provider='groq',model='openai/gpt-oss-120b'))
    assert estimate-smaller==1488
    assert json.dumps(value.__dict__,sort_keys=True)==before


@pytest.mark.parametrize('asset',['missing','corrupt'])
def test_unavailable_vocabulary_uses_original_conservative_estimate(tmp_path,monkeypatch,asset):
    candidate=tmp_path/'vocabulary.gz'
    if asset=='corrupt': candidate.write_bytes(b'Not a vocabulary')
    monkeypatch.setattr(token_budget,'VOCABULARY',candidate)
    token_budget.encoding.cache_clear()
    try:
        value=request()
        count,method=token_budget.estimate(value,Target(provider='groq',model='openai/gpt-oss-20b'))
        assert method=='byte_estimate'
        assert count==math.ceil(len(json.dumps([value.messages,value.schema],ensure_ascii=False).encode())/3)+2000
    finally:
        token_budget.encoding.cache_clear()


@pytest.mark.parametrize('target',[Target(provider='gemini',model='gemini-3.5-flash-lite'),Target(provider='ollama',model='qwen3:1.7b')])
def test_other_providers_do_not_use_gpt_oss_tokenizer(monkeypatch,target):
    monkeypatch.setattr(token_budget,'encoding',lambda:pytest.fail('Wrong model tokenizer'))
    assert token_budget.estimate(request(),target)[1]=='byte_estimate'
