const { chromium } = require('playwright')
const AxeBuilder = require('@axe-core/playwright').default
const assert = require('node:assert/strict')
const path = require('node:path')
const cookies = '# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t4102444800\tSID\tfixture\n'
async function main() {
 const browser = await chromium.launch({headless:true})
 try {
  for (const [theme,width] of [['light',1280],['dark',390],['light',320]]) {
   const context = await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:'reduce'})
   const page = await context.newPage(), errors = []
   page.on('pageerror', error=>errors.push(error.message))
   let state = {mode:'server',server_source:'anonymous',browser:null,node_available:true,scripts_available:true,yt_dlp_version:'2026.08.19'}
   let reject = false
   const writes = []
   await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url())
    if (url.hostname !== '127.0.0.1') return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (url.pathname === '/api/session') return route.fulfill({json:{configured:true,user:{id:'test',name:'Test'},csrf:'fixture'}})
    if (url.pathname === '/api/youtube') {
     if (request.method() === 'POST') {
      assert.equal(request.headers()['x-csrf-token'],'fixture')
      const payload = request.postDataJSON(); writes.push(payload)
      if (reject) return route.fulfill({status:422,json:{detail:'Could not read the cookie file.'}})
      state = {...state, mode:payload.mode}
     }
     return route.fulfill({json:state})
    }
    throw Error(`Unexpected API ${url.pathname}`)
   })
   await page.goto('http://127.0.0.1:5178/youtube')
   await page.getByRole('heading',{name:'YouTube access',exact:true}).waitFor()
   await page.getByText('Checking public recordings without cookies.',{exact:true}).waitFor()
   assert.equal(await page.getByRole('link',{name:'Get cookies.txt LOCALLY',exact:true}).getAttribute('href'),'https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc')
   await page.getByLabel('YouTube cookie file',{exact:true}).setInputFiles({name:'cookies.txt',mimeType:'text/plain',buffer:Buffer.from(cookies)})
   await page.getByRole('button',{name:'Use cookie file',exact:true}).focus()
   await page.keyboard.press('Enter')
   await page.getByText('Using your uploaded cookies for this session.',{exact:true}).waitFor()
   assert.deepEqual(writes.at(-1),{mode:'upload',cookies})
   assert(!await page.getByLabel('YouTube cookie file',{exact:true}).inputValue())
   await page.getByRole('button',{name:'Use without cookies',exact:true}).focus()
   await page.keyboard.press('Enter')
   await page.getByText('Checking public recordings without cookies.',{exact:true}).waitFor()
   assert.deepEqual(writes.at(-1),{mode:'anonymous',cookies:''})
   await page.getByText('Use Chrome directly or configure the server',{exact:true}).focus()
   await page.keyboard.press('Enter')
   assert(await page.locator('details').getAttribute('open') !== null)
   assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth))
   assert.deepEqual((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations.map(v=>v.id),[])
   await page.screenshot({path:path.join(__dirname,`${theme}-${width}-youtube-access.png`),fullPage:true})
   state = {...state,mode:'server',server_source:'browser',browser:'chrome',scripts_available:false}
   await page.reload()
   await page.getByRole('button',{name:'Use server browser',exact:true}).waitFor()
   await page.getByText('Using chrome on the app server.',{exact:true}).waitFor()
   await page.getByText(/YouTube player support is incomplete/).waitFor()
   reject = true
   await page.getByLabel('YouTube cookie file',{exact:true}).setInputFiles({name:'bad.txt',mimeType:'text/plain',buffer:Buffer.from('bad')})
   await page.getByRole('button',{name:'Use cookie file',exact:true}).click()
   await page.getByRole('alert').filter({hasText:'Could not read the cookie file.'}).waitFor()
   assert.equal(state.mode,'server')
   assert.deepEqual(errors,[])
   console.log(`${theme} ${width}px: optional anonymous mode, upload/removal, server browser setup, error feedback, keyboard and axe passed`)
   await context.close()
  }
 } finally {await browser.close()}
}
main().catch(error=>{console.error(error);process.exitCode=1})
