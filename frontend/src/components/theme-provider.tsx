import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

type Theme = "light" | "dark" | "system"

const ThemeContext = createContext<{
  theme: Theme
  setTheme: (theme: Theme) => void
} | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem("playlist-sorter-theme")
      return saved === "light" || saved === "dark" ? saved : "system"
    } catch {
      return "system"
    }
  })

  useLayoutEffect(() => {
    const system = window.matchMedia("(prefers-color-scheme: dark)")
    const applyTheme = () => {
      document.documentElement.classList.toggle(
        "dark",
        theme === "dark" || (theme === "system" && system.matches),
      )
    }
    applyTheme()
    system.addEventListener("change", applyTheme)
    try {
      localStorage.setItem("playlist-sorter-theme", theme)
    } catch {
      // Theme changes still work when browser storage is unavailable.
    }
    return () => system.removeEventListener("change", applyTheme)
  }, [theme])

  const value = useMemo(() => ({ theme, setTheme }), [theme])
  return <ThemeContext value={value}>{children}</ThemeContext>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error("useTheme must be used within a ThemeProvider")
  return context
}
