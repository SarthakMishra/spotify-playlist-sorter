import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import {
  Table,
  TableHeader,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
  TableCaption,
} from "@/components/ui/table"
import type { Track, Transition } from "@/lib/api"
import {
  compareTimelines,
  elapsedTime,
  intensityLabel,
  measuredIntensity,
  type TimedTrack,
} from "@/lib/review"

function TimingTable({ entries, label }: { entries: TimedTrack[]; label: string }) {
  return (
    <section className="space-y-3">
      <h4 className="text-sm font-semibold">{label}</h4>
      <Table scrollLabel={`${label} times and intensity`}>
        <TableCaption className="sr-only">{label} times and intensity</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead># / Song</TableHead>
            <TableHead>Starts</TableHead>
            <TableHead>Ends</TableHead>
            <TableHead>Intensity</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry, index) => (
            <TableRow key={entry.track.occurrence}>
              <TableCell className="min-w-36 whitespace-normal">
                <p className="font-medium">
                  {index + 1}. {entry.track.name}
                </p>
                <p className="mt-1 text-muted-foreground">{entry.track.artist}</p>
              </TableCell>
              <TableCell className="tabular-nums">{elapsedTime(entry.start)}</TableCell>
              <TableCell className="tabular-nums">{elapsedTime(entry.end)}</TableCell>
              <TableCell>{intensityLabel(entry.intensity)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

export default function SongDetails({
  original,
  tracks,
  transitions,
}: {
  original: Track[]
  tracks: Track[]
  transitions: Transition[]
}) {
  const comparison = compareTimelines(original, tracks)
  const hasIntensity = comparison?.points.some(
    (point) => point.original !== null || point.suggested !== null,
  )
  return (
    <div className="space-y-7">
      <section className="space-y-4" aria-labelledby="intensity-comparison">
        <div>
          <h3 id="intensity-comparison" className="text-base font-semibold">
            Intensity over listening time
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Compare the pacing of the two orders. Each step uses one intensity estimate for a song;
            its width shows how long the song lasts.
          </p>
        </div>
        {comparison && hasIntensity ? (
          <>
            <figure
              aria-label={`Estimated intensity in the original and suggested orders over ${elapsedTime(comparison.total)}. A text table follows.`}
            >
              <ResponsiveContainer width="100%" height={240}>
                <LineChart
                  accessibilityLayer
                  data={comparison.points}
                  margin={{ top: 10, right: 12, left: 0, bottom: 10 }}
                >
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis
                    type="number"
                    dataKey="elapsed"
                    domain={[0, comparison.total]}
                    ticks={[0, comparison.total / 3, (comparison.total * 2) / 3, comparison.total]}
                    tickFormatter={elapsedTime}
                    tick={{ fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={32}
                  />
                  <YAxis
                    domain={[0, 1]}
                    ticks={[0, 0.5, 1]}
                    tickFormatter={intensityLabel}
                    tick={{ fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                    width={68}
                  />
                  <Tooltip
                    filterNull={false}
                    labelFormatter={(value: unknown) =>
                      typeof value === "number" ? elapsedTime(value) : ""
                    }
                    formatter={(value: unknown) =>
                      intensityLabel(typeof value === "number" ? value : null)
                    }
                    contentStyle={{
                      backgroundColor: "var(--popover)",
                      color: "var(--popover-foreground)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius)",
                    }}
                  />
                  <Line
                    dataKey="original"
                    name="Original"
                    stroke="var(--muted-foreground)"
                    strokeDasharray="5 4"
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="suggested"
                    name="Suggested"
                    stroke="var(--foreground)"
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </figure>
            <p className="text-xs leading-5 text-muted-foreground">
              Dashed: original order. Solid: suggested order. Gaps mean the intensity was not
              assessed. Total time: {elapsedTime(comparison.total)}. Timing assumes every item plays
              in full, with crossfade off.
            </p>
          </>
        ) : (
          <p className="rounded-xl border p-4 text-sm leading-6 text-muted-foreground">
            {comparison
              ? "Intensity measurements are unavailable for these entries."
              : "The time comparison needs a known duration for every entry. Check the numbered orders while duration information is incomplete."}
          </p>
        )}
        <p className="text-xs leading-5 text-muted-foreground">
          Intensity combines audio level and rhythmic activity relative to this playlist. Listening
          is the way to decide which order you prefer.
        </p>
        {comparison && (
          <details className="rounded-xl border p-4">
            <summary className="cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
              Song times and intensity
            </summary>
            <div className="mt-4 space-y-5">
              <TimingTable entries={comparison.original} label="Original order" />
              <TimingTable entries={comparison.suggested} label="Suggested order" />
            </div>
          </details>
        )}
      </section>
      <details className="rounded-xl border p-4">
        <summary className="cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring">
          Tempo, key and transition estimates
        </summary>
        <div className="mt-4 space-y-6">
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Song measurements in the suggested order</h3>
            <p className="text-xs leading-5 text-muted-foreground">
              Tempo and key are estimates. Missing values stay unavailable.
            </p>
            <Table scrollLabel="Song measurements in suggested order">
              <TableCaption className="sr-only">Song measurements in suggested order</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Song</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Tempo</TableHead>
                  <TableHead>Intensity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tracks.map((track, index) => (
                  <TableRow key={track.occurrence}>
                    <TableCell className="min-w-36 whitespace-normal">
                      <p className="font-medium">
                        {index + 1}. {track.name}
                      </p>
                      <p className="mt-1 text-muted-foreground">{track.artist}</p>
                    </TableCell>
                    <TableCell>{track.key ?? "Unavailable"}</TableCell>
                    <TableCell className="tabular-nums">
                      {track.bpm == null ? "Unavailable" : `${Math.round(track.bpm)} BPM`}
                    </TableCell>
                    <TableCell>{intensityLabel(measuredIntensity(track))}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
          {transitions.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-sm font-semibold">Between songs</h3>
              <p className="text-xs leading-5 text-muted-foreground">
                Measurements compare actual endings and beginnings. Tempo estimates can count the
                same pulse at half or double the speed.
              </p>
              <Table scrollLabel="Transitions between suggested songs">
                <TableCaption className="sr-only">Transitions between suggested songs</TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead>From / to</TableHead>
                    <TableHead>Tempo difference</TableHead>
                    <TableHead>Evidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transitions.map((transition) => (
                    <TableRow key={transition.index}>
                      <TableCell className="min-w-36 whitespace-normal">
                        <p>
                          {transition.index}. {transition.track1_name}
                        </p>
                        <p className="mt-1 text-muted-foreground">
                          {transition.index + 1}. {transition.track2_name}
                        </p>
                      </TableCell>
                      <TableCell>
                        {transition.bpm_diff == null
                          ? "Unavailable"
                          : `${Math.round(transition.bpm_diff)} BPM`}
                      </TableCell>
                      <TableCell>
                        {transition.score == null
                          ? "Not assessed"
                          : Math.max(...Object.values(transition.evidence)) < 0.5
                            ? "Limited evidence"
                            : "Estimates available"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          )}
        </div>
      </details>
    </div>
  )
}
