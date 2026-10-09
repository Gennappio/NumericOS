import { Route, Routes } from "react-router"
import { AppShell } from "@/components/layout/AppShell"
import { HomePage } from "@/pages/HomePage"

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
      </Routes>
    </AppShell>
  )
}
