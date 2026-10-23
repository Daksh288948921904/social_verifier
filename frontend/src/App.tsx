import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { StartSessionPage } from './pages/StartSessionPage'
import { SessionDashboardPage } from './pages/SessionDashboardPage'
import { VerifyStartPage } from './pages/VerifyStartPage'
import { VerifyResultPage } from './pages/VerifyResultPage'
import { BatchStartPage } from './pages/BatchStartPage'
import { BatchResultPage } from './pages/BatchResultPage'
import { EditorPage } from './pages/EditorPage'
import { SearchPage } from './pages/SearchPage'
import { FootageStartPage } from './pages/FootageStartPage'
import { FootageProjectPage } from './pages/FootageProjectPage'
import { LoginPage } from './pages/LoginPage'
import { RequireAuth } from './components/RequireAuth'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<RequireAuth><StartSessionPage /></RequireAuth>} />
        <Route path="/sessions/:sessionId" element={<RequireAuth><SessionDashboardPage /></RequireAuth>} />
        <Route path="/verify" element={<RequireAuth><VerifyStartPage /></RequireAuth>} />
        <Route path="/verify/batch" element={<RequireAuth><BatchStartPage /></RequireAuth>} />
        <Route path="/verify/batch/:batchId" element={<RequireAuth><BatchResultPage /></RequireAuth>} />
        <Route path="/verify/:checkId" element={<RequireAuth><VerifyResultPage /></RequireAuth>} />
        <Route path="/verify/:checkId/editor" element={<RequireAuth><EditorPage /></RequireAuth>} />
        <Route path="/search" element={<RequireAuth><SearchPage /></RequireAuth>} />
        <Route path="/footage" element={<RequireAuth><FootageStartPage /></RequireAuth>} />
        <Route path="/footage/:projectId" element={<RequireAuth><FootageProjectPage /></RequireAuth>} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
