export function HomePage() {
  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-2xl font-semibold">Research workspace</h1>
      <p className="text-muted-foreground">
        NumericOS is built one milestone at a time. After ticket M0-T01 the application shell, the
        API health check and the CLI exist; projects, the scientific board and the event ledger
        arrive with the remaining M0 tickets.
      </p>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        <li>
          API: <code>GET /v1/health</code> (its result is the connection status above)
        </li>
        <li>
          CLI: <code>numericos health --json</code>
        </li>
      </ul>
    </section>
  )
}
