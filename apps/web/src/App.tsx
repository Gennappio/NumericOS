import { Route, Routes } from "react-router"
import { AppShell } from "@/components/layout/AppShell"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { ProjectPage } from "@/pages/ProjectPage"
import { ProjectsPage } from "@/pages/ProjectsPage"

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  )
}
