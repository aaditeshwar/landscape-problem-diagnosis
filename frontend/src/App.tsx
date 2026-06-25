import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { routerBasename } from './appBase'
import { DiagnosisApp } from './routes/DiagnosisApp'
import { DashboardPage } from './routes/DashboardPage'
import { FeedbackPage } from './routes/FeedbackPage'
import { ReviewPage } from './routes/ReviewPage'
import { ReviseCardsPage } from './routes/ReviseCardsPage'
import { SignalEditorPage } from './routes/SignalEditorPage'
import { TriagingPage } from './routes/TriagingPage'
import { VariablesPage } from './routes/VariablesPage'

export default function App() {
  return (
    <BrowserRouter basename={routerBasename()}>
      <Routes>
        <Route path="/" element={<DiagnosisApp />} />
        <Route path="/feedback" element={<FeedbackPage />} />
        <Route path="/revise-cards" element={<ReviseCardsPage />} />
        <Route path="/signals" element={<SignalEditorPage />} />
        <Route path="/triaging" element={<TriagingPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/variables" element={<VariablesPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
