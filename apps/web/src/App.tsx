import { Route, Routes } from "react-router"
import { AppShell } from "@/components/layout/AppShell"
import { AgentView } from "@/pages/AgentView"
import { ConversationView } from "@/pages/ConversationView"
import { ExperimentsView } from "@/pages/ExperimentsView"
import { ExperimentView } from "@/pages/ExperimentView"
import { FilesView } from "@/pages/FilesView"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { PipelineView } from "@/pages/PipelineView"
import { BoardView, ProjectPage } from "@/pages/ProjectPage"
import { ProjectsPage } from "@/pages/ProjectsPage"
import { RunView } from "@/pages/RunView"
import { TheoryView } from "@/pages/TheoryView"

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
          <Route path="theory" element={<TheoryView />} />
          <Route path="pipeline" element={<PipelineView />} />
          <Route path="files" element={<FilesView />} />
          <Route path="agent" element={<AgentView />} />
          <Route path="conversations/:sessionId" element={<ConversationView />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  )
}
