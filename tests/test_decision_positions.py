"""Task 15.3: compare recorded positions without inventing consent or a winner."""
from copy import deepcopy

import pytest

from pka import decisions


def source(text, number=1, **kwargs):
    return {'source_id': f'S{number}', 'path': 'slack/team', 'start': number, 'end': number,
            'text': text, 'message_id': f'C1:{number}', 'partial': False, **kwargs}


def point(text, kind, sources, quotes=None):
    return decisions.checked_points({'items': [{'text': text, 'kind': kind,
        'evidence_ids': [s['source_id'] for s in sources],
        'quotes': quotes or [s['text'] for s in sources]}]}, sources)[0]


def test_separate_suggestion_and_agreement_within_one_message():
    s = source('I propose Redis for the cache.\nWe decided to use PostgreSQL for receipts.')
    assert decisions.recorded_kind(s) == 'mixed'
    review = decisions.review([s])
    assert [p['kind'] for p in review['positions']] == ['proposal', 'decision']
    p = point('We agreed to use Redis.', 'decision', [s], ['I propose Redis for the cache.'])
    assert p['kind'] == 'proposal' and p['text'] == 'I propose Redis for the cache.'
    p = point('PostgreSQL handles receipts.', 'decision', [s], ['We decided to use PostgreSQL for receipts.'])
    assert p['kind'] == 'decision' and p['source_wording']


@pytest.mark.parametrize('text', [
    'We have not decided to use Redis.',
    'We decided to use Redis if the benchmark passes.',
    'Decision: Use Redis. Approval is pending.',
    'Decision: Use Redis. No final agreement has been reached.',
    'Agreed.',
    '> Decision: Use Redis for the cache.',
    '```\nDecision: Use Redis for the cache.\n```',
])
def test_qualifiers_vague_assent_and_quoted_content_do_not_establish_agreement(text):
    assert decisions.recorded_kind(source(text)) == 'unclear'


def test_truncated_quote_cannot_erase_negation_or_condition():
    s = source('We have not decided to use Redis.')
    assert point('We decided to use Redis.', 'decision', [s], ['decided to use Redis'])['kind'] == 'unclear'
    s = source('We decided to use Redis if the benchmark passes.')
    assert point('We decided to use Redis.', 'decision', [s], ['We decided to use Redis'])['kind'] == 'unclear'


def test_two_proposals_are_alternatives_not_conflicting_agreements():
    sources = [source('I propose setting CONFIDENCE_THRESHOLD to 0.60.'),
               source('I propose setting CONFIDENCE_THRESHOLD to 0.45.', 2)]
    compared = decisions.review(sources)['comparisons']
    assert len(compared) == 1 and compared[0]['kind'] == 'alternatives'
    assert point('There is a conflict.', 'conflict', sources)['kind'] == 'proposal'


def test_proposal_and_recorded_adoption_remain_separate_and_do_not_prove_implementation():
    sources = [source('I propose setting CONFIDENCE_THRESHOLD to 0.60.'),
               source('Final decision: keep CONFIDENCE_THRESHOLD at 0.45.', 2)]
    review = decisions.review(sources)
    assert review['comparisons'][0]['kind'] == 'alternatives'
    assert [p['kind'] for p in review['positions']] == ['proposal', 'decision']
    assert 'implementation' in review['positions'][1]['reason']
    assert 'winner' not in review and 'final' not in review


def test_differing_agreements_across_model_batches_keep_both_positions_and_no_latest_winner():
    sources = [source('Decision: set CONFIDENCE_THRESHOLD to 0.45.', message_ts='100.0'),
               source('Unrelated notes. ' * 700, 2),
               source('Decision: set CONFIDENCE_THRESHOLD to 0.60.', 3, message_ts='200.0')]
    assert len(decisions.batches(sources)) > 1
    review = decisions.review(sources)
    comparison = review['comparisons'][0]
    assert comparison['kind'] == 'conflict' and len(comparison['position_ids']) == 2
    assert 'no winner' in comparison['reason']
    assert len(review['positions']) == 2
    checked = point('The new value won.', 'conflict', [sources[0], sources[2]])
    assert checked['kind'] == 'conflict' and 'The new value won' not in checked['text']
    assert '0.45' in checked['text'] and '0.60' in checked['text']


@pytest.mark.parametrize('second', [
    'Decision: use PostgreSQL for receipts.',
    'Decision: use Redis for the cache.',
    'I propose Memcached for the cache.',
])
def test_different_message_text_is_not_enough_for_a_conflict(second):
    sources = [source('Decision: use Redis for the cache.'), source(second, 2)]
    assert point('The team disagrees.', 'conflict', sources)['kind'] != 'conflict'


def test_explicit_opposed_product_choices_are_compared():
    review = decisions.review([source('We decided to use Redis.'), source('We decided not to use Redis.', 2)])
    assert review['comparisons'][0]['kind'] == 'conflict'


def test_scopes_equal_numbers_partial_messages_and_duplicate_message_ids_do_not_create_conflicts():
    cases = [
        [source('Decision: set CONFIDENCE_THRESHOLD to 0.45 in production.'), source('Decision: set CONFIDENCE_THRESHOLD to 0.60 in staging.', 2)],
        [source('Decision: set CONFIDENCE_THRESHOLD to 0.45.'), source('Decision: set CONFIDENCE_THRESHOLD to 0.450.', 2)],
        [source('Decision: set CONFIDENCE_THRESHOLD to 0.45.'), source('Decision: set CONFIDENCE_THRESHOLD to 0.60.', 2, partial=True)],
        [source('Decision: set CONFIDENCE_THRESHOLD to 0.45.'), source('Decision: set CONFIDENCE_THRESHOLD to 0.60.', 2, message_id='C1:1')],
    ]
    for sources in cases:
        assert decisions.review(sources)['comparisons'] == []


def test_a_different_value_in_an_unquoted_sentence_cannot_support_a_conflict():
    sources = [source('Decision: set CONFIDENCE_THRESHOLD to 0.45.\nThe log includes this ticket.'),
               source('Decision: set CONFIDENCE_THRESHOLD to 0.60.\nThe log mentions a timeout.', 2)]
    p = point('Conflicting thresholds.', 'conflict', sources,
              ['The log includes this ticket.', 'The log mentions a timeout.'])
    assert p['kind'] == 'unclear'


def test_old_cached_conflicts_are_rechecked_without_changing_stored_payload():
    sources = [source('Decision: use Redis for the cache.'), source('Decision: use PostgreSQL for receipts.', 2)]
    saved = {'items': [{'text': 'These decisions conflict.', 'kind': 'conflict', 'source_ids': ['S1', 'S2'],
                       'quotes': [{'source_id': s['source_id'], 'text': s['text']} for s in sources], 'source_wording': False}]}
    original = deepcopy(saved)
    upgraded = decisions.recheck_summary(saved, sources)
    assert saved == original and upgraded['labels_rechecked']
    assert upgraded['items'][0]['kind'] != 'conflict'
    assert upgraded['classification_version'] == decisions.CLASSIFICATION_VERSION


def test_demo_handoff_decision_is_not_downgraded_by_pending_test_execution():
    s = source('For SCRUM-23, the demo test decision is to keep CONFIDENCE_THRESHOLD at 0.45.\nSynthetic decision record; validation is pending.')
    assert decisions.recorded_kind(s) == 'decision'


@pytest.mark.parametrize('text', [
    'No-answer wording can still suggest handoff.',
    'An already-open handoff suppresses a new suggestion.',
    '[Demo | threshold proposal v1]',
])
def test_mentions_of_suggestions_and_titles_are_not_treated_as_new_proposals(text):
    assert decisions.positions([source(text)]) == []


def test_explicit_thread_correction_preserves_proposal_agreement_and_withdrawal():
    sources = [source('[Demo | proposal v1]\nFor QA-23, I\u2019m considering raising the handoff threshold to 0.60 for the next test run.',
                      message_ts='100.0', thread_ts='100.0'),
               source('[Demo | FINAL correction v2] Do not adopt the 0.60 proposal above. '
                      'The final decision for QA-23 is to retain the repository default 0.45. '
                      'This replaces proposal v1.', 2, message_ts='200.0', thread_ts='100.0')]
    review = decisions.review(sources)
    assert len(review['comparisons']) == 1
    update = review['comparisons'][0]
    assert update['kind'] == 'recorded_update'
    cited = [p for p in review['positions'] if p['id'] in update['position_ids']]
    assert {p['kind'] for p in cited} == {'proposal', 'decision', 'historical'}
    assert '0.60' in cited[0]['text'] and any('0.45' in p['text'] and p['kind'] == 'decision' for p in cited)
    for altered in ({'thread_ts': '999.0'}, {'thread_ts': None}, {'partial': True}, {'path': 'slack/other'}):
        assert decisions.review([sources[0], {**sources[1], **altered}])['comparisons'] == []
    assert decisions.review([sources[0], {**sources[1], 'text': 'The final decision for QA-23 is to retain 0.45.'}])['comparisons'] == []
