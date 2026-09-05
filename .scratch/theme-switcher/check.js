// Paste this function into the browser console, then run await checkThemeSwitcher().
async function checkThemeSwitcher() {
  const trigger = document.querySelector('button[aria-label^="Theme:"]')
  if (!trigger) throw new Error("Theme switcher is missing")
  const assert = (condition, message) => {
    if (!condition) throw new Error(message)
  }
  const settle = () => new Promise((resolve) => setTimeout(resolve, 100))
  const next = { light: "dark", dark: "system", system: "light" }
  const icons = { light: "sun", dark: "moon", system: "monitor" }
  let theme = localStorage.getItem("playlist-sorter-theme")
  for (let index = 0; index < 3; index++) {
    trigger.click()
    await settle()
    theme = next[theme]
    const expectedDark = theme === "dark" || (
      theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches
    )
    assert(document.documentElement.classList.contains("dark") === expectedDark, `${theme} did not apply`)
    assert(localStorage.getItem("playlist-sorter-theme") === theme, `${theme} was not saved`)
    assert(trigger.textContent.trim().toLowerCase() === theme, `${theme} label is missing`)
    assert(trigger.querySelector(`.lucide-${icons[theme]}`), `${theme} icon is missing`)
    assert(!document.querySelector('[role="menu"]'), "A dropdown opened")
  }
  const header = document.querySelector("header > div").getBoundingClientRect()
  const content = document.querySelector("main section").getBoundingClientRect()
  assert(Math.abs(header.left - content.left) < 1 && Math.abs(header.right - content.right) < 1,
    "Header and page content are misaligned")
  assert(document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    "Page overflows horizontally")
  for (const button of document.querySelectorAll("header button")) {
    assert(button.textContent.trim(), "A header button has no visible label")
    assert(button.getBoundingClientRect().height === 32, "A header button is not compact")
    assert(button.classList.contains("hover:bg-muted"), "A header button is not using ghost styling")
  }
  return "Theme cycle, icons, labels, persistence, header alignment, and button styles passed"
}
