import { Link } from "react-router"

export function NotFoundPage() {
  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="text-sm underline underline-offset-4">
        Back to all projects
      </Link>
    </section>
  )
}
