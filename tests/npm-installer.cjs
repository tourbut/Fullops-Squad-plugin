'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const installer = require('../bin/fullops-squad.cjs');

test('arguments validate hosts and preserve paths with spaces', () => {
  const result = installer.parseArgs(['update', '--hosts', 'claude,grok,claude', '--repo', 'service repo', '--dry-run']);
  assert.deepEqual(result.hosts, ['claude-code', 'grok']);
  assert.equal(result.repo, path.resolve('service repo'));
  assert.equal(result.dryRun, true);
  assert.throws(() => installer.parseArgs(['install', '--hosts', 'unknown']));
  assert.throws(() => installer.parseArgs(['update', '--repo']));
});

test('Codex homes include current, default, explicit and existing Orca without changing environment', () => {
  const home = path.resolve('user');
  const current = path.join(home, 'custom');
  const env = { CODEX_HOME: current, APPDATA: path.join(home, 'appdata'), TOKEN: 'preserved' };
  const result = installer.targets({ hosts: ['codex'], codexHomes: [current, path.join(home, 'extra')] }, env, home, () => true, () => 'version');
  assert.equal(result.length, 4);
  assert.equal(new Set(result.map(t => t.home)).size, 4);
  assert.equal(env.CODEX_HOME, current);
  assert.ok(result.every(t => t.env.TOKEN === 'preserved' && t.env.CODEX_HOME === t.home));
});

test('marketplace source conflicts block registration; Claude dependencies come first', () => {
  const target = { host: 'claude-code', cli: 'claude', label: 'claude' };
  const commands = installer.registration(target, new Map());
  assert.deepEqual(commands.map(c => c[1][3]), ['DietrichGebert/ponytail', 'anthropics/claude-plugins-official', 'tourbut/Fullops-Squad-plugin']);
  assert.throws(() => installer.registration(target, new Map([['fullops-squad', 'another/repo']])), /출처 충돌/);
  assert.equal(installer.normalizeSource('https://github.com/tourbut/Fullops-Squad-plugin.git'), 'tourbut/fullops-squad-plugin');
});

function fixture(t, host = 'grok') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fullops-installer-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, 'scripts'));
  fs.writeFileSync(path.join(root, 'scripts/deps.py'), '');
  fs.writeFileSync(path.join(root, 'dependencies.json'), '{}');
  fs.writeFileSync(path.join(root, 'plugin.json'), JSON.stringify({ version: '0.9.10' }));
  fs.writeFileSync(path.join(root, 'marketplace.json'), JSON.stringify({ plugins: [{ name: 'fullops-squad', version: '0.9.10' }] }));
  const rows = version => host === 'grok' ? [{ name: 'fullops-squad', marketplace: 'fullops-squad', version, path: root }] :
    [{ id: 'fullops-squad@fullops-squad', version, installPath: root }];
  return { root, rows };
}

test('installed metadata must match the package version', t => {
  const { root, rows } = fixture(t);
  const target = { host: 'grok', cli: 'grok', label: 'grok', env: {} };
  assert.equal(installer.pluginInfo(target, () => JSON.stringify(rows('0.9.10'))).root, root);
  assert.throws(() => installer.pluginInfo(target, () => JSON.stringify(rows('0.9.11'))), /버전 불일치/);
});

function flow(t, { fresh = false, failInstall = false, depsMissing = false, corrupt = false, expected = '0.9.10' } = {}) {
  const { root, rows } = fixture(t);
  if (corrupt) fs.writeFileSync(path.join(root, 'dependencies.json'), '{broken');
  fs.writeFileSync(path.join(root, 'marketplace.json'), JSON.stringify({ plugins: [{ name: 'fullops-squad', version: expected }] }));
  const calls = [];
  let installed = !fresh;
  let missing = depsMissing;
  let registered = !fresh;
  const execute = (command, args, env, capture) => {
    calls.push({ command, args: [...args], capture });
    if (args[0] === '--version' || args[0] === '-c') return 'ok';
    if (args[0] === 'plugin' && args[1] === 'marketplace' && args[2] === 'list') return JSON.stringify(!registered ? [] :
      [{ name: 'fullops-squad', root, source: { url: 'https://github.com/tourbut/Fullops-Squad-plugin.git' } }]);
    if (args[0] === 'plugin' && args[1] === 'list') return JSON.stringify(installed ? rows('0.9.10') : []);
    if (args[1] === 'marketplace' && args[2] === 'add') registered = true;
    if (args[0] === 'plugin' && ['install', 'update'].includes(args[1])) {
      if (failInstall) throw new Error('native install failed');
      installed = true;
      if (corrupt) fs.writeFileSync(path.join(root, 'dependencies.json'), '{}');
    }
    if (args[0].endsWith('deps.py') && args.includes('--check') && missing) throw new Error('dependency missing');
    if (args.includes('--host') && !args.includes('--check')) missing = false;
    return '';
  };
  return { calls, execute, root };
}

test('fresh update installs native plugin, dependencies and verifies the result', t => {
  const { calls, execute } = flow(t, { fresh: true });
  assert.equal(installer.main(['update', '--hosts', 'grok'], execute), 0);
  assert.ok(calls.some(c => c.args.join(' ') === 'plugin install fullops-squad@fullops-squad --trust'));
  assert.ok(calls.some(c => c.args.includes('--host') && c.args.includes('grok')));
  assert.ok(calls.some(c => c.args.includes('--check')));
});

test('unchanged dependencies are checked; missing dependencies are repaired', t => {
  for (const missing of [false, true]) {
    const { calls, execute } = flow(t, { depsMissing: missing });
    assert.equal(installer.main(['update', '--hosts', 'grok'], execute), 0);
    assert.equal(calls.some(c => c.args.includes('--host') && !c.args.includes('--check')), missing);
    assert.ok(calls.some(c => c.args.join(' ') === 'plugin update fullops-squad'));
  }
});

test('dry-run makes no mutations and failed native installs report failure', t => {
  const dry = flow(t, { fresh: true });
  assert.equal(installer.main(['update', '--hosts', 'grok', '--dry-run'], dry.execute), 0);
  assert.ok(dry.calls.every(c => c.capture));
  const failed = flow(t, { failInstall: true });
  assert.equal(installer.main(['update', '--hosts', 'grok'], failed.execute), 1);
  assert.equal(failed.calls.some(c => c.args.includes('--host')), false);
});

test('--repo forwards the prior installed version without modifying repository files', t => {
  const { root, calls, execute } = flow(t);
  const repo = path.join(root, 'service repo');
  fs.mkdirSync(repo);
  const marker = path.join(repo, 'custom.txt');
  fs.writeFileSync(marker, 'existing work');
  assert.equal(installer.main(['update', '--hosts', 'grok', '--repo', repo], execute), 0);
  const plan = calls.find(c => c.args[0].endsWith('update.py'));
  assert.deepEqual(plan.args.slice(1), ['--repo', repo, '--from', '0.9.10']);
  assert.equal(fs.readFileSync(marker, 'utf8'), 'existing work');
});

test('a failed Claude update does not prevent the Grok update', t => {
  const grok = flow(t);
  const claude = fixture(t, 'claude-code');
  const execute = (command, args, env, capture) => {
    if (command !== 'claude') return grok.execute(command, args, env, capture);
    if (args[0] === '--version') return 'ok';
    if (args[1] === 'marketplace' && args[2] === 'list') return JSON.stringify([
      { name: 'ponytail', repo: 'DietrichGebert/ponytail' },
      { name: 'claude-plugins-official', repo: 'anthropics/claude-plugins-official' },
      { name: 'fullops-squad', repo: 'tourbut/Fullops-Squad-plugin' },
    ]);
    if (args[1] === 'list') return JSON.stringify(claude.rows('0.9.10'));
    if (args[1] === 'update') throw new Error('Claude update failed');
    return '';
  };
  assert.equal(installer.main(['update', '--hosts', 'claude,grok'], execute), 1);
  assert.ok(grok.calls.some(c => c.args.join(' ') === 'plugin update fullops-squad'));
  assert.ok(grok.calls.some(c => c.args.includes('--check')));
});

test('Windows launcher preserves shell metacharacters as data', { skip: process.platform !== 'win32' }, t => {
  const { root } = fixture(t);
  const echo = path.join(root, 'echo args.cjs');
  fs.writeFileSync(echo, 'process.stdout.write(JSON.stringify(process.argv.slice(2)))');
  const values = ['한글 경로', 'a&b', '$(throw bad)', '`whoami`', "single'quote"];
  const call = installer.invocation(process.execPath, [echo, ...values]);
  const result = spawnSync(call.command, call.args, { encoding: 'utf8', windowsHide: true });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), values);
});

test('corrupt metadata repairs through native commands before running dependencies', t => {
  const { calls, execute } = flow(t, { corrupt: true });
  assert.equal(installer.main(['update', '--hosts', 'grok'], execute), 0);
  const native = calls.findIndex(c => c.args.join(' ') === 'plugin update fullops-squad');
  const deps = calls.findIndex(c => c.args[0].endsWith('deps.py'));
  assert.ok(native >= 0 && deps > native);
});

test('stale, unknown and downgrade targets never report update success', t => {
  for (const expected of ['0.9.11', null, '0.9.9']) {
    const { calls, execute } = flow(t, { expected });
    assert.equal(installer.main(['update', '--hosts', 'grok'], execute), 1);
    assert.equal(calls.some(c => c.args[0].endsWith('deps.py')), false);
    if (expected !== '0.9.11') assert.equal(calls.some(c => c.args.join(' ') === 'plugin update fullops-squad'), false);
  }
});

test('one target preflight failure leaves the other target able to finish', t => {
  const grok = flow(t);
  const execute = (command, args, env, capture) => {
    if (command === 'claude') {
      if (args[0] === '--version') return 'ok';
      throw new Error('unavailable marketplace JSON');
    }
    return grok.execute(command, args, env, capture);
  };
  assert.equal(installer.main(['update', '--hosts', 'claude,grok'], execute), 1);
  assert.ok(grok.calls.some(c => c.args.includes('--check')));
});
