"""Full Jira text must survive pagination, indexing, refresh and access checks."""
import asyncio
import copy
from dataclasses import replace
import hashlib

import httpx
import pytest

from pka.config import LIMITS
from pka.connectors import jira
from pka.connectors.base import SourceError
from pka.index import Index

SITE = 'https://fixture.atlassian.net'


def run(work):
    return asyncio.run(work)


def issue(**fields):
    return {'key':'ENG-1', 'fields':{'summary':'Requirements',
        'comment':{'comments':[], 'total':0}, **fields}}


def comment(cid, body=None):
    return {'id':str(cid), 'body':body or f'Discussion {cid}', 'author':{'displayName':'Engineer'}}


def reader(data, pages=(), names=None):
    calls = []
    def handler(request):
        assert request.method == 'GET' and request.url.host == 'fixture.atlassian.net'
        calls.append(request)
        if request.url.path.endswith('/myself'):
            return httpx.Response(200, json={'accountId':'reader'})
        if request.url.path.endswith('/comment'):
            start = int(request.url.params['startAt'])
            response = pages(start) if callable(pages) else pages[start]
            return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)
        assert request.url.path == jira.SEARCH
        assert '*all' in request.url.params['fields'] and request.url.params['expand'] == 'names'
        return httpx.Response(200, json={'issues':[copy.deepcopy(data)], 'isLast':True, 'names':names or {}})
    return jira.JiraSource(SITE, 'reader@example.com', 'fixture', httpx.MockTransport(handler)), calls


def test_comments_beyond_twenty_and_custom_criteria_are_searchable(tmp_path):
    data = issue(description='Requirement detail. '*500, customfield_10091='Accept only greenwidgets',
                 comment={'comments':[comment(0)], 'total':26})
    def pages(start):
        end = min(start+13, 26)
        return {'startAt':start, 'total':26, 'comments':[
            comment(i, 'Late decision requires cobaltqueue' if i == 25 else None) for i in range(start,end)]}
    source, calls = reader(data, pages, {'customfield_10091':'Acceptance criteria'})
    imported = run(source.issues('ENG'))[0]
    blocks = jira.issue_blocks(SITE, imported)
    assert ''.join(b['text'] for b in blocks) == jira.issue_block(SITE, imported)['text']
    assert all(len(b['text']) <= LIMITS.chunk_chars and b['url'] == SITE+'/browse/ENG-1' for b in blocks)
    assert 'Acceptance criteria:\nAccept only greenwidgets' in ''.join(b['text'] for b in blocks)
    index = Index(tmp_path/'index.sqlite3')
    scan = {'id':1, 'repo':'acme/shop','commit':'a'*40,'status':'complete'}
    index.activate(1, [], scan)
    index.replace_source(1, 'jira/', blocks)
    for term in ('greenwidgets', 'cobaltqueue'):
        assert any(term in b['text'] for b in index.search(term, scan))
    assert source.last_coverage['state'] == 'complete'
    assert source.last_coverage['comments'] == 26 and source.last_coverage['custom_text_fields'] == 1
    assert [r.url.params['startAt'] for r in calls if r.url.path.endswith('/comment')] == ['0','13']
    digest = index.source_digests(1, 'jira/')
    assert run(source.check_issues_access('ENG', ['ENG-1'], digest)) == {'checked':1}


@pytest.mark.parametrize('change', ['later_comment', 'custom_criteria', 'description_tail'])
def test_access_rechecks_content_beyond_original_excerpt(change):
    data = issue(description='Long text. '*500, customfield_123='Original criteria',
                 comment={'comments':[], 'total':2})
    comments = [comment(1), comment(2, 'Private later discussion')]
    source, _ = reader(data, lambda start: {'startAt':start,'total':2,'comments':[comments[start]]},
                       {'customfield_123':'Requirements'})
    imported = run(source.issues('ENG'))[0]
    digest = hashlib.sha256('\n'.join(b['text'] for b in jira.issue_blocks(SITE, imported)).encode()).hexdigest()
    if change == 'later_comment': comments[1]['body'] = 'Now redacted'
    elif change == 'custom_criteria': data['fields']['customfield_123'] = 'Changed criteria'
    else: data['fields']['description'] += 'Changed tail'
    with pytest.raises(SourceError, match='no longer fully visible'):
        run(source.check_issues_access('ENG', ['ENG-1'], {'ENG-1':digest}))


@pytest.mark.parametrize('gap', ['comment_limit', 'page_limit', 'empty_page', 'unknown_total', 'text_limit'])
def test_limits_and_unknown_totals_never_claim_complete(monkeypatch, gap):
    monkeypatch.setattr(jira, 'LIMITS', replace(LIMITS, jira_max_comments=1 if gap=='comment_limit' else 1000,
        jira_max_comment_pages=1 if gap in {'page_limit','unknown_total'} else 20,
        jira_max_issue_chars=100 if gap=='text_limit' else 200000))
    data = issue(description='Text '*100, comment={'comments':[], 'total':2})
    def pages(start):
        page = {'startAt':start, 'total':2, 'comments':[] if gap=='empty_page' else [comment(start)]}
        if gap == 'unknown_total': page.pop('total')
        return page
    source, _ = reader(data, pages)
    run(source.issues('ENG'))
    assert source.last_coverage['state'] == ('unknown' if gap=='unknown_total' else 'partial')
    assert source.last_coverage['notes']


@pytest.mark.parametrize('fault', ['repeated_id', 'wrong_offset', 'changed_total', 'forbidden', 'unreadable'])
def test_broken_comment_pages_fail_instead_of_publishing_a_complete_snapshot(fault):
    def pages(start):
        if fault == 'forbidden': return httpx.Response(403)
        if fault == 'unreadable': return {'comments':None}
        return {'startAt':0 if fault=='wrong_offset' else start,
                'total':3 if fault=='changed_total' and start else 2,
                'comments':[comment(0 if fault=='repeated_id' else start)]}
    source, _ = reader(issue(comment={'total':2, 'comments':[]}), pages)
    with pytest.raises(SourceError): run(source.issues('ENG'))


def test_unknown_embedded_total_is_completed_from_comment_endpoint():
    source, calls = reader(issue(comment={'comments':[comment(1)]}),
        {0:{'startAt':0, 'total':1, 'comments':[comment(1)]}})
    run(source.issues('ENG'))
    assert source.last_coverage['state'] == 'complete'
    assert len([r for r in calls if r.url.path.endswith('/comment')]) == 1


def test_complete_embedded_page_needs_no_additional_comment_request():
    source, calls = reader(issue(comment={'comments':[comment(1)], 'total':1}))
    run(source.issues('ENG'))
    assert len(calls) == 1


@pytest.mark.parametrize('key', ['OPS-1', '../ENG-1', 'ENG-1/comment?x=1'])
def test_returned_issue_cannot_widen_project_or_comment_endpoint(key):
    data = issue(); data['key'] = key
    source, calls = reader(data)
    with pytest.raises(SourceError): run(source.issues('ENG'))
    assert len(calls) == 1


def test_rich_requirements_keep_table_boundaries_and_link_targets():
    doc = {'type':'doc','content':[{'type':'tableRow','content':[
        {'type':'tableCell','content':[{'type':'text','text':'Condition'}]},
        {'type':'tableCell','content':[{'type':'text','text':'Expected'}]}]},
        {'type':'text','text':'Contract','marks':[{'type':'link','attrs':{'href':'https://example.com/spec'}}]},
        {'type':'inlineCard','attrs':{'url':'https://example.com/criteria'}}]}
    value = jira.adf_text(doc)
    assert 'Condition\tExpected' in value and 'https://example.com/spec' in value
    assert 'https://example.com/criteria' in value


def test_mcp_pages_all_excerpts_and_counts_issues_separately(monkeypatch):
    from pka import mcp_server
    data = issue(description='Full requirement. '*500, customfield_456='Tail acceptance value')
    source, _ = reader(data, names={'customfield_456':'Acceptance criteria'})
    monkeypatch.setattr(mcp_server, 'jira', lambda: source)
    monkeypatch.setattr(mcp_server, 'JIRA_PROJECT', 'ENG')
    async def scenario():
        begun = await mcp_server.jira_begin_read()
        assert begun['ok'] and begun['data']['issues'] == 1 and begun['data']['blocks'] > 1
        cursor, blocks = 0, []
        while cursor is not None:
            page = (await mcp_server.jira_list_issues(cursor))['data']
            blocks.extend(page['blocks'])
            cursor = page['next_cursor']
        assert len(blocks) == begun['data']['blocks']
        assert 'Tail acceptance value' in ''.join(b['text'] for b in blocks)
    run(scenario())
