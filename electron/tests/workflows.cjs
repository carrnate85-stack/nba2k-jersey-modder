const { _electron: electron } = require(process.env.JERSEY_PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const testRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'jersey-ui-test-'));
const artifacts = path.join(root, 'electron/out/review');
fs.mkdirSync(artifacts, {recursive: true});
for (const item of ['main.py', 'assets', 'tools', 'nba2k_jersey_modder', 'blendermodels', 'wpf']) {
  fs.cpSync(path.join(root, item), path.join(testRoot, item), {recursive:true, filter: source => !source.includes('__pycache__') && !source.includes(`${path.sep}bin${path.sep}`) && !source.includes(`${path.sep}obj${path.sep}`)});
}
const executablePath = path.join(root, 'electron/out/NBA 2K Jersey Modder-win32-x64/NBA2KJerseyModder.exe');
let application;
(async () => {
  application = await electron.launch({ executablePath, cwd: testRoot, env: { ...process.env, JERSEY_MODDER_ROOT: testRoot, JERSEY_MODDER_SCREENSHOT: '', JERSEY_MODDER_TEST_PROJECT: '' } });
  const page = await application.firstWindow();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.getByPlaceholder('Detroit 1962 Home').fill('UI Verification');
  await page.getByRole('button', {name:'Create Project', exact:true}).click();
  await page.locator('.preview-stage img').waitFor({timeout:30000});
  await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
  const projectPath = path.join(testRoot, 'projects/UI Verification/UI Verification.nba2kproject.json');
  assert.equal(JSON.parse(fs.readFileSync(projectPath)).projectVersion, 3);
  await page.getByLabel('Show UV overlay').uncheck();
  await page.waitForFunction(() => document.querySelector('footer').textContent.includes('Recovery saved'));
  assert.ok(fs.existsSync(projectPath + '.recovery'));
  await page.getByRole('button', {name:'Save project', exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.project-title span').textContent === 'Saved');
  assert.ok(fs.existsSync(projectPath + '.bak'));
  assert.equal(JSON.parse(fs.readFileSync(projectPath)).generator.uvOverlay.enabled, false);
  const logo = path.join(testRoot, 'wpf/JerseyModder.Wpf/Assets/app-icon.png');
  await application.evaluate(({dialog}, logo) => { dialog.showOpenDialog = async () => ({canceled:false,filePaths:[logo]}); }, logo);
  await page.getByRole('button', {name:/^Logos/}).click();
  await page.getByRole('button', {name:'Choose Front Wordmark',exact:true}).click();
  await page.getByLabel('Show UV overlay').check();
  await page.waitForTimeout(750);

  for (const size of [[1540,940],[1000,700]]) {
    await application.evaluate(({BrowserWindow}, size) => BrowserWindow.getAllWindows()[0].setSize(...size), size);
    await page.waitForTimeout(250);
    const fit = await page.locator('.preview-panel').evaluate(element => { const box=element.getBoundingClientRect(); return box.right <= innerWidth && box.bottom <= innerHeight && box.width > 150 && box.height > 150; });
    assert.ok(fit, `Generator fits ${size}`);
    await page.screenshot({path:path.join(artifacts, `generator-${size.join('x')}.png`)});
  }
  await page.getByRole('button', {name:'Texture Creator', exact:true}).click();
  await page.getByLabel('Texture type').selectOption('Normal Texture');
  await page.locator('.preview-stage img').waitFor({timeout:30000});
  await page.locator('input[type=number]').fill('0');
  await page.waitForTimeout(1000);
  assert.ok(!(await page.locator('footer').textContent()).includes('Unknown texture'));
  await page.screenshot({path:path.join(artifacts,'normal-preview.png')});
  await page.getByRole('button', {name:'Number Editor', exact:true}).click();
  await page.getByRole('button', {name:'Browse Game Numbers',exact:true}).click();
  await page.getByRole('dialog', {name:'Game number catalog'}).waitFor();
  await page.getByRole('button', {name:'Close catalog',exact:true}).click();
  await page.getByLabel('Fill hex color').fill('#123456');
  assert.equal(await page.getByLabel('No change').first().isChecked(), false);
  await page.getByRole('button', {name:'Generator', exact:true}).click();
  await page.getByRole('button', {name:'Number Editor', exact:true}).click();
  assert.equal(await page.getByLabel('Fill hex color').inputValue(), '#123456');
  for (const name of ['Logo Creator', 'Trim Creator', 'Trim Path Lab', 'Tweak Editor', 'IFF Textures', 'RDAT Editor', 'Template Editor']) {
    await page.getByRole('button', {name, exact:true}).click();
    await page.getByRole('heading', {name, exact:true}).waitFor();
    await page.screenshot({path:path.join(artifacts, `${name.toLowerCase().replaceAll(' ','-')}.png`)});
    if(name === 'Template Editor') {
      await page.locator('.zone-list button').first().click();
      await page.getByRole('dialog', {name:'Edit zone'}).waitFor();
      await page.getByRole('dialog').getByLabel('x', {exact:true}).fill('-12');
      await page.getByRole('button', {name:'Apply Zone Edits',exact:true}).click();
      assert.ok((await page.locator('.zone-list button').first().textContent()).includes('-12'));
    }
  }
  await page.getByRole('button', {name:'Generator', exact:true}).click();
  const editorPromise = application.waitForEvent('window');
  await page.getByRole('button', {name:'Open Web Layer Editor'}).click();
  const editor = await editorPromise;
  await editor.waitForLoadState('domcontentloaded');
  await editor.locator('canvas').first().waitFor();
  await editor.waitForFunction(() => document.getElementById('loadStatus')?.textContent.startsWith('Loaded '));
  const pixels = await editor.locator('canvas').first().evaluate(canvas => {
    const context = canvas.getContext('2d');
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let light = 0;
    for(let index=0; index<data.length; index+=400) if(data[index]>180 && data[index+1]>180) light++;
    return light;
  });
  assert.ok(pixels > 20, 'Web editor displays rendered texture pixels');
  await editor.screenshot({path:path.join(artifacts,'layer-editor.png')});
  await editor.getByRole('button', {name:/Return to App/i}).click();
  await page.waitForTimeout(500);
  assert.equal(application.windows().length, 1);
  assert.deepEqual(errors, []);
  await page.evaluate(() => window.jersey.setDirty(false));
  await application.close(); application = null;
  console.log('PASS: startup, recovery/save, two window sizes, normal preview, persistent number colors, all pages, web editor return.');
})().catch(error => { console.error(error); process.exitCode=1; }).finally(async () => {
  if(application) { await application.evaluate(({BrowserWindow}) => BrowserWindow.getAllWindows().forEach(window => window.destroy())).catch(()=>{}); await application.close().catch(()=>{}); }
  const resolved = path.resolve(testRoot);
  if(resolved.startsWith(path.resolve(os.tmpdir()) + path.sep) && path.basename(resolved).startsWith('jersey-ui-test-')) fs.rmSync(resolved,{recursive:true,force:true});
});
