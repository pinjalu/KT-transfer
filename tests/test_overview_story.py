"""The simple story keeps each supported claim and its source in the right place."""

from pka.overview import TOPICS, section_from


PURPOSE = next(topic for topic in TOPICS if topic['key'] == 'purpose')


def source(source_id, text):
    return {'source_id': source_id, 'path': 'README.md', 'start': 1, 'end': 1,
            'url': None, 'text': text}


def test_story_maps_problem_solution_and_journey_without_losing_citations():
    sources = [source('S1', 'Parcel desk lets a customer track a parcel number.'),
               source('S2', 'The browser sends a number to /track and displays the status.')]
    answer = {'statements': [
        {'text': '**Problem:** Customers need to know where a parcel is.', 'source_ids': ['S1']},
        {'text': '**Solution:** Parcel desk lets customers track a parcel number.', 'source_ids': ['S1']},
        {'text': '**You do (illustrative):** A customer enters a sample parcel number; this was not run.', 'source_ids': ['S2']},
        {'text': '**Project does:** The browser sends the number to /track.', 'source_ids': ['S2']},
        {'text': '**You get:** The browser displays the saved parcel status.', 'source_ids': ['S2']},
    ], 'missing_information': ''}
    section = section_from(PURPOSE, sources, answer, measure=False)
    assert section['story'] == {'problem': 0, 'solution': 1, 'input': 2,
                                'process': 3, 'output': 4}
    assert section['statements'][section['story']['output']]['source_ids'] == ['S2']
    assert section['sources'][1]['text'] == sources[1]['text']


def test_missing_story_parts_are_not_filled_from_an_unrelated_statement():
    sources = [source('S1', 'The library offers a calculate function.')]
    answer = {'statements': [
        {'text': '**Solution:** The library offers a calculate function.', 'source_ids': ['S1']},
        {'text': 'The command syntax is unknown.', 'source_ids': ['S1']},
    ], 'missing_information': 'The files do not say who uses this or what output they see.'}
    section = section_from(PURPOSE, sources, answer, measure=False)
    assert section['story'] == {'solution': 0}
    assert 'output' not in section['story']
    assert 'who uses this' in section['missing_information']
