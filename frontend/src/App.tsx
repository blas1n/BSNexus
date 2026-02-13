import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import ArchitectPage from './pages/ArchitectPage'
import BoardPage from './pages/BoardPage'
import WorkersPage from './pages/WorkersPage'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/architect/:sessionId?" element={<ArchitectPage />} />
            <Route path="/board" element={<BoardPage />} />
            <Route path="/board/:projectId" element={<BoardPage />} />
            <Route path="/workers" element={<WorkersPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
