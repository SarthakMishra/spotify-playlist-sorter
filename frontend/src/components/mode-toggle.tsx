import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"

const modes = {
  light: { icon: Sun, label: "Light", next: "dark" },
  dark: { icon: Moon, label: "Dark", next: "system" },
  system: { icon: Monitor, label: "System", next: "light" },
} as const

export function ModeToggle() {
  const { theme, setTheme } = useTheme()
  const { icon: Icon, label, next } = modes[theme]

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-24 gap-2 text-muted-foreground focus-visible:text-foreground max-sm:flex-1"
      aria-label={`Theme: ${label}. Switch to ${modes[next].label}`}
      onClick={() => setTheme(next)}
    >
      <Icon aria-hidden="true" />
      {label}
    </Button>
  )
}
