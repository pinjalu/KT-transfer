"""The simple story keeps each supported claim and its source in the right place."""

from pka.overview import TOPICS, section_from, hide_unreliable_purpose, purpose_needs_retry


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


def test_prompt_instructions_and_uncited_claims_never_become_project_story_cards():
    sources = [source('S1', 'Customers enter a parcel number to look up the saved delivery status.')]
    answer = {'statements': [
        {'text': "**Problem:** Who has a need, and what difficulty are they trying to solve? Use the project's documentation when it says this.", 'source_ids': ['S1']},
        {'text': '**Solution:** What does THIS project let that person do to address the problem? Describe the main product, not a list of technologies.', 'source_ids': ['S1']},
        {'text': '**Problem:** Customers need to look up their saved delivery status by parcel number.', 'source_ids': ['S1']},
    ], 'missing_information': ''}
    section = section_from(PURPOSE, sources, answer)
    assert len(section['statements']) == 1
    assert section['story'] == {'problem': 0}
    assert 'writing instructions' in section['missing_information']
    assert purpose_needs_retry(answer, section)


def test_old_saved_overview_hides_prompt_echo_and_unsupported_story_until_rebuilt():
    section = {'key':'purpose', 'statements':[
        {'text':'**Problem:** Who has a need, and what difficulty are they trying to solve?', 'support':'check this'},
        {'text':'**Solution:** Parcel desk lets customers look up delivery status.', 'support':'supported'},
    ], 'story':{'problem':0, 'solution':1}, 'missing_information':''}
    cleaned = hide_unreliable_purpose({'sections':[section]})['sections'][0]
    assert cleaned['story'] == {'solution':0}
    assert len(cleaned['statements']) == 1
    assert 'Update the saved explanation' in cleaned['missing_information']
