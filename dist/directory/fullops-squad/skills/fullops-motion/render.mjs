#!/usr/bin/env node
// Renders a single-file HTML motion piece whose page defines window.seek(t): every frame is a pure function of t.
// Playwright (or playwright-core) comes from the video folder's node_modules; FFmpeg from PATH or --ffmpeg.
//   node render.mjs index.html --out renders/v01/clip.mp4 --width 1920 --height 1080 --fps 60 --duration 15 [--subframes 4] [--audio mix.wav]
//   node render.mjs index.html --stills 0,0.5,1 --out qa/v01/stills --width 1920 --height 1080
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'

const fail = message => { console.error(`render.mjs: ${message}`); process.exit(2) }
let opt, positionals
try {
  ({ values: opt, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: 'string' }, width: { type: 'string' }, height: { type: 'string' }, fps: { type: 'string', default: '60' },
    duration: { type: 'string' }, subframes: { type: 'string', default: '1' }, stills: { type: 'string' },
    audio: { type: 'string' }, ffmpeg: { type: 'string', default: 'ffmpeg' }, channel: { type: 'string' }, crf: { type: 'string', default: '16' },
  },
  }))
} catch (error) { fail(error.message) }
const number = (name, min) => {
  const value = Number(opt[name])
  if (!Number.isFinite(value) || value < min) fail(`--${name} must be a number >= ${min}`)
  return value
}
if (positionals.length !== 1 || !opt.out) fail('usage: render.mjs <index.html> --out <file|dir> --width W --height H (--duration S | --stills t,...)')
const width = number('width', 1), height = number('height', 1)
const fps = number('fps', 1), subframes = Math.round(number('subframes', 1))
const stills = opt.stills?.split(',').map(Number)
if (stills?.some(t => !Number.isFinite(t) || t < 0)) fail('--stills takes seconds such as 0,0.5,1')
const duration = stills ? 0 : number('duration', 1 / fps)
if (!stills && existsSync(opt.out)) fail(`${opt.out} exists; render to a new version path`)

const require = createRequire(join(process.cwd(), 'noop.js'))
let chromium
for (const name of ['playwright', 'playwright-core']) {
  try { ({ chromium } = require(name)); break } catch { /* try the next package */ }
}
if (!chromium) fail('playwright is not installed in this folder (npm i -D playwright, or playwright-core with --channel chrome)')

const browser = await chromium.launch(opt.channel ? { channel: opt.channel } : {})
try {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 })
  await page.goto(pathToFileURL(resolve(positionals[0])).href)
  await page.evaluate(() => document.fonts.ready)
  if (!(await page.evaluate(() => typeof window.seek === 'function'))) throw new Error('the page has no window.seek(t)')
  // seek may return a promise (a canvas that draws asynchronously); a frame waits for it and one paint.
  const shot = async t => {
    await page.evaluate(async t => { await window.seek(t); await new Promise(requestAnimationFrame) }, t)
    return page.screenshot({ type: 'png', clip: { x: 0, y: 0, width, height } })
  }

  if (stills) {
    mkdirSync(opt.out, { recursive: true })
    for (const t of stills) writeFileSync(join(opt.out, `t${t.toFixed(3)}.png`), await shot(t))
  } else {
    mkdirSync(dirname(resolve(opt.out)), { recursive: true })
    const frames = Math.round(duration * fps)
    const rate = fps * subframes
    // Subframes average into one frame (motion blur): tmix over each group, keep the group's last mix.
    const blur = subframes > 1 ? `tmix=frames=${subframes},select='eq(mod(n\\,${subframes})\\,${subframes - 1})',` : ''
    const args = ['-v', 'error', '-n', '-f', 'image2pipe', '-framerate', String(rate), '-i', '-',
      ...(opt.audio ? ['-i', opt.audio] : []),
      '-vf', `${blur}setpts=N/(${fps}*TB),scale=out_color_matrix=bt709:out_range=tv,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv`,
      '-r', String(fps),
      '-c:v', 'libx264', '-crf', opt.crf, '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
      ...(opt.audio ? ['-c:a', 'aac'] : []), '-t', String(frames / fps), opt.out]
    const ffmpeg = spawn(opt.ffmpeg, args, { stdio: ['pipe', 'inherit', 'inherit'] })
    const done = new Promise((ok, no) => { ffmpeg.on('error', no); ffmpeg.on('close', code => (code === 0 ? ok() : no(new Error(`ffmpeg exited ${code}`)))) })
    // A dead ffmpeg is reported by the awaits below; until one runs, neither signal may crash past browser.close().
    done.catch(() => {})
    ffmpeg.stdin.on('error', () => {})
    try {
      for (let n = 0; n < frames * subframes; n++) {
        if (!ffmpeg.stdin.write(await shot(n / rate))) await Promise.race([new Promise(ok => ffmpeg.stdin.once('drain', ok)), done])
      }
    } catch (error) {
      ffmpeg.kill() // a failed frame leaves ffmpeg waiting on stdin
      await done.catch(() => {})
      throw error
    }
    ffmpeg.stdin.end()
    await done
  }
  console.log(JSON.stringify({ out: opt.out, width, height, fps, ...(stills ? { stills } : { duration, frames: Math.round(duration * fps), subframes }) }))
} catch (error) {
  console.error(`render.mjs: ${error.message}`)
  process.exitCode = 1
} finally {
  await browser.close()
}
