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

test('hooks require modern python3 even when python would succeed', t => {
  const { calls, execute } = flow(t);
  const onlyPython = (command, args, ...rest) => {
    if (command === 'python3') throw new Error('missing or old python3');
    return execute(command, args, ...rest);
  };
  assert.throws(() => installer.main(['update', '--hosts', 'grok'], onlyPython), /python3 3.10/);
  assert.ok(calls.every(c => c.args[0] === '--version'));
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
  assert.deepEqual(commands.map(c => c[1][3]), ['DietrichGebert/ponytail', 'anthropics/claude-plugins-official', 'cursor/plugins', 'tourbut/Fullops-Squad-plugin']);
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
  assert.ok(calls.some(c => c.args.join(' ') === 'plugin install fullops-squad@fullops-squad'));
  assert.ok(calls.every(c => !c.args.includes('--trust')));
  assert.ok(calls.some(c => c.args.includes('--host') && c.args.includes('grok')));
  assert.ok(calls.some(c => c.args.includes('--check')));
});

test('update refreshes latest dependencies even when the manifest is unchanged', t => {
  for (const missing of [false, true]) {
    const { calls, execute } = flow(t, { depsMissing: missing });
    assert.equal(installer.main(['update', '--hosts', 'grok'], execute), 0);
    assert.equal(calls.some(c => c.args.includes('--host') && !c.args.includes('--check')), true);
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

test('shared dependencies refresh once per run; later CLIs only repair', t => {
  const grok = flow(t);
  fs.writeFileSync(path.join(grok.root, 'scripts/deps.py'), '# accepts --no-refresh');
  const claude = fixture(t, 'claude-code');
  const execute = (command, args, env, capture) => {
    if (command !== 'claude') return grok.execute(command, args, env, capture);
    if (args[0] === '--version') return 'ok';
    if (args[1] === 'marketplace' && args[2] === 'list') return JSON.stringify([
      { name: 'ponytail', repo: 'DietrichGebert/ponytail' },
      { name: 'claude-plugins-official', repo: 'anthropics/claude-plugins-official' },
      { name: 'fullops-squad', repo: 'tourbut/Fullops-Squad-plugin', installLocation: claude.root },
    ]);
    if (args[1] === 'list') return JSON.stringify(claude.rows('0.9.10'));
    return '';
  };
  assert.equal(installer.main(['update', '--hosts', 'claude,grok'], execute), 0);
  const installs = grok.calls.filter(c => c.args[0].endsWith('deps.py') && !c.args.includes('--check'));
  assert.deepEqual(installs.map(c => c.args.slice(1)), [['--host', 'claude-code'], ['--host', 'grok', '--no-refresh']]);
});

test('grok reads the target version from the installed plugin when its marketplace list names no folder', t => {
  const { root } = fixture(t);
  const target = { host: 'grok', cli: 'grok', label: 'grok', env: {} };
  const execute = (cli, args) => args[1] === 'marketplace'
    ? JSON.stringify([{ name: 'fullops-squad', kind: 'git', source: { url: 'https://github.com/tourbut/Fullops-Squad-plugin.git' } }])
    : JSON.stringify([{ name: 'fullops-squad', marketplace: 'fullops-squad', version: '0.9.9', path: '/installed', source: root }]);
  assert.equal(installer.expectedVersion(target, execute), '0.9.10');
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

test('Windows launcher runs npm .ps1 shims under a Restricted policy', { skip: process.platform !== 'win32' }, t => {
  const { root } = fixture(t);
  fs.writeFileSync(path.join(root, 'fakecli.ps1'), 'Write-Output "ps1 $args"');
  fs.writeFileSync(path.join(root, 'fakecli.cmd'), '@echo cmd %*');
  const call = installer.invocation('fakecli', ['--version']);
  const env = { ...process.env, PATH: root + path.delimiter + process.env.PATH, PSExecutionPolicyPreference: 'Restricted' };
  const result = spawnSync(call.command, call.args, { encoding: 'utf8', windowsHide: true, env });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), 'ps1 --version');
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

// Runs the real CLI and launcher against fakes on PATH. Fake python3 keeps deps.py from running; every home is under the temp root.
const FAKE_CLI = String.raw`'use strict';
const fs = require('node:fs'), path = require('node:path');
const [cli, ...args] = process.argv.slice(2);
const root = process.env.FAKE_ROOT, home = process.env.CODEX_HOME, command = args.join(' ');
fs.appendFileSync(path.join(root, 'calls.log'), JSON.stringify({ cli, args, home }) + '\n');
if (cli === 'python3' || command === '--version') process.exit(0);
const file = path.join(home, 'fake-state.json');
const state = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : { marketplaces: {} };
const marketplace = path.join(root, 'marketplace');
const out = value => console.log(JSON.stringify(value));
if (command === 'plugin marketplace list --json') out({ marketplaces: Object.entries(state.marketplaces).map(([name, source]) =>
  ({ name, root: marketplace, marketplaceSource: { sourceType: 'git', source } })) });
else if (command === 'plugin list --json --marketplace fullops-squad') out({ available: [], installed: !state.installed ? [] :
  [{ pluginId: 'fullops-squad@fullops-squad', name: 'fullops-squad', marketplaceName: 'fullops-squad', version: state.installed }] });
else if (args[1] === 'marketplace' && args[2] === 'add') state.marketplaces[args[3].includes('ponytail') ? 'ponytail' : 'fullops-squad'] = args[3];
else if (command === 'plugin add fullops-squad@fullops-squad') {
  const source = path.join(marketplace, 'dist/native/fullops-squad');
  state.installed = JSON.parse(fs.readFileSync(path.join(source, 'plugin.json'), 'utf8')).version;
  fs.cpSync(source, path.join(home, 'plugins/cache/fullops-squad/fullops-squad', state.installed), { recursive: true });
} else if (command !== 'plugin marketplace upgrade fullops-squad') { console.error('unexpected: ' + command); process.exit(3); }
fs.mkdirSync(home, { recursive: true });
fs.writeFileSync(file, JSON.stringify(state));
`;

function writePackage(directory, version) {
  fs.mkdirSync(path.join(directory, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(directory, 'scripts/deps.py'), '# accepts --no-refresh');
  fs.writeFileSync(path.join(directory, 'scripts/update.py'), '');
  fs.writeFileSync(path.join(directory, 'dependencies.json'), '{}');
  fs.writeFileSync(path.join(directory, 'plugin.json'), JSON.stringify({ version }));
}

function codexHost(t, target = '1.2.0') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'fullops-codex-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const bin = path.join(root, 'bin');
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'fake.cjs'), FAKE_CLI);
  for (const cli of ['codex', 'python3']) {
    fs.writeFileSync(path.join(bin, `${cli}.ps1`), `& node "$PSScriptRoot/fake.cjs" ${cli} @args; exit $LASTEXITCODE`);
    fs.writeFileSync(path.join(bin, cli), `#!/bin/sh\nexec node "$(dirname "$0")/fake.cjs" ${cli} "$@"\n`, { mode: 0o755 });
  }
  const marketplace = path.join(root, 'marketplace');
  fs.mkdirSync(path.join(marketplace, '.agents/plugins'), { recursive: true });
  fs.writeFileSync(path.join(marketplace, '.agents/plugins/marketplace.json'), JSON.stringify({ plugins: [
    { name: 'fullops-squad', source: { source: 'local', path: './dist/native/fullops-squad' } }] }));
  writePackage(path.join(marketplace, 'dist/native/fullops-squad'), target);
  const home = path.join(root, 'home');
  const codexHome = path.join(home, '.codex');
  const run = (args, env = {}) => {
    fs.rmSync(path.join(root, 'calls.log'), { force: true });
    const result = spawnSync(process.execPath, [path.join(__dirname, '../bin/fullops-squad.cjs'), ...args], {
      encoding: 'utf8', windowsHide: true,
      env: { ...process.env, PATH: bin + path.delimiter + process.env.PATH, HOME: home, USERPROFILE: home,
        APPDATA: path.join(root, 'appdata'), CODEX_HOME: codexHome, FAKE_ROOT: root, ...env },
    });
    const log = path.join(root, 'calls.log');
    const calls = fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\n').map(line => JSON.parse(line)) : [];
    return { ...result, calls, commands: calls.map(c => [c.cli, ...c.args].join(' ')) };
  };
  // A home that already holds this FullOps version from the given marketplace source.
  const seed = (directory, installed, source = 'https://github.com/tourbut/Fullops-Squad-plugin.git') => {
    if (installed) writePackage(path.join(directory, 'plugins/cache/fullops-squad/fullops-squad', installed), installed);
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, 'fake-state.json'), JSON.stringify({ installed,
      marketplaces: { ponytail: 'https://github.com/DietrichGebert/ponytail.git', 'fullops-squad': source } }));
  };
  return { root, codexHome, run, seed };
}

const isMutation = command => /marketplace add|marketplace upgrade|plugin add|deps\.py|update\.py/.test(command);

test('Codex install registers, installs and verifies in every home through the real launcher', t => {
  const { root, codexHome, run } = codexHost(t);
  const custom = path.join(root, 'custom home');
  const result = run(['install', '--hosts', 'codex'], { CODEX_HOME: custom });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const homes = [custom, codexHome];
  assert.deepEqual([...new Set(result.calls.map(c => c.home))].sort(), [...homes].sort(), 'no call may reach a home outside the temp root');
  homes.forEach((home, index) => {
    const own = result.calls.filter(c => c.home === home && c.args[0] !== '--version' && c.args[0] !== '-c');
    const cache = path.join(home, 'plugins/cache/fullops-squad/fullops-squad/1.2.0');
    const deps = path.join(cache, 'scripts/deps.py');
    assert.deepEqual(own.filter(c => isMutation([c.cli, ...c.args].join(' '))).map(c => [c.cli, ...c.args].join(' ')), [
      'codex plugin marketplace add DietrichGebert/ponytail',
      'codex plugin marketplace add tourbut/Fullops-Squad-plugin',
      'codex plugin marketplace upgrade fullops-squad',
      'codex plugin add fullops-squad@fullops-squad',
      // Shared tools refresh once per run, so only the first home omits --no-refresh.
      `python3 ${deps} --host codex${index ? ' --no-refresh' : ''}`,
      `python3 ${deps} --check --host codex`,
    ]);
    assert.ok(result.stdout.includes(`codex (${home}): 1.2.0`), result.stdout);
  });
});

test('Codex update re-adds the plugin, since it has no plugin update, and forwards the prior version', t => {
  const { root, codexHome, run, seed } = codexHost(t);
  seed(codexHome, '1.1.0');
  const repo = path.join(root, 'service repo');
  const result = run(['update', '--hosts', 'codex', '--repo', repo]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.commands.filter(isMutation)[0], 'codex plugin marketplace upgrade fullops-squad');
  assert.ok(result.commands.includes('codex plugin add fullops-squad@fullops-squad'));
  assert.ok(!result.commands.some(c => c.includes('plugin update') || c.includes('marketplace add')));
  const plan = result.calls.find(c => c.args[0].endsWith('update.py'));
  assert.equal(plan.args[0], path.join(codexHome, 'plugins/cache/fullops-squad/fullops-squad/1.2.0/scripts/update.py'));
  assert.deepEqual(plan.args.slice(1), ['--repo', repo, '--from', '1.1.0']);
  assert.match(result.stdout, /1\.2\.0 변경됨/);
});

test('Codex dry-run and check never mutate; check needs an installed plugin', t => {
  const { codexHome, run, seed } = codexHost(t);
  const dry = run(['update', '--hosts', 'codex', '--dry-run']);
  assert.equal(dry.status, 0, dry.stdout + dry.stderr);
  assert.ok(dry.stdout.includes(JSON.stringify(['codex', 'plugin', 'add', 'fullops-squad@fullops-squad'])));
  assert.equal(dry.commands.filter(isMutation).length, 0);
  const absent = run(['check', '--hosts', 'codex']);
  assert.equal(absent.status, 1);
  assert.match(absent.stdout, /설치되지 않았습니다/);
  seed(codexHome, '1.1.0');
  const checked = run(['check', '--hosts', 'codex']);
  assert.equal(checked.status, 0, checked.stdout + checked.stderr);
  assert.deepEqual(checked.commands.filter(isMutation), [
    `python3 ${path.join(codexHome, 'plugins/cache/fullops-squad/fullops-squad/1.1.0/scripts/deps.py')} --check --host codex`]);
});

test('Codex refuses a conflicting source and a downgrade; a corrupt cache repairs through plugin add', t => {
  const conflict = codexHost(t);
  conflict.seed(conflict.codexHome, '1.1.0', 'https://github.com/someone/else.git');
  const blocked = conflict.run(['update', '--hosts', 'codex']);
  assert.equal(blocked.status, 1);
  assert.match(blocked.stderr, /fullops-squad 마켓플레이스 출처 충돌/);
  assert.equal(blocked.commands.filter(isMutation).length, 0);

  const older = codexHost(t, '1.0.0');
  older.seed(older.codexHome, '1.1.0');
  const downgrade = older.run(['update', '--hosts', 'codex']);
  assert.equal(downgrade.status, 1);
  assert.match(downgrade.stdout, /downgrade를 거부/);
  assert.ok(!downgrade.commands.some(c => c.includes('plugin add') || c.includes('deps.py')));

  const corrupt = codexHost(t);
  corrupt.seed(corrupt.codexHome, '1.1.0');
  fs.writeFileSync(path.join(corrupt.codexHome, 'plugins/cache/fullops-squad/fullops-squad/1.1.0/dependencies.json'), '{broken');
  const repaired = corrupt.run(['update', '--hosts', 'codex']);
  assert.equal(repaired.status, 0, repaired.stdout + repaired.stderr);
  assert.match(repaired.stdout, /1\.2\.0 복구됨/);
  const order = ['codex plugin add fullops-squad@fullops-squad', 'deps.py'].map(text => repaired.commands.findIndex(c => c.includes(text)));
  assert.ok(order[0] >= 0 && order[1] > order[0]);
});
