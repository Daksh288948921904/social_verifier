import { chromium } from 'playwright'

const shotsDir = 'scripts/screenshots'
await import('node:fs/promises').then((fs) => fs.mkdir(shotsDir, { recursive: true }))

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
page.on('console', (msg) => {
  if (msg.type() === 'error') console.log('[console.error]', msg.text())
})
page.on('pageerror', (err) => console.log('[pageerror]', err.message))

console.log('--- Navigating to Start Session page ---')
await page.goto('http://localhost:5176/', { waitUntil: 'networkidle' })
await page.waitForSelector('text=Live Cutter')
await page.screenshot({ path: `${shotsDir}/01-start-page.png` })
console.log('Start page loaded OK')

console.log('--- Creating a session ---')
await page.fill('input[placeholder*="youtube"]', 'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8')
await page.click('button:has-text("Start")')
await page.waitForURL(/\/sessions\//, { timeout: 15000 })
await page.waitForSelector('text=Clips')
await page.screenshot({ path: `${shotsDir}/02-session-dashboard.png` })
console.log('Session dashboard loaded OK, url =', page.url())

// give it a few seconds to receive websocket events (transcript ticks / errors)
await page.waitForTimeout(6000)
await page.screenshot({ path: `${shotsDir}/03-session-dashboard-after-wait.png` })

const bodyText = await page.textContent('body')
console.log('--- Dashboard contains "Live" badge:', bodyText.includes('Live'))
console.log('--- Dashboard contains "No clips yet":', bodyText.includes('No clips yet'))

await browser.close()
console.log('--- DONE ---')
