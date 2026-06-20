import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { DiagnosisApp } from './routes/DiagnosisApp'
import { FeedbackPage } from './routes/FeedbackPage'
import { ReviseCardsPage } from './routes/ReviseCardsPage'
import { SignalEditorPage } from './routes/SignalEditorPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DiagnosisApp />} />
        <Route path="/feedback" element={<FeedbackPage />} />
        <Route path="/revise-cards" element={<ReviseCardsPage />} />
        <Route path="/signals" element={<SignalEditorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
