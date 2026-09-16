const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Ajv = require('ajv/dist/2020');

const root = path.resolve(__dirname, '../plugins/fullops-squad');
const json = file => JSON.parse(fs.readFileSync(file, 'utf8'));
for (const kind of ['plugin', 'mcp']) {
  const schema = json(path.join(__dirname, `vendor/agent-plugins/schemas/1.0.0/${kind}.schema.json`));
  const ajv = new Ajv({ strict: false });
  const validate = ajv.compile(schema);
  assert(validate(json(path.join(root, `${kind}.json`))), ajv.errorsText(validate.errors));
}
for (const legacy of ['.codex-plugin', '.claude-plugin', '.mcp.json', 'mcp_config.json']) {
  assert(!fs.existsSync(path.join(root, legacy)), `Host adapter leaked into standard package: ${legacy}`);
}
function contained(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    assert(fs.realpathSync(file).startsWith(root + path.sep), `Package path escapes root: ${file}`);
    if (entry.isDirectory()) contained(file);
  }
}
contained(root);
const skills = fs.readdirSync(path.join(root, 'skills'));
for (const name of skills) {
  const skill = fs.readFileSync(path.join(root, 'skills', name, 'SKILL.md'), 'utf8');
  assert(skill.startsWith('---\n'));
  assert(skill.includes(`\nname: ${name}\n`));
  assert(/^description: .+/m.test(skill));
}
console.log(`PASS: Agent Plugins 1.0.0 schemas, package containment, ${skills.length} skill entry points`);
