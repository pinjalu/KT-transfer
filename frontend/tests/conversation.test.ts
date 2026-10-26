import { describe, expect, it } from 'vitest'
import { conversationContext } from '../src/lib/answer'
import type { Answer, Turn } from '../src/lib/answer'

const turn = (question = 'Explain uploads.'): Turn => ({ question, asked_at: '', failed: null,
  knowledge_revision: 4, answer: { repo: 'acme/app', commit: 'abc', knowledge_revision: 4,
    error: null, statements: [{ text: 'Only PNG is accepted.', source_ids: ['S1'] }],
    missing_information: '' } as Answer })

describe('conversation context', () => {
  it('sends four recent turns without treating previous citations as evidence', () => {
    const history = Array.from({ length: 6 }, (_, n) => turn(`Question ${n}`))
    const context = conversationContext(history, 'acme/app', 4)!
    expect(context.turns.map(t => t.question)).toEqual(['Question 2', 'Question 3', 'Question 4', 'Question 5'])
    expect(context.turns[0]).toEqual({ question: 'Question 2', answer: 'Only PNG is accepted.' })
    expect(context).toMatchObject({ repo: 'acme/app', commit: 'abc', knowledge_revision: 4 })
  })

  it('excludes another project, old source revision, failed replies and incorrect feedback', () => {
    const wrongProject = turn(); wrongProject.answer!.repo = 'acme/other'
    const old = turn(); old.answer!.knowledge_revision = 3
    const failed = turn(); failed.failed = 'Disconnected'
    const error = turn(); error.answer!.error = 'Model unavailable'
    const incorrect = turn(); incorrect.rating = 'incorrect'
    expect(conversationContext([wrongProject, old, failed, error, incorrect], 'acme/app', 4)).toBeUndefined()
  })

  it('caps answer size and keeps only the latest commit', () => {
    const older = turn(); older.answer!.commit = 'old'
    const latest = turn(); latest.answer!.statements[0].text = 'x'.repeat(5000)
    const context = conversationContext([older, latest], 'acme/app', 4)!
    expect(context.turns).toHaveLength(1)
    expect(context.turns[0].answer).toHaveLength(1800)
  })
})
