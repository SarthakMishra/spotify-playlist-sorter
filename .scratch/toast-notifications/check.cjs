// Start Vite, then NODE_PATH=/path/to/browser-tools/node_modules node .scratch/toast-notifications/check.cjs
// Reuses the browser fixtures in check.js; every API request, including saves, is mocked.
const { chromium } = require("playwright")
const AxeBuilder = require("@axe-core/playwright").default
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const source = fs.readFileSync(path.join(__dirname, "check.js"), "utf8")
const activeToast = '[data-slot="toast"]:not([data-ending-style])'

async function main() {
  const browser = await chromium.launch({ headless: true })
  try {
    for (const [theme, width] of [["light", 1280], ["dark", 390], ["light", 320]]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: theme, reducedMotion: "reduce" })
      const page = await context.newPage()
      const errors = []
      page.on("pageerror", error => errors.push(error.message))
      await page.addInitScript({ content: source + "\nwindow.checkToastNotifications = checkToastNotifications; installToastCheck()" })
      await page.goto("http://127.0.0.1:5178/playlists/toast-check")
      console.log(theme, width, await page.evaluate(() => checkToastNotifications()))

      // Navigate within the app so mocks remain in place while we clear the old job.
      await page.getByRole("link", { name: "Your playlists", exact: true }).click()
      await page.evaluate(() => { window.toastCheck.job = null; window.toastCheck.rejectNext = true })
      await page.getByRole("link", { name: "Weekend listening 3 songs" }).click()
      const analysisToast = page.locator(activeToast).filter({ hasText: "Couldn't check songs" })
      await analysisToast.waitFor()
      assert(!(await page.locator("main").innerText()).includes("Temporarily unavailable"))
      await analysisToast.locator('[data-slot="toast-action"]').click()
      await page.getByRole("heading", { name: "Checking songs" }).waitFor()
      assert.equal(await analysisToast.count(), 0)

      // Paused analysis must offer both a toast action and recovery after dismissal.
      await page.evaluate(() => { window.toastCheck.failPoll = true })
      const pollToast = page.locator(activeToast).filter({ hasText: "Couldn't check progress" })
      await pollToast.waitFor()
      assert(!(await page.locator("main").innerText()).includes("Failed to fetch"))
      assert.equal(await page.locator('main [data-slot="alert"]').count(), 0)
      await page.keyboard.press("F6")
      assert(await page.evaluate(() => !!document.activeElement.closest('[data-slot="toast-viewport"]')))
      // Base UI exposes high-priority toast controls to the accessibility tree when focused.
      // Focus guards are invisible sentinels that redirect focus, not user controls.
      const a11y = await new AxeBuilder({ page }).exclude("[data-base-ui-focus-guard]")
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()
      assert.deepEqual(a11y.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ html: node.html, message: node.failureSummary })) })), [])
      await page.screenshot({ path: path.join(__dirname, `${theme}-${width}-polling-error.png`), fullPage: true })
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      const titleBox = await pollToast.locator('[data-slot="toast-title"]').boundingBox()
      const actionBox = await pollToast.locator('[data-slot="toast-action"]').boundingBox()
      assert(titleBox.width >= 140, "Toast action squeezed the message into a narrow column")
      assert(actionBox.y >= titleBox.y + titleBox.height, "Toast action must sit below the message")
      await pollToast.getByRole("button", { name: "Close toast" }).focus()
      await page.keyboard.press("Enter")
      assert.equal(await pollToast.count(), 0)
      await page.evaluate(() => { window.toastCheck.failPoll = false; window.toastCheck.job.status = "ready" })
      await page.locator("main").getByRole("button", { name: "Check progress" }).focus()
      await page.keyboard.press("Enter")
      await page.getByRole("button", { name: "Arrange playlist", exact: true }).waitFor()

      // Leaving a paused playlist removes its retry action. Returning resumes polling.
      await page.getByRole("button", { name: "Arrange playlist", exact: true }).click()
      await page.evaluate(() => { window.toastCheck.failPoll = true })
      await pollToast.waitFor()
      await page.getByRole("link", { name: "Your playlists", exact: true }).click()
      await page.getByRole("heading", { name: "Your playlists", exact: true }).waitFor()
      assert.equal(await page.locator(activeToast).count(), 0)
      await page.evaluate(() => { window.toastCheck.failPoll = false; window.toastCheck.job.status = "ready" })
      await page.getByRole("link", { name: "Weekend listening 3 songs" }).click()
      await page.getByRole("button", { name: "Arrange playlist", exact: true }).waitFor()
      assert.equal(await page.locator(activeToast).count(), 0)

      await page.getByRole("link", { name: "YouTube access", exact: true }).click()
      const withoutCookies = page.getByRole("button", { name: "Use without cookies", exact: true })
      await withoutCookies.click()
      const accessToast = page.locator(activeToast).filter({ hasText: "YouTube access updated" })
      await accessToast.waitFor()
      assert(!(await page.locator("main").innerText()).includes("YouTube access updated"))
      await page.evaluate(() => document.querySelectorAll('[data-slot="toast-close"]').forEach(button => button.click()))
      await page.evaluate(() => { window.toastCheck.youtubeStatus = 503 })
      await withoutCookies.click()
      await page.locator(activeToast).filter({ hasText: "Couldn't update YouTube access" }).waitFor()
      assert(!(await page.locator("main").innerText()).includes("Failed to fetch"))
      await page.evaluate(() => document.querySelectorAll('[data-slot="toast-close"]').forEach(button => button.click()))
      await page.evaluate(() => { window.toastCheck.youtubeStatus = 422 })
      await page.getByLabel("YouTube cookie file", { exact: true }).setInputFiles({ name: "invalid.txt", mimeType: "text/plain", buffer: Buffer.from("invalid fixture") })
      await page.getByRole("button", { name: "Use cookie file", exact: true }).click()
      await page.locator('main [role="alert"]').filter({ hasText: "Choose a valid cookie export." }).waitFor()
      assert.equal(await page.locator(activeToast).count(), 0)
      assert.deepEqual(errors, [])
      console.log(theme, width, "Passed: analysis failure/retry, polling dismissal/recovery, navigation cleanup, keyboard, accessibility, overflow, YouTube access feedback and inline validation.")
      await context.close()
    }
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
