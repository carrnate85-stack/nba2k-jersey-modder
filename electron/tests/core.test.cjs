const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const ts = require('typescript');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText, filename);
const { normalizeProject, atomicWrite, readProject, portableProject } = require('../src/project-storage.ts');
const { LatestQueue } = require('../src/latest-queue.ts');
const { FileAccess } = require('../src/file-access.ts');
const defaults = JSON.parse(fs.readFileSync(path.join(__dirname, '../../assets/project-defaults.json')));

test('legacy migration preserves colors, staging, and unknown extension data without nested version fields', () => {
  const project = normalizeProject({ projectVersion: 1, generator: { colors: { left_panel_color: '#112233' } }, custom: 42 }, defaults);
  assert.equal(project.generator.colors.shorts_left_panel_color, '#112233');
  assert.equal(project.generator.projectVersion, undefined);
  assert.equal(project.custom, 42);
  assert.deepEqual(project.creators.logo.items, []);
  assert.throws(() => normalizeProject({ projectVersion: 999 }, defaults), /newer/);
  assert.throws(() => normalizeProject({ generator: { logos: 'broken' } }, defaults), /Invalid/);
});

test('atomic saves retain previous valid data and portable assets reopen after a folder move', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'jersey-storage-'));
  try {
    const file = path.join(folder, 'project.json');
    const data = normalizeProject({}, defaults);
    data.generator.images.front_wordmark_image = path.join(folder, 'assets/logos/logo.png');
    atomicWrite(file, JSON.stringify(portableProject(data, file)));
    assert.equal(JSON.parse(fs.readFileSync(file)).generator.images.front_wordmark_image, 'assets/logos/logo.png');
    assert.equal(readProject(file, defaults).generator.images.front_wordmark_image, data.generator.images.front_wordmark_image);
    atomicWrite(file, JSON.stringify({ ...data, marker: true }), true);
    assert.equal(JSON.parse(fs.readFileSync(file + '.bak')).marker, undefined);
    assert.equal(JSON.parse(fs.readFileSync(file)).marker, true);
    assert.equal(fs.readdirSync(folder).filter(x => x.endsWith('.tmp')).length, 0);
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
});

test('rapid previews run the first and latest request only, then recover after failure', async () => {
  const queue = new LatestQueue();
  const ran = [];
  let release;
  const first = queue.submit('render', () => new Promise(resolve => { ran.push(1); release = resolve; }));
  const second = queue.submit('render', async () => ran.push(2)).catch(error => error.message);
  const third = queue.submit('render', async () => { ran.push(3); return 3; });
  release(1);
  assert.equal(await first, 1);
  assert.equal(await second, 'Preview superseded');
  assert.equal(await third, 3);
  assert.deepEqual(ran, [1, 3]);
  await assert.rejects(queue.submit('render', async () => { throw new Error('failed'); }));
  assert.equal(await queue.submit('render', async () => 4), 4);
});

test('file permissions prevent sibling traversal and writes to read-only assets', () => {
  const permissions = new FileAccess();
  const base = path.join(os.tmpdir(), 'jersey-allowed');
  permissions.grantTree(base);
  assert.equal(permissions.check(path.join(base, 'image.png')), path.join(base, 'image.png'));
  assert.throws(() => permissions.check(path.join(base, 'image.png'), true));
  assert.throws(() => permissions.check(path.join(base, '../jersey-allowed-other/image.png')));
  const selected = path.join(os.tmpdir(), 'selected-font.iff');
  permissions.grant(selected, true);
  assert.equal(permissions.check(selected, true), selected);
});
