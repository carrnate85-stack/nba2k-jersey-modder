const path = require('node:path');
const { MakerSquirrel } = require('@electron-forge/maker-squirrel');
const { MakerZIP } = require('@electron-forge/maker-zip');
const { AutoUnpackNativesPlugin } = require('@electron-forge/plugin-auto-unpack-natives');
const { VitePlugin } = require('@electron-forge/plugin-vite');

module.exports = {
  packagerConfig: {
    asar: true,
    icon: path.resolve(__dirname, '../wpf/JerseyModder.Wpf/Assets/app-icon.ico'),
    executableName: 'NBA2KJerseyModder',
  },
  rebuildConfig: {},
  makers: [
    new MakerSquirrel({ name: 'NBA2KJerseyModder', setupIcon: path.resolve(__dirname, '../wpf/JerseyModder.Wpf/Assets/app-icon.ico') }),
    new MakerZIP({}, ['win32']),
  ],
  plugins: [
    new AutoUnpackNativesPlugin({}),
    new VitePlugin({
      build: [
        { entry: 'src/main.ts', config: 'vite.main.config.ts' },
        { entry: 'src/preload.ts', config: 'vite.preload.config.ts' },
      ],
      renderer: [{ name: 'main_window', config: 'vite.renderer.config.ts' }],
    }),
  ],
};
