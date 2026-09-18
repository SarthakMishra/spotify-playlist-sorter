import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "cn"

const modes = {
  light: { icon: Sun, label: "Light", next: "dark" },
  dark: { icon: Moon, label: "Dark", next: "system" },
  system: { icon: Monitor, label: "System", next: "light" },
} as const

const iconTransition = "absolute inset-0 transition-[opacity,filter,scale] duration-300 ease-swift"

export function ModeToggle() {
  const { theme, setTheme } = useTheme()
  const { label, next } = modes[theme]

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Theme: ${label}. Switch to ${modes[next].label}`}
            onClick={() => setTheme(next)}
          />
        }
      >
        <span className="relative size-4">
          {Object.entries(modes).map(([key, mode]) => {
            const Icon = mode.icon
            const active = key === theme
            return (
              <Icon
                key={key}
                aria-hidden="true"
                className={cn(
                  iconTransition,
                  active ? "scale-100 opacity-100 blur-none" : "scale-25 opacity-0 blur-xs",
                )}
              />
            )
          })}
        </span>
      </TooltipTrigger>
      <TooltipContent>Theme: {label}</TooltipContent>
    </Tooltip>
  )
}
