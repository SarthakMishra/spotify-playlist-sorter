// NODE_PATH must expose Playwright and axe; Vite runs at 127.0.0.1:5178.
// All API traffic uses invented fixtures, including simulated save requests.
const { chromium } = require("playwright")
const AxeBuilder = require("@axe-core/playwright").default
const assert = require("node:assert/strict")
const path = require("node:path")
const playlistId = "p".repeat(22)
const names = ["Afterglow", "Uncertain recording", "Night drive", "Unavailable item", "Afterglow", "Weekend demo", "An evening conversation"]
const reasons = [null, "Recording uncertain", null, "Unavailable on Spotify", null, "Local file", "Episode"]
const original = names.map((name, i) => ({
  occurrence: `fixture:snapshot:${i}`, original_position: i, duration_ms: 180000,
  id: i === 3 || i === 5 ? null : (i === 4 ? "a" : String.fromCharCode(97 + i)).repeat(22),
  name, artist: i === 3 ? "" : i === 6 ? "Example show" : "Example artist",
  kind: i === 3 ? "unavailable" : i === 5 ? "local" : i === 6 ? "episode" : "track",
  fixed_reason: reasons[i], key: reasons[i] ? null : "8B",
  bpm: reasons[i] ? null : 120 + i, energy: reasons[i] ? null : 0.5 + i * 0.05,
}))
function transitionRows(tracks) {
  return tracks.slice(1).map((to, i) => {
    const from = tracks[i]
    const measured = from.analysis_status === "ready" && to.analysis_status === "ready" && !from.fixed_reason && !to.fixed_reason
    return {index:i+1,track1_occurrence:from.occurrence,track2_occurrence:to.occurrence,
      track1_name:from.name,track2_name:to.name,score:measured?.8:null,bpm_diff:measured?2:null,
      energy_diff:measured?to.energy-from.energy:null,
      components:{tempo:measured?.1:null,intensity:measured?.3:null,texture:measured?.2:null,chroma:measured?.2:null},
      evidence:{tempo:measured?.8:0,intensity:measured?.8:0,texture:measured?.8:0,chroma:measured?.8:0}}
  })
}
function job(tracks = original, order = [2, 1, 0, 3, 4, 5, 6], options = {}) {
  tracks = tracks.map(track => ({...track,analysis_status:track.fixed_reason
    ? track.kind === "track" ? track.fixed_reason === "Recording uncertain" ? "uncertain" : "error" : "fixed"
    : track.analysis_status ?? "ready"}))
  const sorted = order.map(i => tracks[i])
  const transitions = transitionRows(sorted)
  const eligible = tracks.filter(track => track.kind === "track").length
  return {
    playlist_id:playlistId,revision:"fixture",name:"Evening flow",status:"ready",can_restore:false,metadata_loaded:true,
    analyzed_count:tracks.filter(track => track.analysis_status === "ready" && !track.fixed_reason).length,
    profile:"smooth",first_occurrence:order.length?tracks[order[0]].occurrence:null,last_occurrence:null,
    completed:eligible,total:eligible,cached_count:0,recording_count:3,
    kept_count:tracks.filter(track=>track.fixed_reason).length,tracks,sorted_tracks:sorted,error:null,
    arrangement:sorted.length?{version:1,cost:.3,baseline_cost:.4,terms:{transition:.3,repetition:.4,monotony:.1},
      evaluations:100,assessed_edges:transitions.filter(t=>t.score!==null).length,total_edges:tracks.length-1,
      limited:false,unchanged:false,same_as_other_profile:null}:null,
    transitions,review:sorted.length?{original_assessed:transitionRows(tracks).filter(t=>t.score!==null).length,
      suggested_assessed:transitions.filter(t=>t.score!==null).length,total_edges:tracks.length-1,
      highlights:transitions.filter(t=>t.score!==null).slice(0,3).map(t=>({...t,text:t.energy_diff>0?
        "Intensity rises from this ending into the next opening.":"Intensity drops from this ending into the next opening."}))}:null,
    ...options,
  }
}
function orderWithPins(tracks, first, last) {
  const locked = new Map(tracks.flatMap((track, i) => track.fixed_reason ? [[i,i]] : []))
  if (first) locked.set(0, tracks.findIndex(track => track.occurrence === first))
  if (last) locked.set(tracks.length - 1, tracks.findIndex(track => track.occurrence === last))
  const used = new Set(locked.values())
  const remaining = tracks.map((_, i) => i).filter(i => !used.has(i))
  return tracks.map((_, i) => locked.has(i) ? locked.get(i) : remaining.shift())
}
async function choose(page, label, number) {
  const input = page.getByRole("combobox", { name: label, exact: true })
  await input.fill(`Originally #${number}`)
  await page.getByRole("option").waitFor()
  assert.equal(await page.getByRole("option").count(), 1)
  await input.press("ArrowDown")
  await input.press("Enter")
}
async function main() {
  const browser = await chromium.launch({ headless: true })
  try {
    for (const [theme, width, height] of [["light",1280,1000],["dark",390,844]]) {
      const context = await browser.newContext({ viewport:{width,height}, colorScheme:theme, reducedMotion:"reduce" })
      const page = await context.newPage()
      const errors = []
      page.on("pageerror", error => errors.push(error.message))
      page.on("console", message => { if (message.type() === "error" && message.text().includes("nativeButton")) errors.push(message.text()) })
      let current = job()
      let savedOrder = original.map(track => track.occurrence)
      let restoreOrder = null
      let failRestore = false
      const writes = []
      await page.route("**/*", async route => {
        const request = route.request(), url = new URL(request.url())
        if (url.hostname !== "127.0.0.1") return route.abort()
        if (!url.pathname.startsWith("/api/")) return route.continue()
        let body
        if (request.method() === "POST") {
          const payload = request.postDataJSON()
          writes.push({ path:url.pathname, payload })
          assert.equal(payload.revision, current.revision)
          if (url.pathname === "/api/job/sort") {
            assert(["smooth","variety"].includes(payload.profile))
            assert(payload.first_occurrence === null || payload.first_occurrence !== payload.last_occurrence)
            const indices = orderWithPins(current.tracks, payload.first_occurrence, payload.last_occurrence)
            const ordered = indices.map(i => current.tracks[i].occurrence)
            const same = current.profile !== payload.profile && current.first_occurrence === payload.first_occurrence &&
              current.last_occurrence === payload.last_occurrence && JSON.stringify(ordered) === JSON.stringify(current.sorted_tracks.map(t => t.occurrence))
            current = job(current.tracks, indices, { profile:payload.profile, first_occurrence:payload.first_occurrence, last_occurrence:payload.last_occurrence, revision:`revision-${writes.length}`, can_restore:current.can_restore })
            current.arrangement.unchanged = JSON.stringify(ordered) === JSON.stringify(savedOrder)
            current.arrangement.same_as_other_profile = same
          } else if (url.pathname === "/api/job/save") {
            restoreOrder = savedOrder.slice()
            savedOrder = current.sorted_tracks.map(t => t.occurrence)
            current = { ...current, status:"saved", can_restore:true, revision:`saved-${writes.length}` }
          } else if (url.pathname === "/api/job/restore") {
            assert(current.can_restore)
            current = failRestore
              ? { ...current, status:"error", can_restore:false, error:"This playlist changed on Spotify. Check it again before saving or restoring.", revision:`failed-${writes.length}` }
              : { ...current, status:"restored", can_restore:false, sorted_tracks:restoreOrder.map(id => current.tracks.find(t => t.occurrence === id)),
                  first_occurrence:null,last_occurrence:null,arrangement:null,review:null,transitions:[],revision:`restored-${writes.length}` }
            if (!failRestore) savedOrder = restoreOrder.slice()
            restoreOrder = null
          } else throw Error(`Unexpected request: ${url.pathname}`)
          body = url.pathname === "/api/job/sort"
            ? {...current,status:"sorting",sorted_tracks:[],transitions:[],arrangement:null}
            : {...current,status:url.pathname === "/api/job/restore" ? "restoring" : "saving",can_restore:false}
        } else if (url.pathname === "/api/session") body = { configured:true, user:{id:"test",name:"Test"}, csrf:"test" }
        else if (url.pathname === "/api/playlists") body = [{ id:playlistId, name:"Evening flow", total:current.metadata_loaded?current.tracks.length:original.length, image:null }]
        else if (url.pathname === "/api/job") body = current
        else throw Error(`Unexpected request: ${url.pathname}`)
        await route.fulfill({ json:body })
      })
      await page.goto(`http://127.0.0.1:5178/playlists/${playlistId}`)
      await page.getByRole("table").waitFor()
      await page.evaluate(() => document.fonts.ready)
      assert.equal(await page.locator("tbody tr").count(),7)
      assert(await page.getByRole("radio",{name:"Smooth",exact:true}).isChecked())
      assert(await page.getByRole("combobox",{name:"Last song",exact:true}).isDisabled())
      assert.equal(await page.getByText(/Kept in place ·/).count(),4)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-complete-preview.png`),fullPage:true})
      await choose(page,"First song",5)
      await page.getByRole("radio",{name:"More variety",exact:true}).focus()
      await page.keyboard.press("Space")
      assert(await page.getByRole("button",{name:"Save to Spotify",exact:true}).isDisabled())
      await page.getByRole("button",{name:"Arrange again",exact:true}).focus()
      await page.keyboard.press("Enter")
      await page.waitForFunction(() => [...document.querySelectorAll("button")].some(b => b.textContent === "Save to Spotify" && !b.disabled))
      await page.waitForFunction(() => document.activeElement?.textContent === "Playlist preview")
      assert.equal(writes[0].payload.profile,"variety")
      assert.equal(writes[0].payload.first_occurrence,original[4].occurrence)
      assert.equal(writes[0].payload.last_occurrence,null)
      await page.getByRole("tab",{name:"Suggested",exact:true}).focus()
      await page.keyboard.press("ArrowRight")
      await page.waitForFunction(() => document.activeElement?.textContent === "Original")
      await page.keyboard.press("Enter")
      await page.keyboard.press("ArrowRight")
      await page.waitForFunction(() => document.activeElement?.textContent === "Compare")
      await page.keyboard.press("Enter")
      await page.getByText("Tempo, key and transition estimates",{exact:true}).focus()
      await page.keyboard.press("Enter")
      await page.getByRole("heading",{name:"Between songs"}).waitFor()
      assert.equal(await page.getByRole("table",{name:"Song measurements in suggested order",exact:true}).locator("tbody tr").count(),7)
      assert.equal(await page.getByText("Not assessed",{exact:true}).count(),6)
      assert(!/NaN|undefined|%/.test(await page.locator("main").innerText()))
      const a11y = await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()
      assert.deepEqual(a11y.violations.map(v => ({id:v.id,nodes:v.nodes.length})),[])
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-details.png`),fullPage:true})
      await page.getByRole("button",{name:"Save to Spotify",exact:true}).focus()
      await page.keyboard.press("Enter")
      await page.getByRole("link",{name:"Open Spotify",exact:true}).waitFor()
      await page.getByText("Saved and verified on Spotify.",{exact:true}).waitFor()
      await page.getByRole("button",{name:"Restore previous order",exact:true}).waitFor()
      assert.match(await page.locator("#restore-limit").innerText(), /most recent save in this session/)
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-verified-save.png`),fullPage:true})
      await page.getByRole("button",{name:"Restore previous order",exact:true}).focus()
      await page.keyboard.press("Enter")
      await page.getByRole("heading",{name:"Restored order",exact:true}).waitFor()
      await page.waitForFunction(() => document.activeElement?.textContent === "Restored order")
      assert.equal(await page.getByRole("button",{name:"Restore previous order",exact:true}).count(),0)
      assert.equal(await page.getByRole("button",{name:"Save to Spotify",exact:true}).count(),0)
      assert.equal(await page.getByRole("table",{name:"Restored song order",exact:true}).locator("tbody tr").count(),7)
      assert.equal(await page.getByRole("combobox",{name:"First song",exact:true}).inputValue(),"")
      const restoredA11y = await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()
      assert.deepEqual(restoredA11y.violations.map(v => v.id),[])
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-restored-order.png`),fullPage:true})
      current = job(original,[2,1,0,3,4,5,6],{status:"saved",can_restore:true})
      failRestore = true
      await page.reload()
      await page.getByRole("button",{name:"Restore previous order",exact:true}).click()
      await page.getByText(/This playlist changed on Spotify/,{exact:false}).first().waitFor()
      assert.equal(await page.getByRole("button",{name:"Restore previous order",exact:true}).count(),0)
      await page.getByRole("button",{name:"Check again",exact:true}).waitFor()
      failRestore = false
      const five = original.slice(0,5)
      current = job(five,[])
      savedOrder = five.map(t => t.occurrence)
      await page.reload()
      await page.getByRole("button",{name:"Arrange playlist",exact:true}).waitFor()
      assert.equal(await page.getByPlaceholder("Choose for me",{exact:true}).count(),2)
      await choose(page,"First song",1)
      await choose(page,"Last song",1)
      await page.getByText("Choose different entries for the first and last songs.",{exact:true}).waitFor()
      assert(await page.getByRole("button",{name:"Arrange playlist",exact:true}).isDisabled())
      const first = page.getByRole("combobox",{name:"First song",exact:true})
      await page.locator('[data-slot="input-group"]').filter({has:first}).getByRole("button",{name:"Clear choice",exact:true}).click()
      await page.getByRole("button",{name:"Arrange playlist",exact:true}).click()
      await page.getByRole("button",{name:"Save to Spotify",exact:true}).waitFor()
      assert.equal(writes.at(-1).payload.first_occurrence,null)
      assert.equal(writes.at(-1).payload.last_occurrence,five[0].occurrence)
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-optional-pins.png`),fullPage:true})
      current = job(five,[0,1,2,3,4],{first_occurrence:null})
      current.arrangement.unchanged = true
      await page.reload()
      await page.getByText("This is already your saved order.",{exact:true}).waitFor()
      assert.equal(await page.getByRole("button",{name:"Save to Spotify",exact:true}).count(),0)
      await page.getByRole("radio",{name:"More variety",exact:true}).check()
      await page.getByRole("button",{name:"Arrange again",exact:true}).click()
      await page.getByText("Both styles found the same order with these song choices.",{exact:true}).waitFor()
      current = job(original.map(t => ({...t,fixed_reason:t.fixed_reason || "Couldn't analyze this song",key:null,bpm:null,energy:null})),[])
      await page.reload()
      await page.getByText(/None of these songs could be checked/).waitFor()
      assert.equal(await page.locator("tbody tr").count(),7)
      assert.equal(await page.getByRole("combobox").count(),0)
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-unchecked.png`),fullPage:true})
      current = job(original.map((t,i) => i === 0 ? {...t,fixed_reason:"Couldn't analyze this song"} : t),[])
      await page.reload()
      await page.getByRole("combobox",{name:"First song",exact:true}).waitFor()
      assert(await page.getByRole("combobox",{name:"First song",exact:true}).isDisabled())
      const timed = [
        {...original[0],name:"Long song",duration_ms:600000,energy:.2},
        {...original[2],name:"Short song",duration_ms:120000,energy:.8},
        {...original[3],duration_ms:180000},
      ]
      current = job(timed,[1,0,2])
      await page.reload()
      await page.getByText("1 transition worth checking",{exact:true}).focus()
      await page.keyboard.press("Enter")
      await page.getByText("Intensity drops from this ending into the next opening.",{exact:true}).waitFor()
      await page.getByRole("tab",{name:"Compare",exact:true}).click()
      await page.getByRole("figure").waitFor()
      assert.match(await page.getByRole("figure").getAttribute("aria-label"),/15:00/)
      await page.getByText("Song times and intensity",{exact:true}).focus()
      await page.keyboard.press("Enter")
      const originalTimes = page.getByRole("table",{name:"Original order times and intensity",exact:true})
      const suggestedTimes = page.getByRole("table",{name:"Suggested order times and intensity",exact:true})
      assert.match(await originalTimes.locator("tbody tr").nth(0).innerText(),/0:00.*10:00/s)
      assert.match(await originalTimes.locator("tbody tr").nth(1).innerText(),/10:00.*12:00/s)
      assert.match(await suggestedTimes.locator("tbody tr").nth(0).innerText(),/0:00.*2:00/s)
      assert.match(await suggestedTimes.locator("tbody tr").nth(1).innerText(),/2:00.*12:00/s)
      assert.match(await suggestedTimes.locator("tbody tr").nth(2).innerText(),/Unavailable/)
      if (width < 500) {
        const horizontal = originalTimes.locator("xpath=ancestor::*[@data-slot='scroll-area-viewport'][1]")
        await horizontal.focus()
        await page.keyboard.press("ArrowRight")
        await page.waitForFunction(() => document.querySelector('[aria-label="Original order times and intensity"][data-slot="scroll-area-viewport"]').scrollLeft > 0)
      }
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      const comparisonA11y = await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()
      assert.deepEqual(comparisonA11y.violations.map(v=>({id:v.id,nodes:v.nodes.length})),[])
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-time-comparison.png`),fullPage:true})
      current = job(timed.map((t,i)=>i===2?{...t,duration_ms:null}:t),[1,0,2])
      await page.reload()
      await page.getByRole("tab",{name:"Compare",exact:true}).click()
      await page.getByText(/The time comparison needs a known duration/).waitFor()
      assert.equal(await page.getByRole("figure").count(),0)
      await page.getByRole("tab",{name:"Suggested",exact:true}).click()
      assert.equal(await page.getByRole("table",{name:"Suggested song order",exact:true}).locator("tbody tr").count(),3)
      current = job([],[],{status:"analyzing",metadata_loaded:false,completed:0,total:0})
      await page.reload()
      await page.getByRole("heading",{name:"Loading playlist",exact:true}).waitFor()
      const pending = original.map(t=>t.kind==="track"?{...t,fixed_reason:null,analysis_status:t.id===original[0].id?"matching":"pending",key:null,bpm:null,energy:null}:t)
      current = job(pending,[],{status:"analyzing",completed:0})
      await page.getByRole("table",{name:"Songs in your playlist",exact:true}).waitFor()
      assert.equal(await page.getByRole("table",{name:"Songs in your playlist",exact:true}).locator("tbody tr").count(),7)
      assert.equal(await page.getByText("Finding recording",{exact:true}).count(),2)
      assert.equal(await page.getByRole("radio").count(),0)
      const viewport = await page.locator('[data-slot="scroll-area-viewport"][aria-label="Songs in your playlist"]').elementHandle()
      await viewport.focus()
      current = job(pending.map(t=>t.analysis_status==="matching"?{...t,analysis_status:"analyzing"}:t),[],{status:"analyzing",completed:0})
      await page.getByText("Measuring audio",{exact:true}).first().waitFor()
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-analysis-progress.png`),fullPage:true})
      current = job(original,[])
      await page.getByRole("radio",{name:"Smooth",exact:true}).waitFor()
      assert(await viewport.evaluate(element=>element.isConnected && element===document.activeElement))
      assert.match(await page.getByRole("status").first().innerText(),/3 checked successfully/)
      current = job(pending,[],{status:"analyzing",completed:0})
      await page.reload()
      await page.getByRole("table",{name:"Songs in your playlist",exact:true}).waitFor()
      const priorWrites = writes.length
      await page.getByRole("link",{name:"Your playlists",exact:true}).click()
      await page.getByRole("link",{name:/Evening flow/}).click()
      await page.getByRole("table",{name:"Songs in your playlist",exact:true}).waitFor()
      assert.equal(writes.length,priorWrites)
      current = job(pending.map(t=>t.fixed_reason?t:{...t,analysis_status:"error",fixed_reason:"Check interrupted"}),[],{status:"error",completed:0,error:"Checking stopped. Check the playlist again."})
      await page.reload()
      await page.getByRole("table",{name:"Order last loaded",exact:true}).waitFor()
      assert.equal(await page.getByRole("table",{name:"Order last loaded",exact:true}).locator("tbody tr").count(),7)
      assert.equal(await page.getByRole("button",{name:"Save to Spotify",exact:true}).count(),0)
      await page.getByRole("button",{name:"Check again",exact:true}).waitFor()
      await page.screenshot({path:path.join(__dirname,`${theme}-${width}-interrupted-check.png`),fullPage:true})
      assert.deepEqual(errors,[])
      console.log(`${theme} ${width}px: profiles/pins, focus, complete progress/recovery, elapsed-time comparison, missing durations, notes, verified save/restore, stale restore rejection, no-op states and axe checks passed`)
      await context.close()
    }
  } finally { await browser.close() }
}
main().catch(error => {console.error(error);process.exitCode=1})
