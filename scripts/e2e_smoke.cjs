/**
 * End-to-end smoke test of the full user workflow in a real browser.
 *
 * Prerequisites: backend on :8000 and frontend dev server on :5173.
 * Usage: node scripts/e2e_smoke.cjs [path/to/file.pdf] [screenshotDir]
 */
const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

const BASE = process.env.APP_URL || 'http://localhost:5173'
const pdf = path.resolve(process.argv[2] || path.join(__dirname, '../backend/samples/photosynthesis.pdf'))
const shots = process.argv[3] ? path.resolve(process.argv[3]) : null

async function shot(page, name) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: false })
}

;(async () => {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: shots ? 2 : 1, acceptDownloads: true })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))

  // 1. Landing
  await page.goto(BASE)
  await page.getByRole('heading', { name: /smart, editable slides/i }).waitFor()
  await page.waitForTimeout(500)
  await shot(page, '01-landing')
  console.log('✓ landing page')

  // 2. Upload
  await page.getByRole('link', { name: /convert a pdf/i }).click()
  await page.locator('input[type=file]').setInputFiles(pdf)
  await shot(page, '02-upload')
  await page.getByRole('button', { name: /upload & continue/i }).click()
  await page.waitForURL(/\/configure\//)
  console.log('✓ upload')

  // 3. Configure
  await page.getByRole('heading', { name: /configure your presentations/i }).waitFor()
  await page.getByRole('button', { name: /professional blue/i }).click()
  await page.waitForTimeout(300)
  await shot(page, '03-configure')
  await page.getByRole('button', { name: /generate presentations/i }).click()
  await page.waitForURL(/\/processing\//)
  await shot(page, '04-processing')
  console.log('✓ configure + processing started')

  // 4. Preview
  await page.waitForURL(/\/preview\//, { timeout: 120000 })
  await page.getByRole('heading', { name: /edit slide 1/i }).waitFor()
  await page.waitForTimeout(500)
  // select slide 3 and edit its title + first bullet
  await page.locator('aside[aria-label="Slides"] > ol > li button').nth(2).click()
  const title = page.locator('#slide-title')
  await title.fill('Edited In The Browser')
  const firstBullet = page.getByLabel('Bullet points 1')
  if (await firstBullet.count()) await firstBullet.fill('A bullet point written during the E2E test')
  await page.getByText('All changes saved').waitFor({ timeout: 10000 })
  await shot(page, '05-preview-editor')
  console.log('✓ edit + autosave')

  // reorder: move slide 3 up
  await page.getByRole('button', { name: 'Move slide up' }).click()
  await page.getByRole('heading', { name: /edit slide 2/i }).waitFor()
  console.log('✓ reorder')

  // regenerate slide 4
  await page.locator('aside[aria-label="Slides"] > ol > li button').nth(3).click()
  await page.getByRole('button', { name: 'Regenerate', exact: true }).click()
  await page.getByText(/regenerated from the source pages/i).waitFor({ timeout: 20000 })
  console.log('✓ regenerate')

  // delete last slide
  const countBefore = await page.locator('aside[aria-label="Slides"] > ol > li').count()
  page.once('dialog', (d) => d.accept())
  await page.locator('aside[aria-label="Slides"] > ol > li button').last().click()
  await page.getByRole('button', { name: /^delete$/i }).click()
  await page.getByText('Slide deleted').waitFor()
  const countAfter = await page.locator('aside[aria-label="Slides"] > ol > li').count()
  if (countAfter !== countBefore - 1) throw new Error(`delete failed ${countBefore} -> ${countAfter}`)
  console.log('✓ delete')

  // switch template
  await page.getByLabel('Template').selectOption('dark_academic')
  await page.getByText(/template changed/i).waitFor()
  await page.locator('aside[aria-label="Slides"] > ol > li button').first().click()
  await page.waitForTimeout(400)
  await shot(page, '06-preview-dark-academic')
  console.log('✓ template switch')

  // download from preview and check the file reflects the edit
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /download pptx/i }).click()])
  const out = path.join(require('os').tmpdir(), dl.suggestedFilename())
  await dl.saveAs(out)
  const size = fs.statSync(out).size
  if (size < 10000) throw new Error('downloaded file too small')
  console.log(`✓ download ${dl.suggestedFilename()} (${size} bytes) -> ${out}`)

  // 5. Download page
  await page.getByRole('button', { name: /finish/i }).click()
  await page.waitForURL(/\/download\//)
  await page.getByRole('heading', { name: /presentations are ready/i }).waitFor()
  await shot(page, '07-download')
  const [dl2] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /download \.pptx/i }).last().click()])
  console.log(`✓ download page: ${dl2.suggestedFilename()}`)

  // dark mode + mobile landing
  await page.goto(BASE)
  await page.getByRole('button', { name: /switch to dark theme/i }).click()
  await page.waitForTimeout(400)
  await shot(page, '08-landing-dark')
  await page.getByRole('button', { name: /switch to light theme/i }).click()
  const mobile = await context.newPage()
  await mobile.setViewportSize({ width: 390, height: 844 })
  await mobile.goto(BASE + '/upload')
  await mobile.waitForTimeout(400)
  await shot(mobile, '09-upload-mobile')
  const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  if (overflow) throw new Error('horizontal overflow on mobile')
  console.log('✓ dark mode + mobile layout')

  if (errors.length) {
    console.log('Browser errors:', errors)
    process.exitCode = 1
  }
  console.log('DOWNLOADED_FILE=' + out)
  await browser.close()
})().catch((e) => {
  console.error('E2E FAILED:', e)
  process.exit(1)
})
