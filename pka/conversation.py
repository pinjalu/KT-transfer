"""Bounded browser-session context, used to interpret questions, never as evidence."""
import re

from pydantic import BaseModel, ConfigDict, Field


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=600)
    answer: str = Field(max_length=1800)


class Conversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    repo: str = Field(min_length=1, max_length=1200)
    commit: str = Field(min_length=1, max_length=200)
    knowledge_revision: int = Field(ge=0, strict=True)
    turns: list[ConversationTurn] = Field(max_length=4)

    def current_turns(self, scan, revision):
        if (self.repo, self.commit, self.knowledge_revision) != (
                scan['repo'], scan['commit'], revision):
            return []
        return [turn.model_dump() for turn in self.turns if turn.question.strip()]


def followup_query(question, history):
    """Expand referential questions only; independent topics keep their own search."""
    if not history or not re.search(
            r'\b(?:it|its|they|them|their|that|those|these|same|above|previous|earlier)\b|'
            r'\b(?:first|second|third|last|next)\s+(?:step|point|one|part)\b|'
            r'\bthis\s+(?:function|component|endpoint|model|setting|file|ticket|decision|mean|work)\b|'
            r'\bthis\s*[?!.]*$|'
            r'^\s*(?:and\b|also\b|what about\b|why\s*[?!.]*$|tell me more\b|explain more\b|elaborate\b|continue\b)',
            question, re.I):
        return None
    previous = history[-1]
    return (question + '\nPrevious question: ' + previous['question'] +
            '\nPrevious reply (may be incorrect): ' + previous['answer'][:800])
