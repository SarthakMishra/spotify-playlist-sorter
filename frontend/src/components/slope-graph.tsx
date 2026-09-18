import { useMemo, useState } from "react"
import type { Track } from "@/lib/api"

type Move = {
  occurrence: string
  name: string
  artist: string
  was: number
  now: number
}

// One line per song that moved: left is the original position, right is the
// suggested position. Crossings and flat stretches show the churn pattern.
export default function SlopeGraph({ tracks }: { tracks: Track[] }) {
  const [hovered, setHovered] = useState<string | null>(null)

  const { moves, total } = useMemo(() => {
    const result: Move[] = []
    tracks.forEach((track, now) => {
      const was = track.original_position
      if (was !== now)
        result.push({
          occurrence: track.occurrence,
          name: track.name,
          artist: track.artist,
          was: was + 1,
          now: now + 1,
        })
    })
    return { moves: result, total: tracks.length }
  }, [tracks])

  if (moves.length === 0) return null

  const pad = 8
  const step = total > 1 ? (100 - pad * 2) / (total - 1) : 0
  const y = (position: number) => pad + position * step
  const hoveredMove = moves.find((move) => move.occurrence === hovered)

  return (
    <div className="space-y-3">
      <p className="text-xs leading-5 text-muted-foreground">
        Each line is one song: left is where it was, right is where it plays now.
      </p>
      <div
        className="relative py-1"
        aria-label={`${moves.length} of ${total} songs changed position`}
      >
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="h-48 w-full"
          aria-hidden="true"
        >
          {moves.map((move) => {
            const dim = hovered !== null && hovered !== move.occurrence
            return (
              <path
                key={move.occurrence}
                d={`M 0 ${y(move.was - 1).toFixed(2)} L 100 ${y(move.now - 1).toFixed(2)}`}
                fill="none"
                stroke={dim ? "var(--muted-foreground)" : "var(--foreground)"}
                strokeOpacity={dim ? 0.25 : 0.9}
                strokeWidth={dim ? 1 : 1.5}
                vectorEffect="non-scaling-stroke"
              />
            )
          })}
        </svg>
        {/* Hit targets live outside the stretched SVG so hover areas stay usable. */}
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
        >
          {moves.map((move) => (
            <path
              key={move.occurrence}
              d={`M 0 ${y(move.was - 1).toFixed(2)} L 100 ${y(move.now - 1).toFixed(2)}`}
              fill="none"
              stroke="transparent"
              strokeWidth={6}
              vectorEffect="non-scaling-stroke"
              onMouseEnter={() => setHovered(move.occurrence)}
              onMouseLeave={() => setHovered(null)}
            />
          ))}
        </svg>
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Left: original position</span>
        <span>Right: suggested position</span>
      </div>
      <ul className="sr-only">
        {moves.map((move) => (
          <li key={move.occurrence}>
            {move.name} · {move.artist}: was #{move.was}, now #{move.now}
          </li>
        ))}
      </ul>
      {hoveredMove && (
        <output className="block text-sm font-medium">
          {hoveredMove.name}
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            #{hoveredMove.was} → #{hoveredMove.now}
          </span>
        </output>
      )}
    </div>
  )
}
