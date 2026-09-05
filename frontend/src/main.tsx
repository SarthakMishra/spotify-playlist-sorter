import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router/dom"
// oxlint-disable-next-line import/no-unassigned-import -- Vite loads the global stylesheet for its side effect.
import "./index.css"
import { router } from "./App"

const theme = window.matchMedia("(prefers-color-scheme: dark)")
const applyTheme = () => document.documentElement.classList.toggle("dark", theme.matches)
applyTheme()
theme.addEventListener("change", applyTheme)

const root = document.getElementById("root")
if (!root) throw new Error("The page could not start.")
createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
