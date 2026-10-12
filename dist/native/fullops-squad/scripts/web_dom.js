// Shared local inspection. Raw DOM and input values stay in the browser; only their digest leaves it.
async (activeOnly = false) => {
  if (!globalThis.crypto?.subtle) throw new Error('secure_context_required');
  const key = '__fullopsWebObservationV1';
  if (!globalThis[key]) {
    let revision = 0;
    const observer = new MutationObserver(() => revision++);
    observer.observe(document, {subtree:true, childList:true, attributes:true, characterData:true});
    Object.defineProperty(globalThis, key, {configurable:true, value:Object.freeze({id:crypto.randomUUID(),
      read:() => revision, stop:() => { observer.disconnect(); delete globalThis[key]; }})});
  }
  const nodes = [...document.querySelectorAll('button,a[href],input:not([type=hidden]),textarea,select,[role],[contenteditable=true],summary')];
  const name = el => (el.getAttribute('aria-label') ||
    (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim() ||
    [...(el.labels || [])].map(label => label.textContent).join(' ').trim() ||
    (el.tagName === 'INPUT' ? el.getAttribute('placeholder') || el.getAttribute('title') || '' : el.innerText || el.textContent || '')).trim().slice(0, 120);
  const role = el => el.getAttribute('role') || ({BUTTON:'button',A:'link',TEXTAREA:'textbox',SELECT:'combobox',SUMMARY:'button'}[el.tagName]) ||
    (el.tagName === 'INPUT' ? ({checkbox:'checkbox',radio:'radio',button:'button',submit:'button',search:'searchbox',number:'spinbutton'}[el.type] || 'textbox') : el.isContentEditable ? 'textbox' : '');
  const describe = (el, index) => {
    const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0 && style.visibility === 'visible' && style.display !== 'none';
    const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
    const hit = x >= 0 && y >= 0 && x < innerWidth && y < innerHeight ? document.elementFromPoint(x, y) : null;
    return {ref:'e' + index, role:role(el), name:name(el), near:(el.closest('li,[role=listitem],label')?.innerText || '').trim().slice(0, 100),
      state:[`disabled=${!!(el.disabled || el.getAttribute('aria-disabled') === 'true')}`, ...(el.type === 'checkbox' || el.type === 'radio' ? [`checked=${el.checked}`] : [])],
      visible, occluded:!(hit && (hit === el || el.contains(hit))), sensitive:el.type === 'password' || /password|token|secret|api.?key/i.test(el.autocomplete + ' ' + el.name),
      href:el.closest('a[href]')?.href || null,
      form_action:el.form ? (el.hasAttribute('formaction') ? el.formAction : el.form.action) : null, tag:el.tagName};
  };
  const raw = JSON.stringify([globalThis[key].id, globalThis[key].read(), performance.timeOrigin, location.href, document.documentElement.outerHTML,
    nodes.map(el => [el.value, el.checked, el.selectedIndex]), scrollX, scrollY]);
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  const digest = [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, '0')).join('');
  const unsupported = [];
  if (document.querySelector('iframe,frame')) unsupported.push('frames');
  if ([...document.querySelectorAll('*')].some(el => el.shadowRoot)) unsupported.push('shadow_roots');
  if (document.querySelector('canvas,select,[role=slider],[role=grid],[role=listbox]')) unsupported.push('custom_or_select_widgets');
  return {url:location.href, digest, unsupported,
    elements:activeOnly ? [] : nodes.map(describe).filter(el => el.role && el.visible),
    active:activeOnly && document.activeElement ? describe(document.activeElement, nodes.indexOf(document.activeElement)) : null};
}
