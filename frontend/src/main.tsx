import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Pending } from './pages/Pending'
import { Home } from './pages/Home'
import { Connections } from './pages/Connections'
import { Ask } from './pages/Ask'
import { Overview } from './pages/Overview'
import { Architecture } from './pages/Architecture'
import { JiraTasks } from './pages/JiraTasks'
import { TeamDecisions } from './pages/TeamDecisions'
import { AuthGate } from './components/AuthGate'
import { Account } from './pages/Account'
import './tokens.css'
import './shell.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthGate><BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route path="account" element={<Account />} />
          <Route index element={<Home />} />
          <Route path="connections" element={<Connections />} />
          <Route path="overview" element={<Overview />} />
          <Route path="ask" element={<Ask />} />
          <Route path="features" element={
            <Pending step="Step 6" title="Feature explorer"
              lead="Waiting on step 5, the feature derivation in pka/features.py."
              items={[
                'Overview, Flow, APIs and data, Tests and Known problems',
                'A worked journey per feature, derived from routes and imports',
                'Related components, each linking to the line behind it',
              ]} />} />
          <Route path="jira" element={<JiraTasks />} />
          <Route path="decisions" element={<TeamDecisions />} />
          <Route path="architecture" element={<Architecture />} />
          <Route path="troubleshooting" element={
            <Pending step="Step 10" title="Troubleshooting"
              lead="Not started anywhere in the codebase. Phase 08 is the thinnest phase in the plan."
              items={[
                'A symptom in, ranked possible causes out, each marked as needing checking',
                'Where to check, pointing at real files, tables and services',
                'Relevant tests, separated into existing and suggested',
              ]} />} />
          <Route path="settings" element={
            <Pending step="Step 12" title="Settings"
              lead="Use your username in the top bar for password and session controls. Model and refresh settings remain environment variables."
              items={[
                'General, Model, Refresh and Activity, all backed by what is already stored',
                'Team and access stays empty until the multi-user gate in ROADMAP.md is passed',
                'Source permissions reflecting the allowlists already enforced',
              ]} />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter></AuthGate>
  </StrictMode>,
)
