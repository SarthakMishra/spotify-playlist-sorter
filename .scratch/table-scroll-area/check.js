// Run this function in the browser console on each playlist preview tab.
async function checkTableScrollAreas() {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message)
  }
  const tables = [...document.querySelectorAll('[data-slot="table"]')]
  assert(tables.length > 0, "No tables to check")
  const results = []
  for (const table of tables) {
    const root = table.closest('[data-slot="table-container"]')
    const viewport = table.closest('[data-slot="scroll-area-viewport"]')
    assert(viewport, "Table still uses native scrollbars")
    assert(getComputedStyle(viewport).scrollbarWidth === "none", "Native scrollbar is visible")
    assert(getComputedStyle(root).overflow === "hidden", "Rounded container does not clip")
    assert(viewport.getAttribute("aria-label"), "Scroll viewport has no accessible name")
    assert(viewport.clientHeight <= Math.min(innerHeight * 0.55, 448) + 1, "Height limit lost")
    const { scrollTop, scrollLeft } = viewport
    const vertical = viewport.scrollHeight > viewport.clientHeight
    const horizontal = viewport.scrollWidth > viewport.clientWidth
    viewport.scrollTo(viewport.scrollWidth, viewport.scrollHeight)
    await new Promise(requestAnimationFrame)
    if (vertical) {
      assert(viewport.scrollTop > 0, "Vertical scrolling failed")
      assert(viewport.tabIndex === 0, "Scrollable viewport is not keyboard focusable")
      assert(Math.abs(table.tHead.getBoundingClientRect().top - viewport.getBoundingClientRect().top) < 2, "Header is not sticky")
    }
    for (const [orientation, overflowing] of [["vertical", vertical], ["horizontal", horizontal]]) {
      if (!overflowing) continue
      const bar = root.querySelector(`[data-slot="scroll-area-scrollbar"][data-orientation="${orientation}"]`)
      assert(bar && bar.getBoundingClientRect().width > 0, `Missing ${orientation} scrollbar`)
      const bounds = root.getBoundingClientRect()
      const rect = bar.getBoundingClientRect()
      assert(rect.left >= bounds.left && rect.top >= bounds.top && rect.right <= bounds.right && rect.bottom <= bounds.bottom, "Scrollbar escapes rounded container")
    }
    if (horizontal) assert(viewport.scrollLeft > 0, "Horizontal scrolling failed")
    viewport.scrollTo(scrollLeft, scrollTop)
    results.push({ label: viewport.getAttribute("aria-label"), vertical, horizontal })
  }
  assert(document.documentElement.scrollWidth <= innerWidth, "Table causes page overflow")
  return results
}
