import { Route, Routes } from "react-router"
import { AppShell } from "@/components/layout/AppShell"
import { ExperimentsView } from "@/pages/ExperimentsView"
import { ExperimentView } from "@/pages/ExperimentView"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { BoardView, ProjectPage } from "@/pages/ProjectPage"
import { ProjectsPage } from "@/pages/ProjectsPage"
import { RunView } from "@/pages/RunView"

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />}>
          <Route index element={<BoardView />} />
          <Route path="experiments" element={<ExperimentsView />} />
          <Route path="experiments/:experimentId" element={<ExperimentView />} />
          <Route path="runs/:runId" element={<RunView />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  )
}
