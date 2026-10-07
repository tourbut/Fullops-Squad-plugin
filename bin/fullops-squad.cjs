#!/usr/bin/env node
// Installs or updates FullOps through each host's native marketplace commands.
// Global plugin installation stays separate from service repository setup.
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const SOURCE = 'tourbut/Fullops-Squad-plugin';
const PLUGIN = 'fullops-squad@fullops-squad';
const HOSTS = ['codex', 'claude-code', 'grok'];
const dependencies = require('../dependencies.json');

function parseArgs(args) {
  const options = { command: args.shift() || 'help', hosts: HOSTS, codexHomes: [], dryRun: false };
  while (args.length) {
    const flag = args.shift();
    if (flag === '--dry-run') options.dryRun = true;
    else if (flag === '--help' || flag === '-h') options.command = 'help';
    else if (['--hosts', '--codex-home', '--repo'].includes(flag)) {
      const value = args.shift();
      if (!value || value.startsWith('--')) throw new Error(`${flag}: 값이 필요합니다`);
      if (flag === '--hosts') options.hosts = value === 'all' ? HOSTS : value.split(',').map(x => x === 'claude' ? 'claude-code' : x);
      else if (flag === '--codex-home') options.codexHomes.push(path.resolve(value));
      else options.repo = path.resolve(value);
    } else throw new Error(`알 수 없는 옵션: ${flag}`);
  }
  if (['--help', '-h'].includes(options.command)) options.command = 'help';
  if (!['help', 'install', 'update', 'check'].includes(options.command)) throw new Error(`알 수 없는 명령: ${options.command}`);
  if (options.hosts.some(h => !HOSTS.includes(h))) throw new Error(`지원하는 CLI: ${HOSTS.join(', ')}`);
  options.hosts = [...new Set(options.hosts)];
  return options;
}

// PowerShell passes decoded values as arguments, without building shell commands.
// This also supports npm's .ps1/.cmd launchers on Windows.
function invocation(command, args, platform = process.platform) {
  if (platform !== 'win32') return { command, args };
  const payload = Buffer.from(JSON.stringify({ command, args })).toString('base64');
  const script = `$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); ` +
    `$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${payload}'))|ConvertFrom-Json; ` +
    `$commandArgs=[string[]]$p.args; $global:LASTEXITCODE=0; & $p.command @commandArgs; exit $LASTEXITCODE`;
  return { command: 'powershell.exe', args: ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')] };
}

function run(command, args, env = process.env, capture = false) {
  const call = invocation(command, args);
  const result = spawnSync(call.command, call.args, {
    env, encoding: 'utf8', stdio: capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    windowsHide: true, maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    const detail = result.error?.message || result.stderr?.trim().split(/\r?\n/).slice(-3).join('\n') || `종료코드 ${result.status}`;
    throw new Error(`${command} ${args.join(' ')}: ${detail}`);
  }
  return result.stdout || '';
}

function available(command, env, execute = run) {
  try { execute(command, ['--version'], env, true); return true; } catch { return false; }
}

function targets(options, env = process.env, home = os.homedir(), exists = fs.existsSync, execute = run) {
  const found = [];
  for (const host of options.hosts) {
    const cli = host === 'claude-code' ? 'claude' : host;
    if (!available(cli, env, execute)) {
      console.log(`${cli}: 실행 파일 없음, 건너뜀`);
      continue;
    }
    if (host !== 'codex') {
      found.push({ host, cli, label: cli, env });
      continue;
    }
    const homes = [env.CODEX_HOME || path.join(home, '.codex'), path.join(home, '.codex'), ...options.codexHomes];
    if (env.APPDATA) {
      const orcaHome = path.join(env.APPDATA, 'orca', 'codex-runtime-home', 'home');
      if (exists(orcaHome)) homes.push(orcaHome);
    }
    const seen = new Set();
    for (const value of homes) {
      const resolved = path.resolve(value);
      const key = process.platform === 'win32' ? resolved.toLowerCase() : resolved;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push({ host, cli, home: resolved, label: `codex (${resolved})`, env: { ...env, CODEX_HOME: resolved } });
    }
  }
  return found;
}

function normalizeSource(value) {
  return String(value || '').replace(/^https?:\/\/github\.com\//i, '').replace(/\.git\/?$/i, '').replace(/\/$/, '').toLowerCase();
}

function marketplaces(target, execute = run) {
  const data = JSON.parse(execute(target.cli, ['plugin', 'marketplace', 'list', '--json'], target.env, true));
  const rows = target.host === 'codex' ? data.marketplaces : data;
  if (!Array.isArray(rows)) throw new Error(`${target.label}: marketplace list JSON 형식 불일치`);
  return new Map(rows.map(row => [row.name, target.host === 'codex' ? row.marketplaceSource?.source || row.root :
    target.host === 'grok' ? row.source?.url : row.repo || row.url || row.path || row.installLocation]));
}

function registration(target, registered) {
  const required = target.host === 'claude-code' ? { ...dependencies.marketplaces, 'fullops-squad': SOURCE } :
    target.host === 'codex' ? { ponytail: dependencies.marketplaces.ponytail, 'fullops-squad': SOURCE } : { 'fullops-squad': SOURCE };
  const commands = [];
  for (const [name, source] of Object.entries(required)) {
    if (registered.has(name)) {
      if (normalizeSource(registered.get(name)) !== normalizeSource(source)) throw new Error(`${target.label}: ${name} 마켓플레이스 출처 충돌`);
    } else commands.push([target.cli, ['plugin', 'marketplace', 'add', source]]);
  }
  return commands;
}

function pluginInfo(target, execute = run) {
  const args = ['plugin', 'list', '--json'];
  if (target.host === 'codex') args.push('--marketplace', 'fullops-squad');
  const data = JSON.parse(execute(target.cli, args, target.env, true));
  const rows = target.host === 'codex' ? data.installed : data;
  if (!Array.isArray(rows)) throw new Error(`${target.label}: plugin list JSON 형식 불일치`);
  const row = rows.find(p => target.host === 'claude-code' ? p.id === PLUGIN : p.name === 'fullops-squad' &&
    (p.marketplaceName || p.marketplace) === 'fullops-squad');
  if (!row) return null;
  const candidates = target.host === 'codex' ? [path.join(target.home, 'plugins/cache/fullops-squad/fullops-squad', row.version || ''), row.source?.path] :
    target.host === 'claude-code' ? [row.installPath] : [row.path, row.source];
  const root = candidates.find(p => p && fs.existsSync(path.join(p, 'scripts/deps.py')));
  if (!root || !row.version) throw new Error(`${target.label}: 설치 경로 또는 버전을 확인할 수 없습니다`);
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'plugin.json'), 'utf8'));
  if (manifest.version !== row.version) throw new Error(`${target.label}: 설치 목록과 패키지 버전 불일치`);
  if (!/^\d+\.\d+\.\d+$/.test(row.version)) throw new Error('지원하지 않는 plugin version: stable SemVer가 필요합니다');
  const raw = fs.readFileSync(path.join(root, 'dependencies.json'), 'utf8');
  JSON.parse(raw);
  return { root, version: row.version, dependencies: raw };
}

function expectedVersion(target, execute = run) {
  const data = JSON.parse(execute(target.cli, ['plugin', 'marketplace', 'list', '--json'], target.env, true));
  const rows = target.host === 'codex' ? data.marketplaces : data;
  const row = rows.find(m => m.name === 'fullops-squad');
  const root = row?.root || row?.installLocation || row?.path;
  if (!root) return null;
  for (const relative of ['.agents/plugins/marketplace.json', '.claude-plugin/marketplace.json', 'marketplace.json']) {
    const catalog = path.join(root, relative);
    if (!fs.existsSync(catalog)) continue;
    const entry = JSON.parse(fs.readFileSync(catalog, 'utf8')).plugins?.find(p => p.name === 'fullops-squad');
    const source = typeof entry?.source === 'string' ? entry.source : entry?.source?.path;
    if (source && !path.isAbsolute(source)) {
      const manifest = path.resolve(root, source, 'plugin.json');
      if (!manifest.startsWith(path.resolve(root) + path.sep)) throw new Error('marketplace package escapes its root');
      if (fs.existsSync(manifest)) return JSON.parse(fs.readFileSync(manifest, 'utf8')).version;
    }
    if (entry?.version) return entry.version;
  }
  return null;
}

function compareVersion(a, b) {
  if (![a, b].every(v => typeof v === 'string' && /^\d+\.\d+\.\d+$/.test(v))) throw new Error('목표 stable SemVer를 확인할 수 없습니다');
  const left = a.split(/[.-]/).slice(0, 3).map(Number), right = b.split(/[.-]/).slice(0, 3).map(Number);
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] - right[i];
  return 0;
}

function operations(target, command, installed) {
  const refresh = target.host === 'codex' ? ['plugin', 'marketplace', 'upgrade', 'fullops-squad'] : ['plugin', 'marketplace', 'update', 'fullops-squad'];
  const install = target.host === 'codex' ? ['plugin', 'add', PLUGIN] : target.host === 'claude-code' ?
    ['plugin', 'install', PLUGIN, '--scope', 'user'] : ['plugin', 'install', PLUGIN, '--trust'];
  const update = target.host === 'claude-code' ? ['plugin', 'update', PLUGIN, '--scope', 'user'] : ['plugin', 'update', 'fullops-squad'];
  return [[target.cli, refresh], [target.cli, command === 'update' && installed && target.host !== 'codex' ? update : install]];
}

function reportPlan(target, commands) {
  console.log(`\n${target.label}`);
  for (const [cli, args] of commands) console.log(JSON.stringify([cli, ...args]));
  console.log('설치 경로·버전 확인 후 deps.py 설치/검사. 새 세션 필요. 레포 setup은 실행하지 않음.');
  console.log('의존성 계획은 새 대상 manifest 확인 전 잠정입니다. global npm 도구, 사용자 skills, 호스트 plugin을 확인·복구합니다.');
}

function main(argv = process.argv.slice(2), execute = run) {
  const options = parseArgs([...argv]);
  if (options.command === 'help') {
    console.log(`FullOps Squad 통합 설치기\n\nfullops-squad install|update|check [--hosts all|codex,claude-code,grok]\n  --dry-run           변경 없이 명령 계획 출력\n  --codex-home PATH   추가 Codex 홈 (반복 가능)\n  --repo PATH         업데이트 후 레포 적용 안내 출력 (레포 수정 없음)\n\nPATH에 있는 CLI를 처리합니다. 기본 Codex 홈과 기존 Windows Orca 홈도 포함합니다.\nCLI 자체 설치와 서비스 레포 setup은 수행하지 않습니다.`);
    return 0;
  }
  const selected = targets(options, process.env, os.homedir(), fs.existsSync, execute);
  if (!selected.length) throw new Error('사용 가능한 대상 CLI가 없습니다');
  const python = ['python3', 'python'].find(p => {
    try { execute(p, ['-c', 'import sys; assert sys.version_info >= (3, 10)'], process.env, true); return true; } catch { return false; }
  });
  if (!python) throw new Error('Python 3.10 이상 실행 파일이 필요합니다');
  // Check all registrations before making any changes.
  const results = [];
  const plans = [];
  for (const target of selected) {
    try {
      const known = marketplaces(target, execute);
      plans.push({ target, known, registered: registration(target, known) });
    } catch (error) {
      if (error.message.includes('출처 충돌')) throw error;
      results.push({ label: target.label, error: `preflight: ${error.message}` });
    }
  }
  for (const { target, known, registered } of plans) {
    const completed = [];
    try {
      let before = null, corrupt = false;
      try { before = known.has('fullops-squad') ? pluginInfo(target, execute) : null; }
      catch (error) {
        if (options.command === 'check') throw error;
        corrupt = true;
        console.log(`${target.label}: 손상된 기존 설치, 공식 호스트 명령으로 복구합니다.`);
      }
      if (options.command === 'check') {
        if (!before) throw new Error('FullOps 플러그인이 설치되지 않았습니다');
        execute(python, [path.join(before.root, 'scripts/deps.py'), '--check', '--host', target.host], target.env);
        results.push({ label: target.label, version: before.version });
        continue;
      }
      const commands = [...registered, ...operations(target, options.command, before || corrupt)];
      if (options.dryRun) { reportPlan(target, commands); continue; }
      console.log(`\n${target.label}: ${before?.version || '미설치'}`);
      for (const [cli, args] of commands) {
        execute(cli, args, target.env);
        completed.push(args.join(' '));
        if (args[1] === 'marketplace' && ['upgrade', 'update'].includes(args[2])) {
          const expected = expectedVersion(target, execute);
          if (!expected) throw new Error('목표 버전 확인 불가: marketplace manifest를 확인한 뒤 재시도하세요');
          compareVersion(expected, expected);
          if (before && expected && compareVersion(expected, before.version) < 0) throw new Error('marketplace 대상 downgrade를 거부합니다');
        }
      }
      const after = pluginInfo(target, execute);
      if (!after) throw new Error('설치 명령 뒤 FullOps를 확인할 수 없습니다');
      const expected = expectedVersion(target, execute);
      if (!expected) throw new Error(`목표 버전 확인 불가; 설치 버전 ${after.version}, 경로 ${after.root}. marketplace manifest를 확인하고 재시도하세요`);
      if (after.version !== expected) throw new Error(`목표 ${expected}에 도달하지 못했습니다: 설치 ${after.version}`);
      if (before && compareVersion(after.version, before.version) < 0) throw new Error('설치 버전 downgrade를 거부합니다');
      const depsScript = path.join(after.root, 'scripts/deps.py');
      let needsDeps = options.command === 'install' || !before || before.dependencies !== after.dependencies;
      if (!needsDeps) {
        try { execute(python, [depsScript, '--check', '--host', target.host], target.env, true); } catch { needsDeps = true; }
      }
      if (needsDeps) execute(python, [depsScript, '--host', target.host], target.env);
      execute(python, [depsScript, '--check', '--host', target.host], target.env);
      completed.push('host dependencies verified');
      if (options.repo) execute(python, [path.join(after.root, 'scripts/update.py'), '--repo', options.repo,
        ...(before ? ['--from', before.version] : [])], target.env);
      results.push({ label: target.label, version: after.version, root: after.root,
        status: before?.version === after.version ? '이미 목표 버전' : corrupt ? '복구됨' : '변경됨' });
    } catch (error) {
      results.push({ label: target.label, error: `${error.message}; 적용된 단계: ${completed.join(', ') || '없음'}. 같은 명령으로 남은 단계를 재시도하세요.` });
    }
  }
  for (const result of results) console.log(`${result.label}: ${result.error ? `실패 — ${result.error}` : `${result.version} ${result.status || ''} ${result.root || ''}`}`);
  if (!options.dryRun && options.command !== 'check') console.log('각 CLI에서 새 에이전트 세션을 여세요. 레포 적용은 FullOps update 요청으로 진행합니다.');
  return results.some(r => r.error) ? 1 : 0;
}

module.exports = { parseArgs, invocation, targets, normalizeSource, registration, pluginInfo, operations, main };
if (require.main === module) {
  try { process.exitCode = main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
