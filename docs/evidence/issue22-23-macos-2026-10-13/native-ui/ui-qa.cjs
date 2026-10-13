const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.argv[2]);
const output = process.argv[3];
const source = process.argv[4];
fs.mkdirSync(output, { recursive: true });
const server = http.createServer((request, response) => {
  const host = request.url.slice(1);
  if (request.method !== 'GET' || !['codex', 'grok'].includes(host)) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end(fs.readFileSync(path.join(source, `${host}.html`)));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  const report = { browser: browser.version(), source, isolation: 'new no-credential contexts; only fixture GET allowed', results: [] };
  try {
    for (const host of ['codex', 'grok']) for (const width of [320, 390, 1280]) {
      const context = await browser.newContext({ viewport: { width, height: 800 }, isMobile: width < 768, reducedMotion: 'reduce' });
      const denied = [];
      await context.route('**/*', route => {
        if (route.request().url() === `${origin}/${host}` && route.request().method() === 'GET') return route.continue();
        denied.push({ url: route.request().url(), method: route.request().method() });
        return route.abort();
      });
      const page = await context.newPage();
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      const checks = [];
      const check = (name, passed, actual) => checks.push({ name, passed, actual });
      await page.goto(`${origin}/${host}`);
      await page.waitForLoadState('networkidle');
      check('mobile-layout-viewport', await page.evaluate(() => innerWidth) === width, await page.evaluate(() => innerWidth));
      check('no-horizontal-overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: innerWidth })));
      check('initial-empty', await page.locator('#list li').count() === 0);
      check('initial-light', await page.locator('html').getAttribute('data-theme') === 'light');
      await page.screenshot({ path: path.join(output, `${host}-${width}-light.png`), fullPage: true });
      await page.locator('#theme').click();
      check('theme-dark', await page.locator('html').getAttribute('data-theme') === 'dark');
      check('pressed-dark', await page.locator('#theme').getAttribute('aria-pressed') === 'true');
      await page.screenshot({ path: path.join(output, `${host}-${width}-dark.png`), fullPage: true });
      await page.locator('#theme').click();
      check('theme-repeat-light', await page.locator('html').getAttribute('data-theme') === 'light');
      await page.locator('#theme').focus();
      await page.keyboard.press('Enter');
      check('keyboard-enter-dark', await page.locator('html').getAttribute('data-theme') === 'dark');
      await page.keyboard.press('Space');
      check('keyboard-space-light', await page.locator('html').getAttribute('data-theme') === 'light');
      check('visible-keyboard-focus', await page.locator('#theme').evaluate(el => el === document.activeElement && getComputedStyle(el).outlineStyle !== 'none' && parseFloat(getComputedStyle(el).outlineWidth) > 0));
      check('reduced-motion', await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches && [...document.querySelectorAll('*')].every(el => getComputedStyle(el).transitionDuration.split(',').every(x => parseFloat(x) === 0))));
      await page.getByRole('textbox', { name: 'New todo' }).fill('milk');
      await page.getByRole('textbox', { name: 'New todo' }).press('Enter');
      check('single-enter-submit', await page.evaluate(() => window.submits) === 1, await page.evaluate(() => window.submits));
      check('one-created-row', await page.locator('#list li').count() === 1);
      await page.getByRole('checkbox', { name: 'Toggle milk' }).check();
      check('checkbox-complete', await page.getByRole('checkbox', { name: 'Toggle milk' }).isChecked());
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      check('repeat-click-one-more-submit', await page.evaluate(() => window.submits) === 2);
      check('disabled-control', await page.getByRole('button', { name: 'Restricted', exact: true }).isDisabled());
      check('no-runtime-errors', errors.length === 0, errors);
      report.results.push({ host, width, checks, denied });
      await context.close();
    }
  } finally { await browser.close(); server.close(); }
  report.failed = report.results.flatMap(row => row.checks.filter(check => !check.passed).map(check => ({ host: row.host, width: row.width, ...check })));
  report.passed = report.failed.length === 0;
  fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ passed: report.passed, failures: report.failed }));
  process.exitCode = report.passed ? 0 : 1;
})().catch(error => { server.close(); console.error(error); process.exitCode = 1; });
