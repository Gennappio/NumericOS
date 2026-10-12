import { artifactUrl, type Artifact } from "@/api/client"
import { formatBytes, shortHash } from "@/lib/format"

const KIND_LABELS: Record<string, string> = {
  result: "Result of the program",
  output: "Output lines",
  resources: "Resource samples",
  journal: "Monitor journal",
  outcome: "How the program ended",
  metric_series: "Samples of a metric",
  metric_summary: "Summary of the metrics",
  monitor_log: "Monitor log",
  code_diff: "Uncommitted changes that ran",
  untracked_files: "Untracked files that ran",
  environment_probe: "Environment probe",
}

/** The files a run left, each with its size and checksum. Results of the program come first. */
export function ArtifactsPanel({ artifacts, ended }: { artifacts: Artifact[]; ended: boolean }) {
  if (artifacts.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {ended ? "The run left no file." : "Files are listed when the run has ended."}
      </p>
    )
  }
  const ordered = [...artifacts].sort(
    (a, b) => Number(b.kind === "result") - Number(a.kind === "result") || a.name.localeCompare(b.name),
  )
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full text-sm">
        <caption className="sr-only">Files of the run</caption>
        <thead className="border-b border-border text-left text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">File</th>
            <th scope="col" className="px-3 py-2 font-medium">What it is</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Size</th>
            <th scope="col" className="px-3 py-2 font-medium">SHA-256</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {ordered.map((artifact) => (
            <tr key={artifact.id}>
              <td className="px-3 py-2">
                <a
                  href={artifactUrl(artifact.id)}
                  className="font-mono text-xs break-all underline underline-offset-4"
                >
                  {artifact.name}
                </a>
              </td>
              <td className="px-3 py-2">{KIND_LABELS[artifact.kind] ?? artifact.kind}</td>
              <td className="px-3 py-2 text-right font-mono text-xs whitespace-nowrap">
                {formatBytes(artifact.size_bytes)}
              </td>
              <td className="px-3 py-2 font-mono text-xs" title={artifact.sha256 ?? undefined}>
                {artifact.sha256 ? `${shortHash(artifact.sha256)}…` : "too large to hash"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
