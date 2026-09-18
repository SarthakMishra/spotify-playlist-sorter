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
  // The timeline merge sorts every boundary; job references are stable between poll updates.
  const comparison = compareTimelines(original, tracks)
  return (
    <div className="space-y-6">
      {comparison ? (
        <div className="space-y-5">
          <TimingTable entries={comparison.original} label="Original order" />
          <TimingTable entries={comparison.suggested} label="Suggested order" />
        </div>
      ) : (
        <p className="rounded-xl border p-4 text-sm leading-6 text-muted-foreground">
          The time comparison needs a known duration for every entry.
        </p>
      )}
      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Song measurements</h3>
        <p className="text-xs leading-5 text-muted-foreground">
          Tempo and key are estimates in the suggested order. Missing values stay unavailable.
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
            Measurements compare actual endings and beginnings.
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
  )
}
