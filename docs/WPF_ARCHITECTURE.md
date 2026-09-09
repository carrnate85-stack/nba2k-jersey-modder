# Historical WPF Interface

WPF is no longer the active frontend. The application now uses Electron with the existing Python engine. See [ARCHITECTURE.md](ARCHITECTURE.md) for current ownership, persistence, and editor contracts.

The `wpf/` sources remain available for compatibility and reference. New interface work belongs in `electron/src/renderer/pages/`. Shared project defaults are loaded from `assets/project-defaults.json`.
