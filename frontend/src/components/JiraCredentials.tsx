import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, post } from '../lib/api'
import { Button } from './ui'

const FIELDS = [
  { key: 'JIRA_SITE', label: 'Jira site URL', type: 'url', placeholder: 'https://yourcompany.atlassian.net' },
  { key: 'JIRA_EMAIL', label: 'Atlassian email', type: 'email', placeholder: 'you@company.com' },
  { key: 'JIRA_API_TOKEN', label: 'Jira API token', type: 'password', placeholder: 'Enter a new API token' },
] as const

export function JiraCredentials({ disabled, onSaved }: { disabled: boolean; onSaved: () => void }) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const changed = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value.trim()])
    .filter(([, value]) => value))

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!Object.keys(changed).length || saving || disabled) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await post('/api/credentials', { values: changed })
      setValues({})
      setOpen(false)
      setMessage('Jira credentials saved. Checking project access again.')
      onSaved()
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not save the Jira credentials.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="conn-credentials">
      {!open ? (
        <Button disabled={disabled} onClick={() => { setOpen(true); setMessage(''); setError('') }}>
          Update Jira credentials
        </Button>
      ) : (
        <form aria-label="Jira credentials" onSubmit={save} autoComplete="off">
          <p id="jira-credential-help" className="conn-credential-help">
            Leave a field blank to keep its saved value. Use the email of the account that created the token.
            Credentials are stored only in this local app.
          </p>
          <div className="conn-credential-fields">
            {FIELDS.map((field) => (
              <label className="field" key={field.key}>
                <span className="field-label">{field.label}</span>
                <input type={field.type} value={values[field.key] ?? ''} placeholder={field.placeholder}
                       autoComplete={field.type === 'password' ? 'new-password' : 'off'}
                       aria-describedby="jira-credential-help" maxLength={500} disabled={disabled || saving}
                       onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))} />
              </label>
            ))}
          </div>
          <div className="conn-credential-actions">
            <Button type="submit" kind="primary" disabled={disabled || saving || !Object.keys(changed).length}>
              {saving ? 'Saving credentials…' : 'Save Jira credentials'}
            </Button>
            <Button disabled={saving} onClick={() => { setValues({}); setOpen(false); setError('') }}>Cancel</Button>
          </div>
        </form>
      )}
      {message && <p role="status" className="conn-credential-help">{message}</p>}
      {error && <p role="alert" className="conn-credential-error">{error}</p>}
    </div>
  )
}
