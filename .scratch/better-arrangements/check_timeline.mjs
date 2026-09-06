import assert from "node:assert/strict"
import { compareTimelines, listeningTimeline, measuredIntensity, elapsedTime } from "../../frontend/src/lib/review.ts"
const track = (id, duration_ms, energy) => ({occurrence:id,id,name:id,artist:"Example",original_position:0,kind:"track",fixed_reason:null,analysis_status:"ready",duration_ms,energy,bpm:null,key:null})
const long = track("Long", 600000, .2)
const short = track("Short", 120000, .8)
const comparison = compareTimelines([long,short],[short,long])
assert.equal(comparison.total,720000)
assert.equal(comparison.original[1].start,600000)
assert.equal(comparison.suggested[1].start,120000)
assert.deepEqual(comparison.points.filter(p => p.elapsed === 120000).map(p => [p.original,p.suggested]), [[.2,.8],[.2,.2]])
assert.deepEqual(comparison.points.filter(p => p.elapsed === 600000).map(p => [p.original,p.suggested]), [[.2,.2],[.8,.2]])
const unknown = {...short, fixed_reason:"Unavailable", analysis_status:"fixed"}
const tail = track("Tail",180000,.6)
const gaps = compareTimelines([long,unknown,tail],[long,unknown,tail])
assert.deepEqual(gaps.points.filter(p => p.elapsed === 600000).map(p => p.original),[.2,null])
assert.deepEqual(gaps.points.filter(p => p.elapsed === 720000).map(p => p.original),[null,.6])
for (const duration_ms of [null,0,-1,Number.NaN,Number.MAX_SAFE_INTEGER+1]) {
  assert.equal(listeningTimeline([{...short,duration_ms}]),null)
  assert.equal(compareTimelines([long,{...short,duration_ms}],[short,long]),null)
}
assert.equal(measuredIntensity({...short,analysis_status:"uncertain"}),null)
assert.equal(measuredIntensity({...short,energy:0}),0)
assert.equal(measuredIntensity({...short,energy:Number.NaN}),null)
assert.equal(elapsedTime(0),"0:00")
assert.equal(elapsedTime(61000),"1:01")
assert.equal(elapsedTime(3600000),"1:00:00")
console.log("Timeline checks passed: elapsed durations, boundary steps, unknown spans, invalid durations and text times.")
