import type { Job, Track } from "@/lib/api"
import { getJob } from "@/lib/api"
import { toast } from "@/components/ui/toast"

export const WORKING_STATUSES = ["analyzing", "sorting", "saving", "restoring"] as const

export function isWorking(job: Job | null | undefined): boolean {
  return !!job && (WORKING_STATUSES as readonly string[]).includes(job.status)
}

export function isWorkingStatus(status: Job["status"] | undefined): boolean {
  return !!status && (WORKING_STATUSES as readonly string[]).includes(status)
}

export function isRematchStage(status: Track["analysis_status"]): boolean {
  return status === "matching" || status === "downloading" || status === "analyzing"
}

// Poll the session's job while it is working. Each request schedules the next one
// after it finishes; cleanup aborts the in-flight request and the pending timer.
export function watchJob(handlers: {
  onJob: (job: Job | null) => void
  onError: (error: unknown) => void
}): () => void {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout>
  async function poll() {
    try {
      const next = await getJob({ signal: controller.signal })
      if (controller.signal.aborted) return
      handlers.onJob(next)
      if (isWorking(next)) timer = setTimeout(poll, 1000)
    } catch (error) {
      if (controller.signal.aborted) return
      handlers.onError(error)
    }
  }
  timer = setTimeout(poll, 700)
  return () => {
    controller.abort()
    clearTimeout(timer)
  }
}

function rematchToastId(occurrence: string): string {
  return `rematch-${occurrence}`
}

export function beginRematchToast(track: Track): void {
  toast.add({
    id: rematchToastId(track.occurrence),
    title: "Re-analyzing this song",
    description: `${track.name} · Using the recording you picked.`,
    type: "loading",
    priority: "low",
    timeout: 0,
  })
}

// Resolve the pending rematch toast once a poll sees the song leave the working stages.
export function resolveRematchToast(job: Job, occurrence: string): boolean {
  const track = job.tracks.find((item) => item.occurrence === occurrence)
  if (!track || isRematchStage(track.analysis_status)) return false
  toast.close(rematchToastId(occurrence))
  if (track.analysis_status === "ready" && job.status === "ready") {
    toast.add({
      title: "Recording updated",
      description: track.name,
      type: "success",
      priority: "low",
      timeout: 5000,
    })
  } else {
    toast.add({
      title: "Couldn't update the recording",
      description: job.error ?? track.fixed_reason ?? "Please try again.",
      type: "error",
      priority: "high",
      timeout: 8000,
    })
  }
  return true
}

export function cancelRematchToast(occurrence: string): void {
  toast.close(rematchToastId(occurrence))
}
