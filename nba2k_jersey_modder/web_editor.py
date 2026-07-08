from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NBA 2K Jersey Web Editor</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #171a20; color: #edf1f7; overflow: hidden; }
    header { height: 48px; display: flex; align-items: center; gap: 12px; padding: 0 14px; background: #222833; border-bottom: 1px solid #343b49; }
    button { background: #f0b429; color: #171a20; border: 0; padding: 8px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; }
    .hint { color: #aab3c2; font-size: 13px; }
    #wrap { height: calc(100vh - 49px); display: grid; grid-template-columns: 1fr 300px; }
    #stage { min-width: 0; min-height: 0; overflow: auto; background: #11141a; }
    canvas { background: #20242b; display: block; margin: 10px auto; }
    aside { border-left: 1px solid #343b49; padding: 12px; overflow: auto; background: #1d222c; }
    h2 { font-size: 14px; margin: 0 0 10px; color: #f8fafc; }
    .layer { padding: 8px; border: 1px solid #343b49; margin-bottom: 8px; border-radius: 6px; color: #d7deeb; cursor: pointer; }
    .layer.active { border-color: #f0b429; color: #fff; }
    .layer strong, .layer span { display: block; }
    .layer span { color: #99a5b8; font-size: 12px; margin-top: 3px; }
    .panel { border-top: 1px solid #343b49; margin-top: 12px; padding-top: 12px; }
    label { display: block; color: #aab3c2; font-size: 12px; margin: 8px 0 3px; }
    input { width: 100%; box-sizing: border-box; background: #11141a; color: #edf1f7; border: 1px solid #343b49; border-radius: 5px; padding: 7px; }
    input[type="checkbox"] { width: auto; }
    .check { display: flex; align-items: center; gap: 8px; margin: 8px 0; color: #d7deeb; font-size: 13px; }
    .check input { margin: 0; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .buttons { display: flex; gap: 8px; margin-top: 10px; }
    .buttons button { flex: 1; padding: 7px 8px; }
    button.secondary { background: #303746; color: #edf1f7; border: 1px solid #475064; }
    button:disabled { opacity: .45; cursor: default; }
    .small { color: #9aa4b5; font-size: 12px; line-height: 1.4; margin-top: 12px; }
    .uv-panel { border: 1px solid #343b49; border-radius: 6px; padding: 10px; margin-bottom: 12px; background: #202632; }
    .uv-panel h2 { margin-bottom: 6px; }
    .range-row { display: flex; align-items: center; gap: 8px; }
    input[type="range"] { padding: 0; }
  </style>
</head>
<body>
  <header>
    <strong>Jersey Web Editor</strong>
    <button id="refresh">Refresh from app</button>
    <button id="resetEditor" class="secondary">Reset edits</button>
    <button id="viewTexture">Texture</button>
    <button id="viewRegion" class="secondary">Region</button>
    <button id="editorZoomOut" class="secondary">Zoom -</button>
    <button id="editorFit" class="secondary">Fit</button>
    <button id="editorZoomIn" class="secondary">Zoom +</button>
    <span id="editorZoomLabel" class="hint">100%</span>
    <span id="loadStatus" class="hint"></span>
    <span class="hint">Drag images. Pull the yellow handle to resize. Wrap logos move only up/down.</span>
  </header>
  <div id="wrap">
    <main id="stage"><canvas id="canvas" width="2048" height="2048"></canvas></main>
    <aside>
      <div id="uvPanel" class="uv-panel">
        <h2>UV Overlay</h2>
        <label class="check"><input id="showUvOverlay" type="checkbox"> Show UV overlay</label>
        <label for="uvOpacity">Opacity <span id="uvOpacityLabel">45%</span></label>
        <input id="uvOpacity" type="range" min="0" max="100" step="1" value="45">
      </div>
      <h2>Editable Images</h2>
      <div id="layers"></div>
      <div class="panel">
        <h2>Position / Layer</h2>
        <div id="selectedName" class="small">Select an image.</div>
        <div class="grid">
          <div><label for="posX">X</label><input id="posX" type="number" step="1"></div>
          <div><label for="posY">Y</label><input id="posY" type="number" step="1"></div>
          <div><label for="posW">Width</label><input id="posW" type="number" step="1" min="1"></div>
          <div><label for="posH">Height</label><input id="posH" type="number" step="1" min="1"></div>
          <div><label for="rotation">Rotation</label><input id="rotation" type="number" step="1"></div>
        </div>
        <div class="buttons"><button id="applyPosition">Apply</button></div>
        <div class="buttons">
          <button id="layerUp" class="secondary">Layer Up</button>
          <button id="layerDown" class="secondary">Layer Down</button>
        </div>
        <div class="buttons"><button id="flipX" class="secondary">Flip X</button></div>
      </div>
      <div class="panel">
        <h2>Transparency</h2>
        <label class="check"><input id="autoBackground" type="checkbox"> Auto background</label>
        <label class="check"><input id="removeWhite" type="checkbox"> Remove white</label>
        <label class="check"><input id="removeBlack" type="checkbox"> Remove black</label>
        <label class="check"><input id="outsideOnly" type="checkbox"> Outside only</label>
        <label for="cleanupTolerance">Tolerance</label>
        <input id="cleanupTolerance" type="number" min="0" max="255" step="1">
        <div class="buttons">
          <button id="applyTransparency">Apply</button>
          <button id="resetTransparency" class="secondary">Use Default</button>
        </div>
      </div>
      <div class="small">Changes are sent back to the desktop app when you release the mouse. Use the desktop app to export PNG or PSD.</div>
    </aside>
  </div>
  <script>
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");
    const stage = document.getElementById("stage");
    const layers = document.getElementById("layers");
    const selectedName = document.getElementById("selectedName");
    const posX = document.getElementById("posX");
    const posY = document.getElementById("posY");
    const posW = document.getElementById("posW");
    const posH = document.getElementById("posH");
    const rotation = document.getElementById("rotation");
    const applyPosition = document.getElementById("applyPosition");
    const layerUp = document.getElementById("layerUp");
    const layerDown = document.getElementById("layerDown");
    const flipX = document.getElementById("flipX");
    const autoBackground = document.getElementById("autoBackground");
    const removeWhite = document.getElementById("removeWhite");
    const removeBlack = document.getElementById("removeBlack");
    const outsideOnly = document.getElementById("outsideOnly");
    const cleanupTolerance = document.getElementById("cleanupTolerance");
    const applyTransparency = document.getElementById("applyTransparency");
    const resetTransparency = document.getElementById("resetTransparency");
    const resetEditor = document.getElementById("resetEditor");
    const viewTexture = document.getElementById("viewTexture");
    const viewRegion = document.getElementById("viewRegion");
    const editorZoomLabel = document.getElementById("editorZoomLabel");
    const loadStatus = document.getElementById("loadStatus");
    const uvPanel = document.getElementById("uvPanel");
    const showUvOverlay = document.getElementById("showUvOverlay");
    const uvOpacity = document.getElementById("uvOpacity");
    const uvOpacityLabel = document.getElementById("uvOpacityLabel");
    let editorZoom = 1;
    let viewMode = "texture";
    let project = null;
    let baseImage = new Image();
    let regionImage = new Image();
    let uvImage = new Image();
    let uvOverlayAvailable = false;
    let uvOverlayEnabled = false;
    let uvOverlayOpacity = 45;
    let uvOverlayTouched = false;
    let overlays = new Map();
    let activeKey = null;
    let drag = null;
    const HANDLE_SIZE = 56;
    const HANDLE_HIT_RADIUS = 58;

    async function loadProject() {
      try {
        loadStatus.textContent = "Loading...";
        const response = await fetch("/api/project", {cache: "no-store"});
        if (!response.ok) throw new Error(`Project failed: ${response.status}`);
        project = await response.json();
        overlays.clear();
        await Promise.all(project.overlays.map(item => new Promise(resolve => {
          const img = new Image();
          img.onload = () => { overlays.set(item.key, img); resolve(); };
          img.onerror = resolve;
          img.src = item.imageUrl + "&t=" + Date.now();
        })));
        await new Promise(resolve => {
          baseImage.onload = resolve;
          baseImage.onerror = resolve;
          baseImage.src = project.baseUrl + "?t=" + Date.now();
        });
        await new Promise(resolve => {
          regionImage.onload = resolve;
          regionImage.onerror = resolve;
          regionImage.src = "/api/region.png?t=" + Date.now();
        });
        uvOverlayAvailable = Boolean(project.uvOverlay?.available);
        if (uvOverlayAvailable) {
          if (!uvOverlayTouched) {
            uvOverlayEnabled = Boolean(project.uvOverlay?.enabled);
            uvOverlayOpacity = Math.max(0, Math.min(100, Number(project.uvOverlay?.opacity ?? uvOverlayOpacity)));
          }
          await new Promise(resolve => {
            uvImage.onload = resolve;
            uvImage.onerror = resolve;
            uvImage.src = `${project.uvOverlay.imageUrl}?t=${Date.now()}`;
          });
        }
        renderUvControls();
        if (!project.overlays.some(item => item.key === activeKey)) {
          activeKey = project.overlays[project.overlays.length - 1]?.key || null;
        }
        renderLayerList();
        renderInspector();
        draw();
        loadStatus.textContent = "Loaded";
      } catch (error) {
        loadStatus.textContent = `Could not load editor: ${error.message}`;
      }
    }

    function renderLayerList() {
      layers.innerHTML = "";
      if (viewMode === "region") {
        const node = document.createElement("div");
        node.className = "layer";
        node.innerHTML = "<strong>Region Preview</strong><span>Side panels, logos, and wordmark regions</span>";
        layers.appendChild(node);
        return;
      }
      for (const item of [...project.overlays].reverse()) {
        const node = document.createElement("div");
        node.className = "layer" + (item.key === activeKey ? " active" : "");
        node.innerHTML = `<strong>${item.label}</strong><span>${item.layerLabel}</span>`;
        node.onclick = () => {
          activeKey = item.key;
          renderLayerList();
          renderInspector();
          draw();
        };
        layers.appendChild(node);
      }
    }

    function activeItem() {
      if (viewMode === "region") return null;
      return project?.overlays.find(item => item.key === activeKey) || null;
    }

    function renderInspector() {
      const item = activeItem();
      const disabled = !item;
      for (const input of [posX, posY, posW, posH]) input.disabled = disabled || !item.canTransform;
      rotation.disabled = disabled || !item.canRotate;
      applyPosition.disabled = disabled || !item.canTransform;
      layerUp.disabled = disabled || !item.canReorder;
      layerDown.disabled = disabled || !item.canReorder;
      flipX.disabled = disabled || !item.canFlip;
      for (const input of [autoBackground, removeWhite, removeBlack, outsideOnly, cleanupTolerance]) {
        input.disabled = disabled || !item.canCleanup;
      }
      applyTransparency.disabled = disabled || !item.canCleanup;
      resetTransparency.disabled = disabled || !item.canCleanup || !item.cleanup?.isOverride;
      if (!item) {
        selectedName.textContent = viewMode === "region"
          ? "Region preview only."
          : "Select an image.";
        for (const input of [posX, posY, posW, posH]) input.value = "";
        rotation.value = "";
        autoBackground.checked = false;
        removeWhite.checked = false;
        removeBlack.checked = false;
        outsideOnly.checked = true;
        cleanupTolerance.value = "";
        return;
      }
      selectedName.textContent = `${item.label} - ${item.layerLabel}${item.flipX ? " - flipped" : ""}`;
      posX.value = Math.round(item.x);
      posY.value = Math.round(item.y);
      posW.value = Math.round(item.width);
      posH.value = Math.round(item.height);
      rotation.value = Math.round(item.rotation || 0);
      posX.disabled = !item.canTransform || item.lockX;
      posW.disabled = !item.canTransform || item.lockX;
      autoBackground.checked = Boolean(item.cleanup?.autoBackground);
      removeWhite.checked = Boolean(item.cleanup?.removeWhite);
      removeBlack.checked = Boolean(item.cleanup?.removeBlack);
      outsideOnly.checked = item.cleanup?.outsideOnly !== false;
      cleanupTolerance.value = Math.round(item.cleanup?.tolerance ?? 32);
    }

    function fittedCanvasSize() {
      const size = Math.max(320, Math.min(stage.clientWidth - 20, stage.clientHeight - 20));
      return size;
    }

    function applyCanvasZoom() {
      const displaySize = Math.max(320, Math.round(fittedCanvasSize() * editorZoom));
      canvas.style.width = displaySize + "px";
      canvas.style.height = displaySize + "px";
      editorZoomLabel.textContent = `${Math.round(editorZoom * 100)}%`;
    }

    function draw() {
      applyCanvasZoom();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (viewMode === "region") {
        if (regionImage.complete) ctx.drawImage(regionImage, 0, 0, 2048, 2048);
        renderInspector();
        return;
      }
      if (baseImage.complete) ctx.drawImage(baseImage, 0, 0, 2048, 2048);
      for (const item of project?.overlays || []) {
        const img = overlays.get(item.key);
        if (!img?.complete) continue;
        ctx.save();
        ctx.globalCompositeOperation = canvasBlendMode(item.blendMode);
        if (item.clipBox) {
          ctx.beginPath();
          ctx.rect(item.clipBox.x, item.clipBox.y, item.clipBox.width, item.clipBox.height);
          ctx.clip();
        }
        drawOverlayImage(img, item);
        ctx.restore();
      }
      drawUvOverlay();
      const active = project?.overlays.find(item => item.key === activeKey);
      if (active?.canTransform) drawBox(active);
      renderInspector();
    }

    function renderUvControls() {
      uvPanel.style.display = uvOverlayAvailable ? "block" : "none";
      showUvOverlay.checked = uvOverlayEnabled;
      showUvOverlay.disabled = !uvOverlayAvailable;
      uvOpacity.disabled = !uvOverlayAvailable || !uvOverlayEnabled;
      uvOpacity.value = uvOverlayOpacity;
      uvOpacityLabel.textContent = `${Math.round(uvOverlayOpacity)}%`;
    }

    function drawUvOverlay() {
      if (!uvOverlayAvailable || !uvOverlayEnabled || viewMode !== "texture") return;
      if (!uvImage.complete || !uvImage.naturalWidth) return;
      ctx.save();
      ctx.globalAlpha = Math.max(0, Math.min(1, uvOverlayOpacity / 100));
      ctx.drawImage(uvImage, 0, 0, 2048, 2048);
      ctx.restore();
    }

    function setViewMode(nextMode) {
      viewMode = nextMode;
      viewTexture.classList.toggle("secondary", viewMode !== "texture");
      viewRegion.classList.toggle("secondary", viewMode !== "region");
      renderLayerList();
      renderInspector();
      draw();
    }

    function canvasBlendMode(blendMode) {
      if (blendMode === "multiply") return "multiply";
      if (blendMode === "overlay") return "overlay";
      return "source-over";
    }

    function drawOverlayImage(img, item) {
      const angle = (item.rotation || 0) * Math.PI / 180;
      if (!angle) {
        ctx.drawImage(img, item.x, item.y, item.width, item.height);
        return;
      }
      const cx = item.x + item.width / 2;
      const cy = item.y + item.height / 2;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);
      ctx.drawImage(img, -item.width / 2, -item.height / 2, item.width, item.height);
      ctx.restore();
    }

    function drawBox(item) {
      ctx.save();
      ctx.strokeStyle = "#ffcc33";
      ctx.lineWidth = 5;
      const angle = (item.rotation || 0) * Math.PI / 180;
      const cx = item.x + item.width / 2;
      const cy = item.y + item.height / 2;
      ctx.translate(cx, cy);
      ctx.rotate(angle);
      ctx.strokeRect(-item.width / 2, -item.height / 2, item.width, item.height);
      if (item.clipBox) {
        ctx.restore();
        ctx.save();
        ctx.setLineDash([16, 10]);
        ctx.strokeStyle = "#31d0ff";
        ctx.strokeRect(item.clipBox.x, item.clipBox.y, item.clipBox.width, item.clipBox.height);
        ctx.setLineDash([]);
        ctx.translate(cx, cy);
        ctx.rotate(angle);
      }
      ctx.fillStyle = "#ffcc33";
      for (const handle of localHandles(item)) {
        ctx.fillRect(handle.x - HANDLE_SIZE / 2, handle.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
      }
      ctx.restore();
    }

    function localHandles(item) {
      if (item.lockX) return [{x: item.width / 2, y: item.height / 2, sx: 0, sy: 1}];
      return [
        {x: -item.width / 2, y: -item.height / 2, sx: -1, sy: -1},
        {x: item.width / 2, y: -item.height / 2, sx: 1, sy: -1},
        {x: -item.width / 2, y: item.height / 2, sx: -1, sy: 1},
        {x: item.width / 2, y: item.height / 2, sx: 1, sy: 1},
      ];
    }

    function rotatedPoint(item, localX, localY) {
      const angle = (item.rotation || 0) * Math.PI / 180;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const cx = item.x + item.width / 2;
      const cy = item.y + item.height / 2;
      return {
        x: cx + localX * cos - localY * sin,
        y: cy + localX * sin + localY * cos,
      };
    }

    function localPoint(point, item) {
      const angle = (item.rotation || 0) * Math.PI / 180;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const cx = item.x + item.width / 2;
      const cy = item.y + item.height / 2;
      const dx = point.x - cx;
      const dy = point.y - cy;
      return {
        x: dx * cos + dy * sin,
        y: -dx * sin + dy * cos,
      };
    }

    function distance(a, b) {
      return Math.hypot(a.x - b.x, a.y - b.y);
    }

    function canvasPoint(event) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * 2048 / rect.width,
        y: (event.clientY - rect.top) * 2048 / rect.height,
      };
    }

    function hitTest(point) {
      for (const item of [...project.overlays].reverse()) {
        if (!item.canTransform) continue;
        for (const handle of localHandles(item)) {
          const handlePoint = rotatedPoint(item, handle.x, handle.y);
          if (distance(point, handlePoint) <= HANDLE_HIT_RADIUS) {
            return {item, mode: "resize", handle};
          }
        }
        const local = localPoint(point, item);
        const inBody = local.x >= -item.width / 2 && local.x <= item.width / 2 &&
                       local.y >= -item.height / 2 && local.y <= item.height / 2;
        if (inBody) return {item, mode: "move"};
      }
      return null;
    }

    canvas.addEventListener("pointerdown", event => {
      if (viewMode === "region") return;
      const point = canvasPoint(event);
      const hit = hitTest(point);
      if (!hit) {
        activeKey = null;
        renderLayerList();
        renderInspector();
        draw();
        return;
      }
      activeKey = hit.item.key;
      renderLayerList();
      renderInspector();
      drag = {
        mode: hit.mode,
        key: hit.item.key,
        start: point,
        original: {...hit.item},
        handle: hit.handle,
      };
      canvas.setPointerCapture(event.pointerId);
      draw();
    });

    async function sendUpdate(item) {
      await fetch("/api/update", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          key: item.key,
          x: item.x,
          y: item.y,
          width: item.width,
          height: item.height,
          rotation: item.rotation || 0,
        }),
      });
    }

    canvas.addEventListener("pointermove", event => {
      if (viewMode === "region") return;
      if (!drag) return;
      const point = canvasPoint(event);
      const item = project.overlays.find(candidate => candidate.key === drag.key);
      const dx = point.x - drag.start.x;
      const dy = point.y - drag.start.y;
      if (drag.mode === "move") {
        if (item.lockX) {
          item.x = 0;
          item.y = drag.original.y + dy;
        } else {
          item.x = drag.original.x + dx;
          item.y = drag.original.y + dy;
        }
      } else {
        if (item.lockX) {
          item.x = 0;
          item.width = 2048;
          item.height = Math.max(1, drag.original.height + dy);
        } else {
          const ratio = drag.original.height / Math.max(1, drag.original.width);
          const handle = drag.handle || {sx: 1, sy: 1};
          const currentLocal = localPoint(point, drag.original);
          const opposite = {
            x: -handle.sx * drag.original.width / 2,
            y: -handle.sy * drag.original.height / 2,
          };
          const widthFromX = Math.max(1, (currentLocal.x - opposite.x) * handle.sx);
          const heightFromY = Math.max(1, (currentLocal.y - opposite.y) * handle.sy);
          item.width = Math.max(widthFromX, heightFromY / ratio);
          item.height = Math.max(1, item.width * ratio);
          const active = {
            x: opposite.x + handle.sx * item.width,
            y: opposite.y + handle.sy * item.height,
          };
          const centerLocal = {
            x: (opposite.x + active.x) / 2,
            y: (opposite.y + active.y) / 2,
          };
          const centerWorld = rotatedPoint(drag.original, centerLocal.x, centerLocal.y);
          item.x = centerWorld.x - item.width / 2;
          item.y = centerWorld.y - item.height / 2;
        }
      }
      draw();
    });

    canvas.addEventListener("pointerup", async event => {
      if (viewMode === "region") return;
      if (!drag) return;
      const item = project.overlays.find(candidate => candidate.key === drag.key);
      drag = null;
      await sendUpdate(item);
      await loadProject();
    });

    applyPosition.onclick = async () => {
      const item = activeItem();
      if (!item) return;
      if (!item.lockX) {
        item.x = Number(posX.value || 0);
        item.width = Math.max(1, Number(posW.value || 1));
      }
      item.y = Number(posY.value || 0);
      item.height = Math.max(1, Number(posH.value || 1));
      item.rotation = Number(rotation.value || 0);
      await sendUpdate(item);
      await loadProject();
    };

    async function reorder(direction) {
      const item = activeItem();
      if (!item || !item.canReorder) return;
      await fetch("/api/reorder", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({key: item.key, direction}),
      });
      await loadProject();
    }

    async function sendTransparency(clearOverride = false) {
      const item = activeItem();
      if (!item || !item.canCleanup) return;
      await fetch("/api/transparency", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          key: item.key,
          autoBackground: autoBackground.checked,
          removeWhite: removeWhite.checked,
          removeBlack: removeBlack.checked,
          outsideOnly: outsideOnly.checked,
          tolerance: Number(cleanupTolerance.value || 32),
          clearOverride,
        }),
      });
      await loadProject();
    }

    async function flipSelected() {
      const item = activeItem();
      if (!item || !item.canFlip) return;
      await fetch("/api/flip", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({key: item.key}),
      });
      await loadProject();
    }

    layerUp.onclick = () => reorder("up");
    layerDown.onclick = () => reorder("down");
    flipX.onclick = flipSelected;
    applyTransparency.onclick = () => sendTransparency(false);
    resetTransparency.onclick = () => sendTransparency(true);
    showUvOverlay.onchange = () => {
      uvOverlayTouched = true;
      uvOverlayEnabled = showUvOverlay.checked;
      renderUvControls();
      draw();
    };
    uvOpacity.oninput = () => {
      uvOverlayTouched = true;
      uvOverlayOpacity = Number(uvOpacity.value || 0);
      uvOpacityLabel.textContent = `${Math.round(uvOverlayOpacity)}%`;
      draw();
    };
    document.getElementById("editorZoomOut").onclick = () => {
      editorZoom = Math.max(0.25, editorZoom / 1.25);
      draw();
    };
    document.getElementById("editorZoomIn").onclick = () => {
      editorZoom = Math.min(8, editorZoom * 1.25);
      draw();
    };
    document.getElementById("editorFit").onclick = () => {
      editorZoom = 1;
      draw();
      stage.scrollLeft = 0;
      stage.scrollTop = 0;
    };
    stage.addEventListener("wheel", event => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      editorZoom = event.deltaY < 0
        ? Math.min(8, editorZoom * 1.12)
        : Math.max(0.25, editorZoom / 1.12);
      draw();
    }, {passive: false});
    resetEditor.onclick = async () => {
      if (!confirm("Reset web editor positions, layer order, flips, and transparency overrides?")) return;
      await fetch("/api/reset", {method: "POST"});
      activeKey = null;
      await loadProject();
    };

    document.getElementById("refresh").onclick = loadProject;
    viewTexture.onclick = () => setViewMode("texture");
    viewRegion.onclick = () => setViewMode("region");
    window.addEventListener("resize", draw);
    loadProject();
  </script>
</body>
</html>
"""


LOGO_SELECTOR_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NBA 2K Logo Selector</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #171a20; color: #edf1f7; overflow: hidden; }
    header { height: 48px; display: flex; align-items: center; gap: 8px; padding: 0 14px; background: #222833; border-bottom: 1px solid #343b49; }
    button { background: #f0b429; color: #171a20; border: 0; padding: 8px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; }
    button.secondary { background: #303746; color: #edf1f7; border: 1px solid #475064; }
    .hint { color: #aab3c2; font-size: 13px; margin-left: 4px; }
    #wrap { height: calc(100vh - 49px); display: grid; grid-template-columns: 1fr 280px; }
    #stage { min-width: 0; min-height: 0; background: #11141a; position: relative; }
    canvas { width: 100%; height: 100%; display: block; cursor: crosshair; }
    aside { border-left: 1px solid #343b49; padding: 12px; background: #1d222c; overflow: auto; }
    h2 { font-size: 14px; margin: 0 0 10px; color: #f8fafc; }
    .buttons { display: flex; gap: 8px; margin-bottom: 8px; }
    .buttons button { flex: 1; }
    .small { color: #9aa4b5; font-size: 12px; line-height: 1.4; margin-top: 12px; }
    .status { color: #d7deeb; font-size: 13px; margin-top: 10px; }
  </style>
</head>
<body>
  <header>
    <strong>Logo Selector</strong>
    <button id="zoomOut" class="secondary">Zoom -</button>
    <button id="fit" class="secondary">Fit</button>
    <button id="zoomIn" class="secondary">Zoom +</button>
    <button id="clear" class="secondary">Clear</button>
    <button id="send">Send Selection</button>
    <span class="hint">Wheel zooms. Shift-drag pans. Drag around the logo to lasso.</span>
  </header>
  <div id="wrap">
    <main id="stage"><canvas id="canvas"></canvas></main>
    <aside>
      <h2>Selection</h2>
      <div class="buttons">
        <button id="sendSide">Send</button>
        <button id="clearSide" class="secondary">Clear</button>
      </div>
      <div id="status" class="status">Loading reference...</div>
      <div class="small">After sending, the desktop Logo Creator preview updates and can be saved or sent to the Generator.</div>
    </aside>
  </div>
  <script>
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");
    const stage = document.getElementById("stage");
    const status = document.getElementById("status");
    const image = new Image();
    let project = null;
    let scale = 1;
    let minScale = 1;
    let panX = 0;
    let panY = 0;
    let points = [];
    let drawing = false;
    let panning = false;
    let panStart = null;
    let dirty = false;

    function resizeCanvas() {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(stage.clientWidth * ratio));
      canvas.height = Math.max(1, Math.floor(stage.clientHeight * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    }

    async function loadProject() {
      try {
        const response = await fetch("/api/logo/project", {cache: "no-store"});
        if (!response.ok) throw new Error(`Project failed: ${response.status}`);
        project = await response.json();
        points = project.points || [];
        if (!project.hasImage) {
          status.textContent = project.message || "Upload a reference photo in the desktop Logo Creator first.";
          draw();
          return;
        }
        await new Promise((resolve, reject) => {
          image.onload = resolve;
          image.onerror = () => reject(new Error("Reference image failed to load."));
          image.src = project.imageUrl + "?t=" + Date.now();
        });
        fitImage();
        status.textContent = points.length
          ? `${points.length} lasso points loaded. ${project.message || ""}`
          : `Ready to lasso. ${project.message || ""}`;
      } catch (error) {
        status.textContent = `Could not load reference: ${error.message}`;
      }
    }

    function fitImage() {
      if (!project?.hasImage) return;
      const width = stage.clientWidth;
      const height = stage.clientHeight;
      minScale = Math.min((width - 32) / project.width, (height - 32) / project.height);
      minScale = Math.max(0.05, Math.min(1, minScale));
      scale = minScale;
      panX = (width - project.width * scale) / 2;
      panY = (height - project.height * scale) / 2;
      draw();
    }

    function draw() {
      const width = stage.clientWidth;
      const height = stage.clientHeight;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#11141a";
      ctx.fillRect(0, 0, width, height);
      if (!project?.hasImage || !image.complete) return;
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(image, panX, panY, project.width * scale, project.height * scale);
      if (!points.length) return;
      ctx.save();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffcc33";
      ctx.fillStyle = "rgba(240, 180, 41, 0.16)";
      ctx.beginPath();
      for (let index = 0; index < points.length; index++) {
        const x = panX + points[index].x * scale;
        const y = panY + points[index].y * scale;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      if (!drawing && points.length > 2) ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    function scheduleDraw() {
      if (dirty) return;
      dirty = true;
      requestAnimationFrame(() => {
        dirty = false;
        draw();
      });
    }

    function canvasPoint(event) {
      const rect = canvas.getBoundingClientRect();
      return {x: event.clientX - rect.left, y: event.clientY - rect.top};
    }

    function imagePoint(event) {
      const point = canvasPoint(event);
      return {
        x: Math.max(0, Math.min(project.width - 1, Math.round((point.x - panX) / scale))),
        y: Math.max(0, Math.min(project.height - 1, Math.round((point.y - panY) / scale))),
      };
    }

    function zoomAt(factor, center) {
      if (!project?.hasImage) return;
      const beforeX = (center.x - panX) / scale;
      const beforeY = (center.y - panY) / scale;
      scale = Math.max(minScale * 0.5, Math.min(12, scale * factor));
      panX = center.x - beforeX * scale;
      panY = center.y - beforeY * scale;
      scheduleDraw();
    }

    canvas.addEventListener("pointerdown", event => {
      if (!project?.hasImage) return;
      canvas.setPointerCapture(event.pointerId);
      if (event.shiftKey || event.button === 1 || event.button === 2) {
        panning = true;
        const point = canvasPoint(event);
        panStart = {x: point.x, y: point.y, panX, panY};
        return;
      }
      drawing = true;
      points = [imagePoint(event)];
      status.textContent = "Lassoing...";
      scheduleDraw();
    });

    canvas.addEventListener("pointermove", event => {
      if (panning && panStart) {
        const point = canvasPoint(event);
        panX = panStart.panX + point.x - panStart.x;
        panY = panStart.panY + point.y - panStart.y;
        scheduleDraw();
        return;
      }
      if (!drawing) return;
      const point = imagePoint(event);
      const last = points[points.length - 1];
      if (!last || Math.abs(point.x - last.x) + Math.abs(point.y - last.y) >= 2) {
        points.push(point);
        scheduleDraw();
      }
    });

    canvas.addEventListener("pointerup", event => {
      if (panning) {
        panning = false;
        panStart = null;
        return;
      }
      if (!drawing) return;
      drawing = false;
      if (points.length < 3) {
        points = [];
        status.textContent = "Draw a larger lasso.";
      } else {
        status.textContent = `${points.length} lasso points ready.`;
      }
      scheduleDraw();
    });

    canvas.addEventListener("wheel", event => {
      event.preventDefault();
      zoomAt(event.deltaY < 0 ? 1.18 : 1 / 1.18, canvasPoint(event));
    }, {passive: false});

    canvas.addEventListener("contextmenu", event => event.preventDefault());

    async function sendSelection() {
      if (!points.length) {
        status.textContent = "Draw a lasso before sending.";
        return;
      }
      await fetch("/api/logo/lasso", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({points}),
      });
      status.textContent = "Selection sent to desktop preview.";
    }

    async function clearSelection() {
      points = [];
      await fetch("/api/logo/clear", {method: "POST"});
      status.textContent = "Selection cleared.";
      scheduleDraw();
    }

    document.getElementById("zoomOut").onclick = () => zoomAt(1 / 1.25, {x: stage.clientWidth / 2, y: stage.clientHeight / 2});
    document.getElementById("zoomIn").onclick = () => zoomAt(1.25, {x: stage.clientWidth / 2, y: stage.clientHeight / 2});
    document.getElementById("fit").onclick = fitImage;
    document.getElementById("clear").onclick = clearSelection;
    document.getElementById("clearSide").onclick = clearSelection;
    document.getElementById("send").onclick = sendSelection;
    document.getElementById("sendSide").onclick = sendSelection;
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
    loadProject();
  </script>
</body>
</html>
"""


NUMBER_SELECTOR_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NBA 2K Number Selector</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #171a20; color: #edf1f7; overflow: hidden; }
    header { height: 48px; display: flex; align-items: center; gap: 8px; padding: 0 14px; background: #222833; border-bottom: 1px solid #343b49; }
    button { background: #f0b429; color: #171a20; border: 0; padding: 8px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; }
    button.secondary { background: #303746; color: #edf1f7; border: 1px solid #475064; }
    select { background: #11141a; color: #edf1f7; border: 1px solid #475064; border-radius: 6px; padding: 7px; }
    .hint { color: #aab3c2; font-size: 13px; margin-left: 4px; }
    #wrap { height: calc(100vh - 49px); display: grid; grid-template-columns: 1fr 280px; }
    #stage { min-width: 0; min-height: 0; background: #11141a; position: relative; }
    canvas { width: 100%; height: 100%; display: block; cursor: crosshair; }
    aside { border-left: 1px solid #343b49; padding: 12px; background: #1d222c; overflow: auto; }
    h2 { font-size: 14px; margin: 0 0 10px; color: #f8fafc; }
    .buttons { display: flex; gap: 8px; margin-bottom: 8px; }
    .buttons button { flex: 1; }
    .small { color: #9aa4b5; font-size: 12px; line-height: 1.4; margin-top: 12px; }
    .status { color: #d7deeb; font-size: 13px; margin-top: 10px; }
    label { display: block; color: #aab3c2; font-size: 12px; margin: 10px 0 4px; }
  </style>
</head>
<body>
  <header>
    <strong>Number Selector</strong>
    <button id="zoomOut" class="secondary">Zoom -</button>
    <button id="fit" class="secondary">Fit</button>
    <button id="zoomIn" class="secondary">Zoom +</button>
    <button id="clear" class="secondary">Clear</button>
    <button id="send">Send to Digit</button>
    <span class="hint">Wheel zooms. Shift-drag pans. Box is best for clean jersey numbers.</span>
  </header>
  <div id="wrap">
    <main id="stage"><canvas id="canvas"></canvas></main>
    <aside>
      <h2>Selection</h2>
      <label for="mode">Pick mode</label>
      <select id="mode"><option>Box</option><option>Lasso</option></select>
      <div class="buttons" style="margin-top: 12px;">
        <button id="sendSide">Send</button>
        <button id="clearSide" class="secondary">Clear</button>
      </div>
      <div id="status" class="status">Loading reference...</div>
      <div class="small">The browser sends the selection into the active digit slot in the desktop Number Set Creator.</div>
    </aside>
  </div>
  <script>
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");
    const stage = document.getElementById("stage");
    const status = document.getElementById("status");
    const modeSelect = document.getElementById("mode");
    const image = new Image();
    let project = null;
    let scale = 1;
    let minScale = 1;
    let panX = 0;
    let panY = 0;
    let points = [];
    let box = null;
    let drawing = false;
    let panning = false;
    let panStart = null;
    let dirty = false;

    function resizeCanvas() {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(stage.clientWidth * ratio));
      canvas.height = Math.max(1, Math.floor(stage.clientHeight * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    }

    async function loadProject() {
      try {
        const response = await fetch("/api/number/project", {cache: "no-store"});
        if (!response.ok) throw new Error(`Project failed: ${response.status}`);
        project = await response.json();
        modeSelect.value = project.mode || "Box";
        points = project.points || [];
        box = project.box || null;
        if (!project.hasImage) {
          status.textContent = "Upload a reference photo in the desktop Number Set Creator first.";
          draw();
          return;
        }
        await new Promise((resolve, reject) => {
          image.onload = resolve;
          image.onerror = () => reject(new Error("Reference image failed to load."));
          image.src = project.imageUrl + "?t=" + Date.now();
        });
        fitImage();
        status.textContent = `Ready for digit ${project.digit}.`;
      } catch (error) {
        status.textContent = `Could not load reference: ${error.message}`;
      }
    }

    function fitImage() {
      if (!project?.hasImage) return;
      const width = stage.clientWidth;
      const height = stage.clientHeight;
      minScale = Math.min((width - 32) / project.width, (height - 32) / project.height);
      minScale = Math.max(0.05, Math.min(1, minScale));
      scale = minScale;
      panX = (width - project.width * scale) / 2;
      panY = (height - project.height * scale) / 2;
      draw();
    }

    function draw() {
      const width = stage.clientWidth;
      const height = stage.clientHeight;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#11141a";
      ctx.fillRect(0, 0, width, height);
      if (!project?.hasImage || !image.complete) return;
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(image, panX, panY, project.width * scale, project.height * scale);
      ctx.save();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffcc33";
      ctx.fillStyle = "rgba(240, 180, 41, 0.16)";
      if (modeSelect.value === "Box" && box) {
        const left = panX + Math.min(box.x1, box.x2) * scale;
        const top = panY + Math.min(box.y1, box.y2) * scale;
        const right = panX + Math.max(box.x1, box.x2) * scale;
        const bottom = panY + Math.max(box.y1, box.y2) * scale;
        ctx.fillRect(left, top, right - left, bottom - top);
        ctx.strokeRect(left, top, right - left, bottom - top);
      }
      if (modeSelect.value === "Lasso" && points.length) {
        ctx.beginPath();
        for (let index = 0; index < points.length; index++) {
          const x = panX + points[index].x * scale;
          const y = panY + points[index].y * scale;
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        if (!drawing && points.length > 2) ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    }

    function scheduleDraw() {
      if (dirty) return;
      dirty = true;
      requestAnimationFrame(() => {
        dirty = false;
        draw();
      });
    }

    function canvasPoint(event) {
      const rect = canvas.getBoundingClientRect();
      return {x: event.clientX - rect.left, y: event.clientY - rect.top};
    }

    function imagePoint(event) {
      const point = canvasPoint(event);
      return {
        x: Math.max(0, Math.min(project.width - 1, Math.round((point.x - panX) / scale))),
        y: Math.max(0, Math.min(project.height - 1, Math.round((point.y - panY) / scale))),
      };
    }

    function zoomAt(factor, center) {
      if (!project?.hasImage) return;
      const beforeX = (center.x - panX) / scale;
      const beforeY = (center.y - panY) / scale;
      scale = Math.max(minScale * 0.5, Math.min(16, scale * factor));
      panX = center.x - beforeX * scale;
      panY = center.y - beforeY * scale;
      scheduleDraw();
    }

    canvas.addEventListener("pointerdown", event => {
      if (!project?.hasImage) return;
      canvas.setPointerCapture(event.pointerId);
      if (event.shiftKey || event.button === 1 || event.button === 2) {
        panning = true;
        const point = canvasPoint(event);
        panStart = {x: point.x, y: point.y, panX, panY};
        return;
      }
      drawing = true;
      const point = imagePoint(event);
      if (modeSelect.value === "Box") {
        box = {x1: point.x, y1: point.y, x2: point.x, y2: point.y};
        points = [];
      } else {
        points = [point];
        box = null;
      }
      status.textContent = "Selecting...";
      scheduleDraw();
    });

    canvas.addEventListener("pointermove", event => {
      if (panning && panStart) {
        const point = canvasPoint(event);
        panX = panStart.panX + point.x - panStart.x;
        panY = panStart.panY + point.y - panStart.y;
        scheduleDraw();
        return;
      }
      if (!drawing) return;
      const point = imagePoint(event);
      if (modeSelect.value === "Box") {
        box.x2 = point.x;
        box.y2 = point.y;
      } else {
        const last = points[points.length - 1];
        if (!last || Math.abs(point.x - last.x) + Math.abs(point.y - last.y) >= 2) {
          points.push(point);
        }
      }
      scheduleDraw();
    });

    canvas.addEventListener("pointerup", event => {
      if (panning) {
        panning = false;
        panStart = null;
        return;
      }
      if (!drawing) return;
      drawing = false;
      if (modeSelect.value === "Lasso" && points.length < 3) {
        points = [];
        status.textContent = "Draw a larger lasso.";
      } else if (modeSelect.value === "Box" && box && Math.abs(box.x2 - box.x1) < 2 && Math.abs(box.y2 - box.y1) < 2) {
        box = null;
        status.textContent = "Draw a larger box.";
      } else {
        status.textContent = "Selection ready.";
      }
      scheduleDraw();
    });

    canvas.addEventListener("wheel", event => {
      event.preventDefault();
      zoomAt(event.deltaY < 0 ? 1.18 : 1 / 1.18, canvasPoint(event));
    }, {passive: false});

    canvas.addEventListener("contextmenu", event => event.preventDefault());
    modeSelect.onchange = () => {
      points = [];
      box = null;
      scheduleDraw();
      status.textContent = `${modeSelect.value} mode.`;
    };

    async function sendSelection() {
      const mode = modeSelect.value;
      if (mode === "Box" && !box) {
        status.textContent = "Draw a box before sending.";
        return;
      }
      if (mode === "Lasso" && points.length < 3) {
        status.textContent = "Draw a lasso before sending.";
        return;
      }
      const response = await fetch("/api/number/selection", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode, box, points}),
      });
      if (!response.ok) {
        status.textContent = "Desktop app could not save the selection.";
        return;
      }
      const result = await response.json();
      status.textContent = `Saved digit ${result.digit}: ${result.saved}`;
    }

    async function clearSelection() {
      points = [];
      box = null;
      await fetch("/api/number/clear", {method: "POST"});
      status.textContent = "Selection cleared.";
      scheduleDraw();
    }

    document.getElementById("zoomOut").onclick = () => zoomAt(1 / 1.25, {x: stage.clientWidth / 2, y: stage.clientHeight / 2});
    document.getElementById("zoomIn").onclick = () => zoomAt(1.25, {x: stage.clientWidth / 2, y: stage.clientHeight / 2});
    document.getElementById("fit").onclick = fitImage;
    document.getElementById("clear").onclick = clearSelection;
    document.getElementById("clearSide").onclick = clearSelection;
    document.getElementById("send").onclick = sendSelection;
    document.getElementById("sendSide").onclick = sendSelection;
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
    loadProject();
  </script>
</body>
</html>
"""


class WebEditorServer:
    def __init__(self, app, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.app = app
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self.httpd is not None:
            return self.url

        handler = self._handler_class()
        for candidate in range(self.port, self.port + 25):
            try:
                self.httpd = ThreadingHTTPServer((self.host, candidate), handler)
                self.port = candidate
                break
            except OSError:
                continue
        if self.httpd is None:
            raise RuntimeError("Could not start the web editor server.")

        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def _handler_class(self):
        app = self.app

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                try:
                    self._handle_get()
                except Exception as exc:  # noqa: BLE001 - HTTP boundary.
                    self.send_error(500, str(exc))

            def do_POST(self) -> None:  # noqa: N802
                try:
                    self._handle_post()
                except Exception as exc:  # noqa: BLE001 - HTTP boundary.
                    self.send_error(500, str(exc))

            def log_message(self, _format: str, *args) -> None:
                return

            def _handle_get(self) -> None:
                if self.path == "/" or self.path.startswith("/index") or self.path.startswith("/editor"):
                    self._send(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/logo"):
                    self._send(LOGO_SELECTOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/number"):
                    self._send(NUMBER_SELECTOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                if self.path.startswith("/api/logo/project"):
                    data = app._run_on_ui_thread(app._logo_creator_web_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/logo/reference"):
                    data, content_type = app._run_on_ui_thread(app._logo_creator_reference_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/number/project"):
                    data = app._run_on_ui_thread(app._number_creator_web_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/number/reference"):
                    data, content_type = app._run_on_ui_thread(app._number_creator_reference_image)
                    self._send(data, content_type)
                    return
                if self.path.startswith("/api/project"):
                    data = app._run_on_ui_thread(app._web_editor_project)
                    self._send_json(data)
                    return
                if self.path.startswith("/api/base.png"):
                    self._send(app._run_on_ui_thread(app._web_editor_base_png), "image/png")
                    return
                if self.path.startswith("/api/region.png"):
                    self._send(app._run_on_ui_thread(app._web_editor_region_png), "image/png")
                    return
                if self.path.startswith("/api/uv.png"):
                    self._send(app._run_on_ui_thread(app._web_editor_uv_png), "image/png")
                    return
                if self.path.startswith("/api/image/"):
                    key = unquote(self.path.split("/api/image/", 1)[1].split("?", 1)[0])
                    data, content_type = app._run_on_ui_thread(
                        lambda: app._web_editor_image(key)
                    )
                    self._send(data, content_type)
                    return
                if not self.path.startswith("/api/") and self.path != "/favicon.ico":
                    self._send(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                    return
                self.send_error(404)

            def _handle_post(self) -> None:
                if self.path.startswith("/api/logo/lasso"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._logo_creator_web_lasso(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/logo/clear"):
                    app._run_on_ui_thread(app._logo_creator_web_clear)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/number/selection"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = app._run_on_ui_thread(
                        lambda: app._number_creator_web_selection(payload)
                    )
                    self._send_json(result)
                    return
                if self.path.startswith("/api/number/clear"):
                    app._run_on_ui_thread(app._number_creator_web_clear)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/update"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_update(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/reorder"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_reorder(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/transparency"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_transparency(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/flip"):
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    app._run_on_ui_thread(lambda: app._web_editor_flip(payload))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/api/reset"):
                    app._run_on_ui_thread(app._web_editor_reset)
                    self._send_json({"ok": True})
                    return
                else:
                    self.send_error(404)
                    return

            def _send_json(self, payload) -> None:
                self._send(json.dumps(payload).encode("utf-8"), "application/json")

            def _send(self, body: bytes, content_type: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        return Handler


def image_content_type(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    if extension == ".gif":
        return "image/gif"
    if extension == ".bmp":
        return "image/bmp"
    return "image/png"
