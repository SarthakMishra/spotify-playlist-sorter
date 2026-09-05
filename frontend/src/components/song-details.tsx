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

export default function SongDetails({
  tracks,
  transitions,
}: {
  tracks: Track[]
  transitions: Transition[]
}) {
  return (
    <div className="pt-6">
      <p className="mb-4 text-sm leading-6 text-muted-foreground">
        Speed is shown in beats per minute. Energy shows how loud a song is compared with the
        others.
      </p>
      {tracks.length > 1 && (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart
            accessibilityLayer
            data={tracks.map((track, index) => ({
              ...track,
              position: index + 1,
              energy: Math.round(track.energy * 100),
            }))}
            margin={{ top: 10, right: 0, left: 0, bottom: 10 }}
          >
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="position" tickLine={false} axisLine={false} minTickGap={24} />
            <YAxis yAxisId="bpm" tickLine={false} axisLine={false} width={40} />
            <YAxis
              tick={{ fill: "var(--muted-foreground)" }}
              yAxisId="energy"
              orientation="right"
              domain={[0, 100]}
              tickLine={false}
              axisLine={false}
              width={35}
            />
            <Tooltip
              labelFormatter={(position: unknown) => `Song ${String(position)}`}
              contentStyle={{
                backgroundColor: "var(--popover)",
                color: "var(--popover-foreground)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
              }}
            />
            <Line
              yAxisId="bpm"
              dataKey="bpm"
              name="Speed"
              stroke="var(--foreground)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              yAxisId="energy"
              dataKey="energy"
              name="Energy"
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
      <p className="mt-2 mb-5 text-xs text-muted-foreground">
        Solid line: speed. Dashed line: energy. Songs run left to right.
      </p>
      <Table>
        <TableCaption>
          Key uses Camelot numbers. Nearby numbers usually fit well together.
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Song</TableHead>
            <TableHead>Key</TableHead>
            <TableHead>Speed</TableHead>
            <TableHead>Energy</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tracks.map((track) => (
            <TableRow key={track.occurrence}>
              <TableCell className="max-w-56 whitespace-normal">{track.name}</TableCell>
              <TableCell>{track.key}</TableCell>
              <TableCell className="tabular-nums">{Math.round(track.bpm)}</TableCell>
              <TableCell className="tabular-nums">{Math.round(track.energy * 100)}%</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {transitions.length > 0 && (
        <>
          <h3 className="mt-8 mb-2 text-sm font-medium">Between songs</h3>
          <Table>
            <TableCaption>
              A higher match means the songs are closer in key, speed, and energy.
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>From / to</TableHead>
                <TableHead>Speed change</TableHead>
                <TableHead>Match</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {transitions.map((transition) => (
                <TableRow key={transition.index}>
                  <TableCell className="max-w-64 whitespace-normal">
                    <p>{transition.track1_name}</p>
                    <p className="mt-1 text-muted-foreground">{transition.track2_name}</p>
                  </TableCell>
                  <TableCell>
                    {transition.bpm_diff == null
                      ? "Unavailable"
                      : `${Math.round(transition.bpm_diff)} BPM`}
                  </TableCell>
                  <TableCell>
                    {transition.score == null
                      ? "Unavailable"
                      : `${Math.round(transition.score * 100)}%`}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  )
}
