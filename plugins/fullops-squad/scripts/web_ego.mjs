/* Optional ego-browser bridge. ego-browser hands a script no stdin, so each call is one process:
   the request comes from a file and the answer is one marked stdout line. Page text never becomes code. */
import fs from 'node:fs/promises';

const MARK = 'FULLOPS_EGO ';
const SELECTOR = 'button,a[href],input:not([type=hidden]),textarea,select,[role],[contenteditable=true],summary';
const KNOWN = ['origin_not_allowed', 'unsupported_bridge_action', 'unsupported_operation'];
const DOM = await fs.readFile(new URL('./web_dom.js', import.meta.url), 'utf8');

const allowed = (safety, url) => { try { return safety.allowed_origins.includes(new URL(url).origin); } catch { return false; } };
const probe = (page, activeOnly) => page.evaluate(`(${DOM})(${activeOnly})`);
// ego counts `nth` over every match in document order, as web_dom.js numbers its refs.
const selector = ref => `css=${SELECTOR} >> nth=${Number(String(ref).slice(1))}`;

function vet(current, data) {
  if (current.digest !== data.page.digest || current.url !== data.page.url) return 'stale_state';
  if (!allowed(data.safety, current.url)) return 'origin_not_allowed';
  if (data.operation === 'scroll_down') return null;
  // ego's CSS search also enters open shadow roots, so an index could name another node there.
  if (current.unsupported.includes('shadow_roots')) return 'unsupported_widget';
  const target = current.elements.find(e => e.ref === data.ref);
  if (!target || !target.visible || target.occluded || target.sensitive || target.state.includes('disabled=true')) return 'not_actionable';
  if (target.tag === 'SELECT') return 'unsupported_widget';
  if ([target.href, target.form_action].some(url => url && !allowed(data.safety, url))) return 'origin_not_allowed';
  return null;
}

async function handle({ action, space, data = {}, timeout = 30000 }) {
  const task = await taskSpace(space);
  if (action === 'close') { await task.finish({ keep: [] }); return true; }
  const page = task.page('p1');
  if (action === 'open') {
    if (!allowed(data.safety, data.url)) throw new Error('origin_not_allowed');
    await page.goto(data.url);
    return true;
  }
  if (action === 'snapshot') return probe(page, false);
  if (action === 'eval') return page.evaluate(data.expression);
  if (action !== 'preflight' && action !== 'act') throw new Error('unsupported_bridge_action');
  const current = await probe(page, false);
  const problem = vet(current, data);
  if (action === 'preflight') return problem;
  if (problem) return { outcome: 'error: ' + problem };
  const wait = { timeout: Math.min(timeout, 10000) };
  let receipt = {};
  if (data.operation === 'scroll_down') await page.evaluate('window.scrollBy(0, 800)');
  else {
    const target = current.elements.find(e => e.ref === data.ref);
    await page.focus(selector(data.ref));
    const active = (await probe(page, true)).active;
    if (!active || active.role !== target.role || active.name !== target.name) return { outcome: 'error: focused_target_mismatch' };
    if (data.operation === 'click' || data.operation === 'check') receipt = await page.click(selector(data.ref), wait);
    else if (data.operation === 'fill' || data.operation === 'fill_submit') {
      await page.fill(selector(data.ref), data.value);
      if (data.operation === 'fill_submit') await page.press(selector(data.ref), 'Enter');
    } else if (data.operation === 'press_enter') await page.press(selector(data.ref), 'Enter');
    else throw new Error('unsupported_operation');
  }
  let popups = 0;
  for (const popup of receipt?.popups ?? []) { await task.page(popup.label).close().catch(() => {}); popups++; }
  if ((await page.info()).dialog) await page.dismissDialog();
  if (!allowed(data.safety, await page.url())) return { outcome: 'error: origin_not_allowed', popups };
  return { outcome: 'ok', popups };
}

const reply = value => console.log(MARK + JSON.stringify(value));
try {
  const request = JSON.parse(await fs.readFile(globalThis.__fullopsEgoRequest, 'utf8'));
  reply({ ok: true, result: await handle(request) });
} catch (error) {
  // Error messages can embed URLs, values or page text; expose only a bounded category.
  reply({ ok: false, error: KNOWN.includes(error.message) ? error.message : String(error.code || error.name).slice(0, 80) });
}
