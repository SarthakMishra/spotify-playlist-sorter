import { useEffect, useRef, useState } from "react"
import { ArrowDownWideNarrow, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { Preset, Track } from "@/lib/api"
import {
  PRESETS,
  SLIDERS,
  describeSlider,
  luckyPreferences,
  presetValues,
  type Preferences,
} from "@/lib/preferences"

type PlacementChoice = "keep" | "top" | "bottom" | "custom"

const placementItems: { value: PlacementChoice; label: string }[] = [
  { value: "keep", label: "Keep in place" },
  { value: "top", label: "Move to top" },
  { value: "bottom", label: "Move to bottom" },
  { value: "custom", label: "Custom position" },
]

const groupPlacementItems: { value: "keep" | "top" | "bottom"; label: string }[] = [
  { value: "keep", label: "Keep in place" },
  { value: "top", label: "Move to top" },
  { value: "bottom", label: "Move to bottom" },
]

function SongPicker({
  id,
  label,
  tracks,
  value,
  onChange,
  disabled,
}: {
  id: string
  label: string
  tracks: Track[]
  value: string | null
  onChange: (value: string | null) => void
  disabled: boolean
}) {
  const selected = tracks.find((track) => track.occurrence === value) ?? null
  return (
    <div className="min-w-0 space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Combobox
        items={tracks}
        value={selected}
        disabled={disabled}
        onValueChange={(track) => onChange(track?.occurrence ?? null)}
        itemToStringLabel={(track) =>
          `${track.name} · ${track.artist} · Originally #${track.original_position + 1}`
        }
        itemToStringValue={(track) => track.occurrence}
        isItemEqualToValue={(a, b) => a.occurrence === b.occurrence}
      >
        <ComboboxInput
          id={id}
          className="w-full"
          placeholder="Choose for me"
          showClear={!!selected && !disabled}
          disabled={disabled}
        />
        <ComboboxContent>
          <ComboboxEmpty>No songs found.</ComboboxEmpty>
          <ComboboxList>
            {(track: Track) => (
              <ComboboxItem key={track.occurrence} value={track}>
                <div className="min-w-0">
                  <p className="truncate">{track.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {track.artist} · Originally #{track.original_position + 1}
                  </p>
                </div>
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
      {selected && (
        <p className="text-xs text-muted-foreground">
          Originally #{selected.original_position + 1}
        </p>
      )}
    </div>
  )
}

export function PreferencesStep({
  preferences,
  onPreferencesChange,
  busy,
  canSort,
  choices,
  firstOccurrence,
  lastOccurrence,
  onFirstChange,
  onLastChange,
  fixedFirst,
  fixedLast,
  fixedTracks,
  total,
  placementTargets,
  slotTaken,
  onPlacementsChange,
  placementConflict,
  hasPreview,
  onArrange,
}: {
  preferences: Preferences
  onPreferencesChange: (preferences: Preferences) => void
  busy: boolean
  canSort: boolean
  choices: Track[]
  firstOccurrence: string | null
  lastOccurrence: string | null
  onFirstChange: (value: string | null) => void
  onLastChange: (value: string | null) => void
  fixedFirst: Track | null
  fixedLast: Track | null
  fixedTracks: Track[]
  total: number
  placementTargets: Map<string, number>
  slotTaken: (slot: number, except: Track) => boolean
  onPlacementsChange: (placements: Record<string, number>) => void
  placementConflict: string | null
  hasPreview: boolean
  onArrange: () => void
}) {
  const [placementChoice, setPlacementChoice] = useState<Record<string, PlacementChoice>>({})
  const [customPositions, setCustomPositions] = useState<Record<string, number>>({})
  const [placementMode, setPlacementMode] = useState<"all" | "individual">("all")
  const [defaultPlacement, setDefaultPlacement] = useState<"keep" | "top" | "bottom">("keep")
  const [moreOpen, setMoreOpen] = useState(!!fixedTracks.length)
  const heading = useRef<HTMLHeadingElement>(null)
  const busyBlocked = busy
  useEffect(() => {
    heading.current?.focus()
  }, [])

  function setPreset(preset: Preset) {
    onPreferencesChange({ ...presetValues(preset), preset })
  }

  function setSlider(key: "pace" | "energy" | "variety", value: number) {
    onPreferencesChange({ ...preferences, [key]: value })
  }

  function commit(nextChoice: Record<string, PlacementChoice>, nextCustom: Record<string, number>) {
    setPlacementChoice(nextChoice)
    setCustomPositions(nextCustom)
    const nextPlacement: Record<string, number> = {}
    for (const track of fixedTracks) {
      const choice = nextChoice[track.occurrence] ?? defaultPlacement
      const custom = nextCustom[track.occurrence] ?? track.original_position + 1
      if (choice === "top") nextPlacement[track.occurrence] = 0
      else if (choice === "bottom") nextPlacement[track.occurrence] = total - 1
      else if (choice === "custom")
        nextPlacement[track.occurrence] = Math.min(Math.max(custom, 1), Math.max(total, 1)) - 1
    }
    onPlacementsChange(nextPlacement)
  }

  if (!canSort) {
    return (
      <section className="space-y-4" aria-labelledby="preferences-heading">
        <h2
          ref={heading}
          id="preferences-heading"
          tabIndex={-1}
          className="rounded-sm text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Preferences
        </h2>
        <p className="text-sm text-muted-foreground">
          {choices.length === 0
            ? "None of these songs could be analyzed, so this playlist keeps its original order."
            : "Only one song can move. At least two analyzed songs are needed to rearrange this playlist."}
        </p>
      </section>
    )
  }

  return (
    <section className="space-y-10" aria-labelledby="preferences-heading">
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2
              ref={heading}
              id="preferences-heading"
              tabIndex={-1}
              className="rounded-sm text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              How should it flow?
            </h2>
            <p aria-live="polite" className="mt-1 text-sm text-muted-foreground">
              Pick a starting feel, then fine-tune below.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => onPreferencesChange(luckyPreferences())}
            className="shrink-0"
          >
            <Sparkles aria-hidden="true" data-icon="inline-start" />
            I'm feeling lucky
          </Button>
        </div>
        <ToggleGroup
          value={[preferences.preset]}
          onValueChange={(values: unknown[]) => {
            const next = values[0]
            const preset = PRESETS.find((meta) => meta.value === next)
            if (preset && preset.value !== preferences.preset) setPreset(preset.value)
          }}
          spacing={4}
          className="grid w-full grid-cols-2"
          aria-label="Flow style"
        >
          {PRESETS.map((preset) => (
            <ToggleGroupItem
              key={preset.value}
              value={preset.value}
              variant="card"
              aria-label={`${preset.label}. ${preset.description}`}
              className="w-full"
            >
              <span className="block text-sm font-medium">{preset.label}</span>
              <span className="block text-xs font-normal text-pretty text-muted-foreground">
                {preset.description}
              </span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <div className="space-y-8">
        {SLIDERS.map((slider) => (
          <div key={slider.key} className="space-y-2">
            <div className="flex items-baseline justify-between gap-3">
              <label htmlFor={`slider-${slider.key}`} className="text-sm font-medium">
                {slider.label}
              </label>
              <span
                id={`slider-${slider.key}-value`}
                className="text-xs text-muted-foreground"
                aria-live="polite"
              >
                {describeSlider(slider.key, preferences[slider.key])}
              </span>
            </div>
            <Slider
              id={`slider-${slider.key}`}
              value={[preferences[slider.key] * 100]}
              max={100}
              min={0}
              step={1}
              onValueChange={(value) => {
                const next = typeof value === "number" ? value : value[0]
                if (next !== undefined) setSlider(slider.key, next / 100)
              }}
              aria-label={`${slider.label}. ${slider.hint}`}
              aria-describedby={`slider-${slider.key}-value`}
              disabled={busyBlocked}
            />
          </div>
        ))}
      </div>
      <Collapsible open={moreOpen} onOpenChange={setMoreOpen}>
        <CollapsibleContent>
          <div className="mb-3 animate-in space-y-5 rounded-xl border bg-muted/20 p-4 duration-150 ease-out fade-in-0">
            <div className="space-y-2">
              <SongPicker
                id="first-song"
                label="First song"
                tracks={fixedFirst ? [fixedFirst] : choices}
                value={fixedFirst?.occurrence ?? firstOccurrence}
                onChange={onFirstChange}
                disabled={busy || !!fixedFirst}
              />
              {fixedFirst && (
                <p className="text-xs text-muted-foreground">
                  This item is placed first. {fixedFirst.fixed_reason}.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <SongPicker
                id="last-song"
                label="Last song"
                tracks={fixedLast ? [fixedLast] : choices}
                value={fixedLast?.occurrence ?? lastOccurrence}
                onChange={onLastChange}
                disabled={busy || !!fixedLast}
              />
              {fixedLast && (
                <p className="text-xs text-muted-foreground">
                  This item is placed last. {fixedLast.fixed_reason}.
                </p>
              )}
            </div>
            {fixedTracks.length > 0 && (
              <fieldset disabled={busyBlocked} className="min-w-0">
                <legend className="text-sm font-medium">Items that can't be analyzed</legend>
                {placementMode === "all" ? (
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
                    <Select
                      items={groupPlacementItems}
                      value={defaultPlacement}
                      onValueChange={(value) => {
                        if (value === null) return
                        setDefaultPlacement(value)
                        commit({}, {})
                      }}
                    >
                      <SelectTrigger
                        size="sm"
                        className="min-w-40 flex-1"
                        aria-label="Placement for items that can't be analyzed"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="keep">Keep in place</SelectItem>
                        <SelectItem value="top">Move to top</SelectItem>
                        <SelectItem value="bottom">Move to bottom</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPlacementMode("individual")}
                    >
                      Choose individually
                    </Button>
                  </div>
                ) : (
                  <div className="mt-2">
                    <ul className="divide-y rounded-xl border bg-background/50 px-3">
                      {fixedTracks.map((track) => {
                        const choice = placementChoice[track.occurrence] ?? defaultPlacement
                        const custom =
                          customPositions[track.occurrence] ?? track.original_position + 1
                        const current = placementTargets.get(track.occurrence)
                        return (
                          <li
                            key={track.occurrence}
                            className="flex flex-wrap items-center gap-3 py-3.5"
                          >
                            <div className="min-w-0 flex-1 basis-40">
                              <p className="truncate text-sm font-medium">{track.name}</p>
                              <p className="truncate text-xs text-muted-foreground">
                                {track.fixed_reason}
                                {current != null && <> · Now #{current + 1}</>}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Select
                                items={placementItems}
                                value={choice}
                                onValueChange={(value) => {
                                  if (value === null) return
                                  const chosenAt =
                                    customPositions[track.occurrence] ?? track.original_position + 1
                                  const nextChoice = {
                                    ...placementChoice,
                                    [track.occurrence]: value,
                                  }
                                  if (value === "top" || (value === "custom" && chosenAt === 1))
                                    onFirstChange(null)
                                  if (
                                    value === "bottom" ||
                                    (value === "custom" && chosenAt === total)
                                  )
                                    onLastChange(null)
                                  commit(nextChoice, customPositions)
                                }}
                              >
                                <SelectTrigger
                                  size="sm"
                                  className="min-w-40"
                                  aria-label={`Position for ${track.name}`}
                                >
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="keep">Keep in place</SelectItem>
                                  <SelectItem value="top" disabled={slotTaken(0, track)}>
                                    Move to top
                                  </SelectItem>
                                  <SelectItem value="bottom" disabled={slotTaken(total - 1, track)}>
                                    Move to bottom
                                  </SelectItem>
                                  <SelectItem value="custom">Custom position</SelectItem>
                                </SelectContent>
                              </Select>
                              {choice === "custom" && (
                                <input
                                  type="number"
                                  className="w-16 animate-in rounded-lg border bg-background px-2 py-1 text-sm tabular-nums duration-150 ease-out fade-in-0 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none disabled:opacity-50"
                                  min={1}
                                  max={total}
                                  value={custom}
                                  aria-label={`Custom position for ${track.name}`}
                                  onChange={(event) => {
                                    const position = Number.parseInt(event.target.value, 10)
                                    if (Number.isNaN(position)) return
                                    const bounded = Math.min(Math.max(position, 1), total)
                                    const nextCustom = {
                                      ...customPositions,
                                      [track.occurrence]: bounded,
                                    }
                                    if (bounded === 1) onFirstChange(null)
                                    if (bounded === total) onLastChange(null)
                                    commit(placementChoice, nextCustom)
                                  }}
                                />
                              )}
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={() => {
                        setPlacementMode("all")
                        setDefaultPlacement("keep")
                        commit({}, {})
                      }}
                    >
                      Use the same position for all
                    </Button>
                  </div>
                )}
              </fieldset>
            )}
          </div>
        </CollapsibleContent>
        {placementConflict && (
          <p role="alert" className="text-sm text-destructive">
            {placementConflict}
          </p>
        )}
        <div className="flex items-center gap-3">
          <CollapsibleTrigger render={<Button variant="outline" size="lg" />}>
            {moreOpen ? "Hide options" : "More options"}
            {fixedTracks.length > 0 && (
              <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground tabular-nums">
                {fixedTracks.length}
              </span>
            )}
          </CollapsibleTrigger>
          <Button
            onClick={onArrange}
            disabled={busyBlocked || placementConflict !== null}
            size="lg"
            className="min-w-0 flex-1"
          >
            <ArrowDownWideNarrow aria-hidden="true" data-icon="inline-start" />
            {hasPreview ? "Arrange again" : "Arrange playlist"}
          </Button>
        </div>
      </Collapsible>
    </section>
  )
}
