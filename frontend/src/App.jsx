import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { ThemeProvider } from './context/ThemeContext'
import ConfigurePage from './pages/ConfigurePage'
import DownloadPage from './pages/DownloadPage'
import LandingPage from './pages/LandingPage'
import NotFoundPage from './pages/NotFoundPage'
import PreviewPage from './pages/PreviewPage'
import ProcessingPage from './pages/ProcessingPage'
import UploadPage from './pages/UploadPage'

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<LandingPage />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="configure/:documentId" element={<ConfigurePage />} />
            <Route path="processing/:jobId" element={<ProcessingPage />} />
            <Route path="preview/:jobId" element={<PreviewPage />} />
            <Route path="download/:jobId" element={<DownloadPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  )
}
