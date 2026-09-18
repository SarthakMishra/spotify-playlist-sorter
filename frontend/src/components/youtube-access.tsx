import { useRef, useState, type SubmitEvent } from "react"
import { Link, useLoaderData, useRouteLoaderData } from "react-router"
import { ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { toast } from "@/components/ui/toast"
import { api, ApiError, type Session, type YouTubeAccess } from "@/lib/api"

const extension =
  "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"

export function YouTubeAccessPage() {
  const initial = useLoaderData<YouTubeAccess>()
  const session = useRouteLoaderData<Session>("root")
  const [access, setAccess] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const fileInput = useRef<HTMLInputElement>(null)
  const source = access.mode === "server" ? access.server_source : access.mode
  const description =
    source === "browser"
      ? `Using ${access.browser ?? "the configured browser"} on the app server.`
      : source === "file"
        ? "Using the cookie file configured on the app server."
        : source === "upload"
          ? "Using your uploaded cookies for this session."
          : "Analyzing public recordings without cookies."

  async function save(mode: YouTubeAccess["mode"], cookies = "") {
    setBusy(true)
    setError("")
    try {
      setAccess(
        await api<YouTubeAccess>("/youtube", {
          method: "POST",
          headers: { "X-CSRF-Token": session?.csrf ?? "" },
          body: JSON.stringify({ mode, cookies }),
        }),
      )
      if (fileInput.current) fileInput.current.value = ""
      toast.add({
        id: "youtube-access",
        title: "YouTube access updated",
        description: "Return to your playlist and analyze songs again.",
        type: "success",
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : "Please try again."
      if (err instanceof ApiError && err.status === 422) {
        setError(message)
      } else {
        toast.add({
          id: "youtube-access",
          title: "Couldn't update YouTube access",
          description: message,
          type: "error",
          priority: "high",
          timeout: 8000,
        })
      }
    } finally {
      setBusy(false)
    }
  }

  async function upload(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const file = fileInput.current?.files?.[0]
    if (!file) return
    if (file.size > 262144) {
      setError("Choose a YouTube-only export smaller than 256 KB.")
      return
    }
    try {
      await save("upload", await file.text())
    } catch {
      setError("Couldn't read this file. Try exporting it again.")
    }
  }

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <Link
        to="/playlists"
        className="inline-flex items-center gap-2 rounded-md text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" strokeWidth={1.5} aria-hidden="true" /> Your playlists
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">YouTube access</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Cookies are optional. They can help us find the correct recording when YouTube requires
          sign-in. We use them for YouTube searches and audio downloads. Analysis continues without
          them.
        </p>
      </div>
      <div className="rounded-xl border p-4 text-sm leading-6">
        <p className="font-medium">{description}</p>
        <p className="mt-1 text-muted-foreground">
          {access.node_available && access.scripts_available
            ? "YouTube player support is installed."
            : "YouTube player support is incomplete. See the server setup below."}
        </p>
      </div>
      <div>
        <h2 className="text-base font-semibold">Export from Chrome</h2>
        <ol className="mt-3 list-decimal space-y-3 pl-5 text-sm leading-6">
          <li>
            Install{" "}
            <a
              href={extension}
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-4"
            >
              Get cookies.txt LOCALLY
            </a>
            . In Chrome's extension settings, turn on Allow in Incognito for this extension.
          </li>
          <li>
            Open one Incognito window and sign in to YouTube. In the same tab, open{" "}
            <a
              href="https://www.youtube.com/robots.txt"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-4"
            >
              youtube.com/robots.txt
            </a>{" "}
            by copying its address.
          </li>
          <li>
            Use the extension to export only youtube.com cookies in Netscape format. Choose the text
            export, not JSON or all sites.
          </li>
          <li>
            Close the Incognito window, then choose the exported file below. Avoid reopening that
            Incognito session so its cookies are not rotated.
          </li>
        </ol>
        <p className="mt-4 text-xs leading-5 text-muted-foreground">
          A cookie file can give access to your YouTube account. Upload it only to an app server you
          trust. This app keeps uploaded YouTube cookies in your session, clears them on sign-out or
          expiry, and does not save them to disk.
        </p>
      </div>
      <form onSubmit={(event) => void upload(event)} className="space-y-3">
        <label htmlFor="youtube-cookie-file" className="block text-sm font-medium">
          YouTube cookie file
        </label>
        <Input
          id="youtube-cookie-file"
          ref={fileInput}
          type="file"
          accept=".txt,text/plain"
          required
          disabled={busy}
          aria-describedby="cookie-format"
        />
        <p id="cookie-format" className="text-xs text-muted-foreground">
          Netscape text format, up to 256 KB.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy}>
            Use cookie file
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void save("anonymous")}
          >
            Use without cookies
          </Button>
          {access.server_source !== "anonymous" && (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => void save("server")}
            >
              Use server {access.server_source === "browser" ? "browser" : "cookie file"}
            </Button>
          )}
        </div>
      </form>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <details className="rounded-xl border p-4 text-sm leading-6">
        <summary className="cursor-pointer rounded-sm font-medium">
          Use Chrome directly or configure the server
        </summary>
        <p className="mt-3 text-muted-foreground">
          Direct access reads Chrome on the computer running the app, not a remote visitor's
          browser. For a server or Docker installation, use the file upload above.
        </p>
        <p className="mt-3">
          For local Chrome, add these settings to the app's .env file and restart it:
        </p>
        <pre className="mt-3 rounded-md bg-muted p-3 text-xs wrap-break-word whitespace-pre-wrap">
          {
            "YOUTUBE_BROWSER=chrome\n# Optional, for a specific profile:\nYOUTUBE_BROWSER_PROFILE=Default"
          }
        </pre>
        <p className="mt-3 text-muted-foreground">
          A configured YOUTUBE_COOKIES_FILE takes precedence. Clear it to use browser access. The
          browser profile stays read-only. If Chrome is locked or cookies cannot be decrypted, use
          the extension export.
        </p>
        <p className="mt-3">
          Player support uses Node 24 and yt-dlp's bundled challenge scripts. To update them with
          the app's dependencies:
        </p>
        <pre className="mt-3 rounded-md bg-muted p-3 text-xs wrap-break-word whitespace-pre-wrap">
          uv sync --locked
        </pre>
        <p className="mt-3 text-muted-foreground">
          Installed yt-dlp: {access.yt_dlp_version}. If YouTube limits requests, wait before
          retrying. Cookies do not remove rate limits.
        </p>
        <a
          href="https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block underline underline-offset-4"
        >
          yt-dlp's cookie and access guidance
        </a>
      </details>
    </section>
  )
}
