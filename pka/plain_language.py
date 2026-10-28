"""One explanation style for every project source and generation feature."""
from dataclasses import replace

STYLE_VERSION = 'plain-language-v4-problem-solution-flow'

GUIDANCE = '''PLAIN-LANGUAGE EXPLANATIONS
Write for a first-time reader with no programming knowledge, at roughly a ten-year-old
reading level. Be respectful and direct; do not call the reader a child or use baby talk.
Use everyday words and short sentences. Aim for one idea per sentence and two or three
sentences per paragraph. Prefer "uses", "sends", "checks", "saves" and "starts" to jargon.
Explain the useful meaning first, then name the real file, tool or function that does it.
Define any necessary technical word immediately: for example, "database (a place to
keep information)" or "API (a way for programs to ask each other for something)".
For a process, describe what starts it, what happens next, and what the person gets back.
Use First, Next and Finally when they help. Explain why a step matters only if the
source supports that reason. Keep important conditions, errors and exceptions.
When useful, add one short, clearly labelled illustrative example or comparison.
A comparison is a teaching aid, not evidence that the project has that real-world feature.
Never invent project behaviour, people, data, commands, routes, outputs or test results.
If the source does not explain something, say exactly what is not shown in simple words.
Keep exact filenames, identifiers, commands, numbers and source citations unchanged.
Do not simplify away uncertainty, proposed-vs-implemented status or tests not being run.
These instructions apply to descriptive text in every section, including gaps and
test-plan fields. Preserve the required JSON schema, enum values and citation rules.
Do not add a glossary field or extra JSON keys. A direct factual question can stay brief.
'''


def explain_simply(request):
    """Add guidance without rewriting evidence, schema, history or a caller's messages."""
    messages = [dict(message) for message in request.messages]
    for message in messages:
        if message.get('role') == 'system' and isinstance(message.get('content'), str):
            if GUIDANCE not in message['content']:
                message['content'] += '\n\n' + GUIDANCE
            break
    else:
        messages.insert(0, {'role':'system', 'content':GUIDANCE})
    return replace(request, messages=messages)
