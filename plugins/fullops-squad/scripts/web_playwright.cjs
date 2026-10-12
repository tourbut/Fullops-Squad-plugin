/* Optional Playwright bridge. JSON on stdin/stdout; page text never becomes executable code. */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const readline = require('node:readline');
const DOM = fs.readFileSync(path.join(__dirname, 'web_dom.js'), 'utf8');
const SELECTOR = 'button,a[href],input:not([type=hidden]),textarea,select,[role],[contenteditable=true],summary';
let browser, context, page, safety, pending, identity;
let blocked = 0;

async function snapshot() {
  return page.evaluate(`(${DOM})(false)`);
}

function destinationAllowed(url) {
  try { return safety.allowed_origins.includes(new URL(url).origin); } catch { return false; }
}

async function handle(message) {
  const { action, data = {}, timeout = 30000 } = message;
  if (page) page.setDefaultTimeout(Math.max(1, timeout));
  if (action === 'start') {
    const packageFile = path.resolve(data.package_file);
    const metadata = JSON.parse(fs.readFileSync(packageFile, 'utf8'));
    if (metadata.name !== '@playwright/cli' || metadata.version !== data.version) throw new Error('package_version_mismatch');
    const load = createRequire(packageFile);
    const { chromium } = load('playwright');
    const actualVersion = load('playwright/package.json').version;
    if (actualVersion !== metadata.dependencies.playwright) throw new Error('runtime_version_mismatch');
    safety = data.safety;
    browser = await chromium.launch({ headless: !data.headed, timeout,
      ...(data.executable ? { executablePath: data.executable } : {}) });
    context = await browser.newContext({ viewport: { width: 1280, height: 900 },
      serviceWorkers: 'block', acceptDownloads: false });
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      const readAsset = ['GET', 'HEAD'].includes(request.method()) &&
        ['document', 'script', 'stylesheet', 'image', 'font', 'media', 'manifest'].includes(request.resourceType());
      const approved = safety.requests.some(rule => rule.method === request.method() && rule.path === url.pathname);
      if (destinationAllowed(url.href) && (readAsset || approved)) await route.continue();
      else { blocked++; await route.abort('blockedbyclient'); }
    });
    await context.routeWebSocket('**/*', socket => { blocked++; socket.close(); });
    page = await context.newPage();
    context.on('page', popup => { if (popup !== page) { blocked++; popup.close().catch(() => {}); } });
    page.on('dialog', dialog => dialog.dismiss());
    identity = { name: 'playwright', cli_version: metadata.version, version: actualVersion,
      browser_version: browser.version(), request_filtering: true, attached: false };
    return identity;
  }
  if (action === 'open') {
    if (!destinationAllowed(data.url)) throw new Error('origin_not_allowed');
    await page.goto(data.url, { waitUntil: 'domcontentloaded', timeout });
    return true;
  }
  if (action === 'snapshot') return snapshot();
  if (action === 'eval') return page.evaluate(data.expression);
  if (action === 'preflight') {
    pending = null;
    const current = await snapshot();
    if (current.digest !== data.page.digest || current.url !== data.page.url) return 'stale_state';
    if (!destinationAllowed(current.url)) return 'origin_not_allowed';
    if (data.operation === 'scroll_down') { pending = { digest: current.digest }; return null; }
    const target = current.elements.find(e => e.ref === data.ref);
    if (!target || !target.visible || target.occluded || target.sensitive || target.state.includes('disabled=true')) return 'not_actionable';
    if (target.tag === 'SELECT') return 'unsupported_widget';
    const destinations = [target.href, ...(['fill_submit', 'press_enter'].includes(data.operation) ? [target.form_action] : [])];
    if (destinations.some(url => url && !destinationAllowed(url))) return 'origin_not_allowed';
    const index = Number(data.ref.slice(1));
    const element = await page.locator(SELECTOR).nth(index).elementHandle();
    if (!element) return 'target_not_found';
    // A handle pins this node; subsequent DOM replacement cannot redirect the action to a different node.
    pending = { digest: current.digest, element, ref: data.ref };
    return null;
  }
  if (action === 'act') {
    const saved = pending;
    pending = null;
    if (!saved || (await snapshot()).digest !== saved.digest || data.ref && saved.ref !== data.ref) return 'error: stale_state';
    const element = saved.element;
    if (data.operation === 'scroll_down') await page.evaluate(() => window.scrollBy(0, 800));
    else if (data.operation === 'click') await element.click({ timeout });
    else if (data.operation === 'check') await element.setChecked(!(await element.isChecked()), { timeout });
    else if (data.operation === 'fill' || data.operation === 'fill_submit') {
      await element.fill(data.value, { timeout });
      if (data.operation === 'fill_submit') await element.press('Enter', { timeout });
    } else if (data.operation === 'press_enter') await element.press('Enter', { timeout });
    else throw new Error('unsupported_operation');
    if (!destinationAllowed(page.url())) return 'error: origin_not_allowed';
    return 'ok';
  }
  if (action === 'close') {
    await browser?.close();
    return { ...identity, blocked_requests: blocked };
  }
  throw new Error('unsupported_bridge_action');
}

const input = readline.createInterface({ input: process.stdin });
(async () => {
  for await (const line of input) {
    let message;
    try {
      message = JSON.parse(line);
      const result = await handle(message);
      process.stdout.write(JSON.stringify({ id: message.id, ok: true, result }) + '\n');
    } catch (error) {
      // Error messages can embed URLs, values or page text; expose only a bounded error category.
      const code = ['package_version_mismatch', 'runtime_version_mismatch', 'origin_not_allowed', 'unsupported_bridge_action', 'unsupported_operation'].includes(error.message) ? error.message : error.name;
      process.stdout.write(JSON.stringify({ id: message?.id, ok: false, error: code }) + '\n');
    }
    if (message?.action === 'close') break;
  }
  input.close();
  process.stdin.destroy();
  await browser?.close();
})().catch(() => { process.exitCode = 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await browser?.close(); process.exit(); });
