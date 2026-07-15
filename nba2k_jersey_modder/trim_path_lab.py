from __future__ import annotations


TRIM_PATH_LAB_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trim Path Lab</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #171a20; color: #edf1f7; overflow: hidden; }
    header { height: 52px; display: flex; align-items: center; gap: 8px; padding: 0 14px; background: #222833; border-bottom: 1px solid #343b49; }
    header strong { margin-right: 8px; }
    button, select, input { font: inherit; }
    button { background: #f0b429; color: #171a20; border: 0; padding: 8px 12px; border-radius: 5px; font-weight: 600; cursor: pointer; }
    button.secondary { background: #303746; color: #edf1f7; border: 1px solid #475064; }
    button.danger { background: #6a2f35; color: #fff; }
    button:disabled { opacity: .45; cursor: default; }
    #wrap { height: calc(100vh - 53px); display: grid; grid-template-columns: minmax(0, 1fr) 330px; }
    #stage { min-width: 0; min-height: 0; position: relative; overflow: hidden; background: #11141a; }
    canvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: crosshair; }
    aside { border-left: 1px solid #343b49; padding: 12px; overflow: auto; background: #1d222c; }
    h2 { font-size: 14px; margin: 0 0 8px; color: #f8fafc; }
    .panel { border: 1px solid #343b49; border-radius: 6px; padding: 10px; margin-bottom: 10px; background: #202632; }
    .hint, .small { color: #aab3c2; font-size: 12px; line-height: 1.45; }
    .status { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #aab3c2; font-size: 12px; flex: 1; }
    .buttons { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; margin-top: 8px; }
    .buttons button { width: 100%; padding: 7px 8px; }
    label { display: block; color: #aab3c2; font-size: 12px; margin: 9px 0 4px; }
    input[type="range"], select { width: 100%; }
    select { background: #11141a; color: #edf1f7; border: 1px solid #475064; border-radius: 5px; padding: 7px; }
    .range-row { display: grid; grid-template-columns: minmax(0, 1fr) 76px; gap: 8px; align-items: center; }
    output { color: #edf1f7; text-align: right; font-size: 12px; }
    input[type="number"] { width: 100%; min-width: 0; background: #11141a; color: #edf1f7; border: 1px solid #475064; border-radius: 5px; padding: 5px 6px; text-align: right; }
    .check { display: flex; align-items: center; gap: 8px; color: #d7deeb; font-size: 13px; margin-top: 9px; }
    .check input { margin: 0; }
    #pathList { display: grid; gap: 6px; max-height: 170px; overflow: auto; }
    .path-item { width: 100%; text-align: left; background: #2a303c; color: #d7deeb; border: 1px solid #40495a; padding: 8px; }
    .path-item.active { border-color: #f0b429; color: #fff; }
    #patternPreview { width: 100%; height: 56px; object-fit: contain; background: repeating-conic-gradient(#2a303c 0 25%, #202632 0 50%) 50% / 16px 16px; border: 1px solid #40495a; }
    @media (max-width: 820px) {
      #wrap { grid-template-columns: minmax(0, 1fr) 280px; }
      header .optional { display: none; }
    }
  </style>
</head>
<body>
  <header>
    <strong>Trim Path Lab</strong>
    <button id="newPath">New Path</button>
    <button id="finishPath" class="secondary">Finish Path</button>
    <button id="undoPoint" class="secondary">Undo Point</button>
    <button id="fit" class="secondary optional">Fit</button>
    <button id="zoomOut" class="secondary optional">Zoom -</button>
    <button id="zoomIn" class="secondary optional">Zoom +</button>
    <span id="status" class="status">Loading staged trim...</span>
  </header>
  <div id="wrap">
    <main id="stage"><canvas id="canvas"></canvas></main>
    <aside>
      <div class="panel">
        <h2>Trim Creator Source</h2>
        <img id="patternPreview" alt="Selected staged trim">
        <div id="sourceName" class="small">No staged trim selected.</div>
        <button id="reload" class="secondary" style="width:100%; margin-top:8px;">Reload Generator + Trim</button>
      </div>
      <div class="panel">
        <h2>Paths</h2>
        <div id="pathList"></div>
        <div class="buttons">
          <button id="duplicatePath" class="secondary">Duplicate</button>
          <button id="removePath" class="danger">Remove</button>
        </div>
        <div class="buttons">
          <button id="layerDown" class="secondary">Layer Down</button>
          <button id="layerUp" class="secondary">Layer Up</button>
        </div>
      </div>
      <div class="panel">
        <h2>Selected Path</h2>
        <label for="curveMode">Path shape</label>
        <select id="curveMode">
          <option value="smooth">Smooth curve</option>
          <option value="straight" selected>Straight segments</option>
          <option value="t">T shape (3 points)</option>
        </select>
        <label for="angleSnap">Angle snapping while drawing</label>
        <select id="angleSnap">
          <option value="0">Off</option>
          <option value="1" selected>Every 1 degree</option>
          <option value="5">Every 5 degrees</option>
          <option value="15">Every 15 degrees</option>
          <option value="45">Every 45 degrees</option>
        </select>
        <label>Current segment</label>
        <div id="segmentReadout" class="small">Angle: -- | Length: --</div>
        <label for="trimWidth">Trim width</label>
        <div class="range-row"><input id="trimWidth" type="range" min="2" max="300" value="64"><input id="trimWidthNumber" type="number" min="2" max="300" value="64" aria-label="Trim width value"></div>
        <label for="patternScale">Pattern length scale</label>
        <div class="range-row"><input id="patternScale" type="range" min="25" max="400" value="100"><input id="patternScaleNumber" type="number" min="25" max="400" value="100" aria-label="Pattern length scale value"></div>
        <label for="patternOffset">Pattern offset</label>
        <div class="range-row"><input id="patternOffset" type="range" min="-1024" max="1024" value="0"><input id="patternOffsetNumber" type="number" min="-1024" max="1024" value="0" aria-label="Pattern offset value"></div>
        <div class="buttons">
          <button id="createOppositeCopy" class="secondary">Opposite Panel Copy</button>
          <button id="createXMirror" class="secondary">X-Axis Mirror</button>
        </div>
        <label class="check"><input id="pathVisible" type="checkbox" checked> Show this layer</label>
        <label class="check"><input id="linkNewCopies" type="checkbox" checked> Link new mirror copies to the source</label>
        <label class="check"><input id="moveLinked" type="checkbox" checked> Move linked layers together</label>
        <button id="unlinkPath" class="secondary" style="width:100%; margin-top:8px;">Unlink Selected Layer</button>
        <div id="linkStatus" class="small">Layer is not linked.</div>
        <div class="small">Drag directly on a finished trim to move its whole layer. For a T shape, click both crossbar ends, then click the stem end. Angles run clockwise: 0 degrees points right and 90 degrees points down. Right-click finishes the path. Hold Alt while placing a point to bypass snapping.</div>
      </div>
      <div class="panel">
        <h2>View</h2>
        <label for="templateOpacity">Generator preview opacity</label>
        <div class="range-row"><input id="templateOpacity" type="range" min="0" max="100" value="65"><output id="templateOpacityValue">65%</output></div>
        <label class="check"><input id="showUvOverlay" type="checkbox" checked> Show UV overlay</label>
        <label for="uvOpacity">UV opacity</label>
        <div class="range-row"><input id="uvOpacity" type="range" min="0" max="100" value="45"><output id="uvOpacityValue">45%</output></div>
        <label class="check"><input id="showPoints" type="checkbox" checked> Show path points</label>
      </div>
      <div class="panel">
        <h2>Output</h2>
        <button id="sendToGenerator" style="width:100%;">Send Layers to Generator</button>
        <button id="savePng" style="width:100%;">Save Combined Transparent PNG</button>
        <button id="saveSelectedPng" class="secondary" style="width:100%; margin-top:8px;">Save Selected Layer PNG</button>
        <div class="buttons">
          <button id="saveJson" class="secondary">Save Paths</button>
          <button id="loadJson" class="secondary">Load Paths</button>
        </div>
        <input id="loadJsonInput" type="file" accept="application/json,.json" hidden>
        <div class="small">The generator preview, UV overlay, and editing points are guides only. PNG export contains only the trim path layers at the full template resolution.</div>
      </div>
    </aside>
  </div>
  <script>
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");
    const stage = document.getElementById("stage");
    const statusNode = document.getElementById("status");
    const backgroundImage = new Image();
    const uvImage = new Image();
    const patternImage = new Image();
    const patternSampleCanvas = document.createElement("canvas");
    const patternSampleContext = patternSampleCanvas.getContext("2d", {willReadFrequently: true});
    let project = null;
    let paths = [];
    let activePathIndex = -1;
    let selectedPointIndex = -1;
    let drawing = false;
    let viewScale = 1;
    let minScale = 1;
    let panX = 0;
    let panY = 0;
    let panning = false;
    let panStart = null;
    let draggingPoint = false;
    let draggingPath = false;
    let dragPathStart = null;
    let dragPathOriginals = null;
    let livePoint = null;
    let renderQueued = false;
    let patternLengthUniform = false;
    let uvOverlayAvailable = false;

    function setStatus(message) { statusNode.textContent = message; }
    function activePath() { return paths[activePathIndex] || null; }
    function defaultPath() {
      return {name: `Trim Path ${paths.length + 1}`, points: [], width: 64, patternScale: 100, patternOffset: 0, curve: "straight", visible: true, linkGroup: null, reverseCrossSection: false, finished: false};
    }
    function cleanPath(raw, index) {
      const width = Math.max(2, Math.min(300, Number(raw?.width) || 64));
      return {
        name: String(raw?.name || `Trim Path ${index + 1}`),
        points: Array.isArray(raw?.points) ? raw.points.map(point => ({x: Number(point.x) || 0, y: Number(point.y) || 0})) : [],
        width,
        patternScale: Math.max(25, Math.min(400, Number(raw?.patternScale) || 100)),
        patternOffset: Math.max(-1024, Math.min(1024, Number(raw?.patternOffset) || 0)),
        curve: ["smooth", "straight", "t"].includes(raw?.curve) ? raw.curve : "straight",
        visible: raw?.visible !== false,
        linkGroup: raw?.linkGroup ? String(raw.linkGroup) : null,
        reverseCrossSection: Boolean(raw?.reverseCrossSection),
        finished: raw?.finished !== false,
      };
    }

    async function loadProject() {
      try {
        const response = await fetch("/api/trim-path/project", {cache: "no-store"});
        if (!response.ok) throw new Error(`Project failed: ${response.status}`);
        const nextProject = await response.json();
        const previousScope = project ? `${project.garment}:${project.templateName}` : "";
        const nextScope = `${nextProject.garment}:${nextProject.templateName}`;
        if (previousScope && previousScope !== nextScope) {
          saveLocalPaths();
          paths = [];
          activePathIndex = -1;
          selectedPointIndex = -1;
          drawing = false;
        }
        if (!nextProject.hasPattern) {
          project = nextProject;
          setStatus(nextProject.message || "Stage a trim in Trim Creator first.");
          queueDraw();
          return;
        }
        project = nextProject;
        uvOverlayAvailable = Boolean(project.uvOverlay?.available);
        const imageLoads = [
          loadImage(backgroundImage, project.backgroundUrl + "?t=" + Date.now()),
          loadImage(patternImage, project.patternUrl + "?t=" + Date.now()),
        ];
        if (uvOverlayAvailable) {
          imageLoads.push(loadImage(uvImage, project.uvOverlay.imageUrl + "?t=" + Date.now()));
        }
        await Promise.all(imageLoads);
        document.getElementById("showUvOverlay").disabled = !uvOverlayAvailable;
        document.getElementById("uvOpacity").disabled = !uvOverlayAvailable;
        patternSampleCanvas.width = Math.max(1, patternImage.naturalWidth);
        patternSampleCanvas.height = Math.max(1, patternImage.naturalHeight);
        patternSampleContext.clearRect(0, 0, patternSampleCanvas.width, patternSampleCanvas.height);
        patternSampleContext.drawImage(patternImage, 0, 0);
        patternLengthUniform = isLengthUniformPattern();
        document.getElementById("patternPreview").src = patternImage.src;
        document.getElementById("sourceName").textContent = `${project.patternName} | ${project.width} x ${project.height} template`;
        if (!paths.length) restoreLocalPaths();
        fitView();
        setStatus(`Click New Path, then click points along the center of the ${project.garment.toLowerCase()} trim.`);
      } catch (error) {
        setStatus(`Could not load Trim Path Lab: ${error.message}`);
      }
    }

    function loadImage(image, url) {
      return new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error(`Image failed to load: ${url}`));
        image.src = url;
      });
    }

    function resizeCanvas() {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(stage.clientWidth * ratio));
      canvas.height = Math.max(1, Math.floor(stage.clientHeight * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      queueDraw();
    }

    function fitView() {
      if (!project?.width) return;
      minScale = Math.min((stage.clientWidth - 32) / project.width, (stage.clientHeight - 32) / project.height);
      minScale = Math.max(.03, minScale);
      viewScale = minScale;
      panX = (stage.clientWidth - project.width * viewScale) / 2;
      panY = (stage.clientHeight - project.height * viewScale) / 2;
      queueDraw();
    }

    function queueDraw() {
      if (renderQueued) return;
      renderQueued = true;
      requestAnimationFrame(() => { renderQueued = false; draw(); });
    }

    function draw() {
      ctx.save();
      ctx.setTransform(window.devicePixelRatio || 1, 0, 0, window.devicePixelRatio || 1, 0, 0);
      ctx.clearRect(0, 0, stage.clientWidth, stage.clientHeight);
      ctx.fillStyle = "#11141a";
      ctx.fillRect(0, 0, stage.clientWidth, stage.clientHeight);
      if (!project?.width || !backgroundImage.complete || !patternImage.complete) { ctx.restore(); return; }
      ctx.globalAlpha = Number(document.getElementById("templateOpacity").value) / 100;
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(backgroundImage, panX, panY, project.width * viewScale, project.height * viewScale);
      if (uvOverlayAvailable && document.getElementById("showUvOverlay").checked && uvImage.complete) {
        ctx.globalAlpha = Number(document.getElementById("uvOpacity").value) / 100;
        ctx.drawImage(uvImage, panX, panY, project.width * viewScale, project.height * viewScale);
      }
      ctx.globalAlpha = 1;
      ctx.translate(panX, panY);
      ctx.scale(viewScale, viewScale);
      paths.forEach((path, index) => {
        if (path.visible) renderPatternPath(ctx, path, Math.max(1, 1.4 / viewScale));
        if (index === activePathIndex) drawPathGuide(ctx, path);
      });
      ctx.restore();
    }

    function panelPairForPath(path) {
      const left = project?.panelZones?.left;
      const right = project?.panelZones?.right;
      if (!left || !right || !path.points.length) return null;
      const center = path.points.reduce((sum, point) => ({x: sum.x + point.x, y: sum.y + point.y}), {x: 0, y: 0});
      center.x /= path.points.length;
      center.y /= path.points.length;
      const zoneDistance = zone => Math.hypot(center.x - (zone.x + zone.width / 2), center.y - (zone.y + zone.height / 2));
      const source = zoneDistance(left) <= zoneDistance(right) ? left : right;
      return {source, target: source === left ? right : left};
    }

    function oppositePanelPath(path) {
      const pair = panelPairForPath(path);
      if (!pair) {
        const centerY = path.points.reduce((sum, point) => sum + point.y, 0) / path.points.length;
        const deltaY = centerY < project.height / 2 ? project.height / 2 : -project.height / 2;
        return {
          ...path,
          points: path.points.map(point => ({x: point.x, y: point.y + deltaY})),
          reverseCrossSection: Boolean(path.reverseCrossSection),
        };
      }
      const {source, target} = pair;
      const deltaX = target.x + target.width / 2 - (source.x + source.width / 2);
      const deltaY = target.y + target.height / 2 - (source.y + source.height / 2);
      return {
        ...path,
        points: path.points.map(point => ({x: point.x + deltaX, y: point.y + deltaY})),
        reverseCrossSection: Boolean(path.reverseCrossSection),
      };
    }

    function samePanelXMirrorPath(path) {
      const pair = panelPairForPath(path);
      const source = pair?.source;
      if (!source) {
        return {
          ...path,
          points: path.points.map(point => ({x: project.width - point.x, y: point.y})),
          reverseCrossSection: true,
        };
      }
      return {
        ...path,
        points: path.points.map(point => {
          const normalizedX = (point.x - source.x) / Math.max(1, source.width);
          return {x: source.x + (1 - normalizedX) * source.width, y: point.y};
        }),
        reverseCrossSection: true,
      };
    }

    function tJunction(path) {
      if (path.points.length < 2) return null;
      return {
        x: (path.points[0].x + path.points[1].x) / 2,
        y: (path.points[0].y + path.points[1].y) / 2,
      };
    }

    function pathPointRuns(path) {
      if (path.curve !== "t") return [path.points];
      const runs = [];
      if (path.points.length >= 2) runs.push([path.points[0], path.points[1]]);
      const junction = tJunction(path);
      if (junction && path.points.length >= 3) runs.push([junction, path.points[2]]);
      return runs;
    }

    function tRenderPointRuns(path) {
      if (path.curve !== "t" || path.points.length < 3) return pathPointRuns(path);
      const crossbarStart = path.points[0];
      const crossbarEnd = path.points[1];
      const stemEnd = path.points[2];
      const junction = tJunction(path);
      const crossbarLength = Math.hypot(
        crossbarEnd.x - crossbarStart.x,
        crossbarEnd.y - crossbarStart.y,
      );
      const stemLength = Math.hypot(stemEnd.x - junction.x, stemEnd.y - junction.y);
      if (crossbarLength < .01 || stemLength < .01) {
        return [[crossbarStart, crossbarEnd]];
      }
      const crossbarNormal = {
        x: -(crossbarEnd.y - crossbarStart.y) / crossbarLength,
        y: (crossbarEnd.x - crossbarStart.x) / crossbarLength,
      };
      const stemDirection = {
        x: (stemEnd.x - junction.x) / stemLength,
        y: (stemEnd.y - junction.y) / stemLength,
      };
      const normalAmount = Math.max(
        .05,
        Math.abs(
          stemDirection.x * crossbarNormal.x + stemDirection.y * crossbarNormal.y,
        ),
      );
      const overlap = Math.min(.75, path.width * .05);
      const boundaryDistance = Math.min(
        stemLength,
        Math.max(0, path.width / 2 - overlap) / normalAmount,
      );
      const stemStart = {
        x: junction.x + stemDirection.x * boundaryDistance,
        y: junction.y + stemDirection.y * boundaryDistance,
      };
      // Draw the stem first and the crossbar last so its bands stay uninterrupted.
      return [[stemStart, stemEnd], [crossbarStart, crossbarEnd]];
    }

    function minimumPathPoints(path) {
      return path?.curve === "t" ? 3 : 2;
    }

    function pathIsRenderable(path) {
      return path.points.length >= minimumPathPoints(path);
    }

    function centerlineSamples(path, targetStep) {
      const points = path.points;
      if (points.length < 2) return points.slice();
      if (path.curve === "straight" || points.length < 3) return straightSamples(points, targetStep);
      const samples = [];
      for (let index = 0; index < points.length - 1; index++) {
        const p0 = points[Math.max(0, index - 1)];
        const p1 = points[index];
        const p2 = points[index + 1];
        const p3 = points[Math.min(points.length - 1, index + 2)];
        const distance = Math.hypot(p2.x - p1.x, p2.y - p1.y);
        const steps = Math.max(2, Math.ceil(distance / targetStep));
        for (let step = index === 0 ? 0 : 1; step <= steps; step++) {
          const t = step / steps;
          const t2 = t * t;
          const t3 = t2 * t;
          samples.push({
            x: .5 * ((2 * p1.x) + (-p0.x + p2.x) * t + (2*p0.x - 5*p1.x + 4*p2.x - p3.x) * t2 + (-p0.x + 3*p1.x - 3*p2.x + p3.x) * t3),
            y: .5 * ((2 * p1.y) + (-p0.y + p2.y) * t + (2*p0.y - 5*p1.y + 4*p2.y - p3.y) * t2 + (-p0.y + 3*p1.y - 3*p2.y + p3.y) * t3),
          });
        }
      }
      return samples;
    }

    function straightSamples(points, targetStep) {
      const samples = [];
      for (let index = 0; index < points.length - 1; index++) {
        const start = points[index];
        const end = points[index + 1];
        const distance = Math.hypot(end.x - start.x, end.y - start.y);
        const steps = Math.max(1, Math.ceil(distance / targetStep));
        for (let step = index === 0 ? 0 : 1; step <= steps; step++) {
          const amount = step / steps;
          samples.push({x: start.x + (end.x - start.x) * amount, y: start.y + (end.y - start.y) * amount});
        }
      }
      return samples;
    }

    function sampledPatternRow(sourceY) {
      const width = patternSampleCanvas.width;
      const sampleXs = [.08, .27, .5, .73, .92].map(amount =>
        Math.max(0, Math.min(width - 1, Math.round((width - 1) * amount)))
      );
      const totals = [0, 0, 0, 0];
      sampleXs.forEach(sourceX => {
        const pixel = patternSampleContext.getImageData(sourceX, sourceY, 1, 1).data;
        for (let channel = 0; channel < 4; channel++) totals[channel] += pixel[channel];
      });
      return totals.map(value => Math.round(value / sampleXs.length));
    }

    function isLengthUniformPattern() {
      const width = patternSampleCanvas.width;
      const height = patternSampleCanvas.height;
      if (width < 2 || height < 1) return true;
      const sampleXs = [.08, .27, .5, .73, .92].map(amount =>
        Math.max(0, Math.min(width - 1, Math.round((width - 1) * amount)))
      );
      const rowStep = Math.max(1, Math.floor(height / 256));
      let comparisons = 0;
      let mismatches = 0;
      for (let sourceY = 0; sourceY < height; sourceY += rowStep) {
        const reference = patternSampleContext.getImageData(sampleXs[2], sourceY, 1, 1).data;
        sampleXs.forEach(sourceX => {
          const pixel = patternSampleContext.getImageData(sourceX, sourceY, 1, 1).data;
          comparisons++;
          if ([0, 1, 2, 3].some(channel => Math.abs(pixel[channel] - reference[channel]) > 10)) {
            mismatches++;
          }
        });
      }
      return comparisons === 0 || mismatches / comparisons <= .02;
    }

    function miterOffsetPoint(points, index, distance, maximumMiter) {
      const current = points[index];
      const previous = points[Math.max(0, index - 1)];
      const next = points[Math.min(points.length - 1, index + 1)];
      const incomingLength = Math.hypot(current.x - previous.x, current.y - previous.y);
      const outgoingLength = Math.hypot(next.x - current.x, next.y - current.y);
      if (index === 0 || incomingLength < .01) {
        const length = Math.max(.01, outgoingLength);
        return {x: current.x - (next.y - current.y) / length * distance, y: current.y + (next.x - current.x) / length * distance};
      }
      if (index === points.length - 1 || outgoingLength < .01) {
        return {x: current.x - (current.y - previous.y) / incomingLength * distance, y: current.y + (current.x - previous.x) / incomingLength * distance};
      }
      const incoming = {x: (current.x - previous.x) / incomingLength, y: (current.y - previous.y) / incomingLength};
      const outgoing = {x: (next.x - current.x) / outgoingLength, y: (next.y - current.y) / outgoingLength};
      const incomingNormal = {x: -incoming.y, y: incoming.x};
      const outgoingNormal = {x: -outgoing.y, y: outgoing.x};
      const miterRaw = {x: incomingNormal.x + outgoingNormal.x, y: incomingNormal.y + outgoingNormal.y};
      const magnitude = Math.hypot(miterRaw.x, miterRaw.y);
      if (magnitude < .01) {
        return {x: current.x + incomingNormal.x * distance, y: current.y + incomingNormal.y * distance};
      }
      const miter = {x: miterRaw.x / magnitude, y: miterRaw.y / magnitude};
      const denominator = Math.max(.05, Math.abs(miter.x * incomingNormal.x + miter.y * incomingNormal.y));
      const miterLength = Math.max(-maximumMiter, Math.min(maximumMiter, distance / denominator));
      return {x: current.x + miter.x * miterLength, y: current.y + miter.y * miterLength};
    }

    function renderUniformPatternPath(target, path, samples) {
      const points = path.curve === "straight" ? path.points : samples;
      if (points.length < 2) return false;
      const sourceHeight = Math.max(1, patternSampleCanvas.height);
      const bands = [];
      const colorsClose = (first, second) => first.every((value, channel) => Math.abs(value - second[channel]) <= 5);
      for (let sourceY = 0; sourceY < sourceHeight; sourceY++) {
        const color = sampledPatternRow(sourceY);
        const currentBand = bands[bands.length - 1];
        if (currentBand && colorsClose(currentBand.color, color)) {
          currentBand.end = sourceY + 1;
        } else {
          bands.push({start: sourceY, end: sourceY + 1, color});
        }
      }
      const halfWidth = path.width / 2;
      const lateralPosition = sourceY => {
        const amount = sourceY / sourceHeight;
        return path.reverseCrossSection
          ? halfWidth - amount * path.width
          : -halfWidth + amount * path.width;
      };
      bands.forEach(band => {
        if (band.color[3] <= 2) return;
        let firstOffset = lateralPosition(band.start);
        let secondOffset = lateralPosition(band.end);
        const direction = Math.sign(secondOffset - firstOffset) || 1;
        firstOffset -= direction * .12;
        secondOffset += direction * .12;
        const firstEdge = points.map((_point, index) => miterOffsetPoint(points, index, firstOffset, path.width * 4));
        const secondEdge = points.map((_point, index) => miterOffsetPoint(points, index, secondOffset, path.width * 4)).reverse();
        const polygon = firstEdge.concat(secondEdge);
        target.beginPath();
        polygon.forEach((point, index) => index ? target.lineTo(point.x, point.y) : target.moveTo(point.x, point.y));
        target.closePath();
        target.fillStyle = `rgba(${band.color[0]}, ${band.color[1]}, ${band.color[2]}, ${band.color[3] / 255})`;
        target.fill();
      });
      return true;
    }

    function drawCornerJoin(target, path, previous, current, next, sourceX, sourceHeight) {
      const incomingLength = Math.hypot(current.x - previous.x, current.y - previous.y);
      const outgoingLength = Math.hypot(next.x - current.x, next.y - current.y);
      if (incomingLength < .01 || outgoingLength < .01) return;
      const incoming = {
        x: (current.x - previous.x) / incomingLength,
        y: (current.y - previous.y) / incomingLength,
      };
      const outgoing = {
        x: (next.x - current.x) / outgoingLength,
        y: (next.y - current.y) / outgoingLength,
      };
      const dot = Math.max(-1, Math.min(1, incoming.x * outgoing.x + incoming.y * outgoing.y));
      const turn = Math.acos(dot);
      if (turn < .01 || turn > Math.PI - .01) return;
      const incomingNormal = {x: -incoming.y, y: incoming.x};
      const outgoingNormal = {x: -outgoing.y, y: outgoing.x};
      const miterRaw = {
        x: incomingNormal.x + outgoingNormal.x,
        y: incomingNormal.y + outgoingNormal.y,
      };
      const miterMagnitude = Math.hypot(miterRaw.x, miterRaw.y);
      if (miterMagnitude < .01) return;
      const miter = {x: miterRaw.x / miterMagnitude, y: miterRaw.y / miterMagnitude};
      const halfWidth = path.width / 2;
      const denominator = Math.abs(miter.x * incomingNormal.x + miter.y * incomingNormal.y);
      const safeDenominator = Math.max(.05, denominator);
      const offsetPoint = (normal, distance) => ({
        x: current.x + normal.x * distance,
        y: current.y + normal.y * distance,
      });
      const miterPoint = distance => {
        const length = Math.max(-path.width * 4, Math.min(path.width * 4, distance / safeDenominator));
        return {x: current.x + miter.x * length, y: current.y + miter.y * length};
      };
      const lateralPosition = sourceY => {
        const amount = sourceY / sourceHeight;
        return path.reverseCrossSection
          ? halfWidth - amount * path.width
          : -halfWidth + amount * path.width;
      };
      for (let sourceY = 0; sourceY < sourceHeight; sourceY++) {
        const sourcePixel = patternSampleContext.getImageData(
          Math.max(0, Math.min(patternSampleCanvas.width - 1, Math.floor(sourceX))),
          sourceY,
          1,
          1,
        ).data;
        if (!sourcePixel[3]) continue;
        let firstOffset = lateralPosition(sourceY);
        let secondOffset = lateralPosition(sourceY + 1);
        const rowWidth = Math.abs(secondOffset - firstOffset);
        const overlap = Math.min(.65, Math.max(.18, rowWidth * .45));
        const direction = Math.sign(secondOffset - firstOffset) || 1;
        firstOffset -= direction * overlap;
        secondOffset += direction * overlap;
        const polygon = [
          offsetPoint(incomingNormal, firstOffset),
          miterPoint(firstOffset),
          offsetPoint(outgoingNormal, firstOffset),
          offsetPoint(outgoingNormal, secondOffset),
          miterPoint(secondOffset),
          offsetPoint(incomingNormal, secondOffset),
        ];
        target.save();
        target.beginPath();
        polygon.forEach((corner, index) => index ? target.lineTo(corner.x, corner.y) : target.moveTo(corner.x, corner.y));
        target.closePath();
        target.fillStyle = `rgba(${sourcePixel[0]}, ${sourcePixel[1]}, ${sourcePixel[2]}, ${sourcePixel[3] / 255})`;
        target.fill();
        target.restore();
      }
    }

    function renderPatternPolyline(target, path, targetStep) {
      const samples = centerlineSamples(path, targetStep);
      if (samples.length < 2 || !patternImage.complete) return;
      if (patternLengthUniform && renderUniformPatternPath(target, path, samples)) return;
      const cornerFlags = samples.map((_sample, index) => {
        if (index <= 0 || index >= samples.length - 1) return false;
        const previous = samples[index - 1];
        const current = samples[index];
        const next = samples[index + 1];
        const incomingX = current.x - previous.x;
        const incomingY = current.y - previous.y;
        const outgoingX = next.x - current.x;
        const outgoingY = next.y - current.y;
        const denominator = Math.max(.01, Math.hypot(incomingX, incomingY) * Math.hypot(outgoingX, outgoingY));
        const cornerDot = Math.max(-1, Math.min(1, (incomingX * outgoingX + incomingY * outgoingY) / denominator));
        return Math.acos(cornerDot) >= .01;
      });
      let distance = 0;
      const sourceWidth = Math.max(1, patternImage.naturalWidth);
      const sourceHeight = Math.max(1, patternImage.naturalHeight);
      const lengthScale = path.patternScale / 100;
      target.save();
      for (let index = 0; index < samples.length; index++) {
        const previous = samples[Math.max(0, index - 1)];
        const current = samples[index];
        const next = samples[Math.min(samples.length - 1, index + 1)];
        if (index > 0) distance += Math.hypot(current.x - previous.x, current.y - previous.y);
        const angle = Math.atan2(next.y - previous.y, next.x - previous.x);
        const sourceX = ((distance + path.patternOffset) / lengthScale % sourceWidth + sourceWidth) % sourceWidth;
        const isCorner = cornerFlags[index];
        if (!isCorner) {
          const previousDistance = index > 0
            ? Math.hypot(current.x - previous.x, current.y - previous.y)
            : 0;
          const nextDistance = index < samples.length - 1
            ? Math.hypot(next.x - current.x, next.y - current.y)
            : 0;
          let leftExtent = index === 0 ? 0 : previousDistance / 2 + .08;
          let rightExtent = index === samples.length - 1 ? 0 : nextDistance / 2 + .08;
          if (index > 0 && cornerFlags[index - 1]) leftExtent = previousDistance + .05;
          if (index < samples.length - 1 && cornerFlags[index + 1]) rightExtent = nextDistance + .05;
          target.save();
          target.translate(current.x, current.y);
          target.rotate(angle);
          const destinationY = path.reverseCrossSection ? path.width / 2 : -path.width / 2;
          const destinationHeight = path.reverseCrossSection ? -path.width : path.width;
          target.drawImage(
            patternImage,
            Math.floor(sourceX),
            0,
            1,
            sourceHeight,
            -leftExtent,
            destinationY,
            Math.max(.01, leftExtent + rightExtent),
            destinationHeight,
          );
          target.restore();
        }
        if (isCorner) {
          drawCornerJoin(target, path, previous, current, next, sourceX, sourceHeight);
        }
      }
      target.restore();
    }

    function renderPatternPath(target, path, targetStep) {
      if (path.curve !== "t") {
        renderPatternPolyline(target, path, targetStep);
        return;
      }
      tRenderPointRuns(path).forEach(points => {
        if (points.length < 2) return;
        renderPatternPolyline(target, {...path, points, curve: "straight"}, targetStep);
      });
    }

    function drawPathGuide(target, path) {
      if (path.points.length) {
        target.save();
        target.strokeStyle = "#f0b429";
        target.lineWidth = 2 / viewScale;
        target.setLineDash([8 / viewScale, 6 / viewScale]);
        target.beginPath();
        pathPointRuns(path).forEach(points => {
          points.forEach((point, index) => index ? target.lineTo(point.x, point.y) : target.moveTo(point.x, point.y));
        });
        target.stroke();
        target.setLineDash([]);
        if (document.getElementById("showPoints").checked) {
          path.points.forEach((point, index) => {
            target.beginPath();
            target.arc(point.x, point.y, (index === selectedPointIndex ? 8 : 6) / viewScale, 0, Math.PI * 2);
            target.fillStyle = index === selectedPointIndex ? "#fff" : "#f0b429";
            target.strokeStyle = "#11141a";
            target.lineWidth = 2 / viewScale;
            target.fill();
            target.stroke();
          });
          const junction = path.curve === "t" ? tJunction(path) : null;
          if (junction) {
            target.beginPath();
            target.arc(junction.x, junction.y, 5 / viewScale, 0, Math.PI * 2);
            target.fillStyle = "#55d6ff";
            target.fill();
          }
        }
        if (drawing && !path.finished && livePoint && path.points.length) {
          drawLiveSegment(target, drawingStartPoint(path), livePoint);
        }
        target.restore();
      }
    }

    function segmentMetrics(start, end) {
      const deltaX = end.x - start.x;
      const deltaY = end.y - start.y;
      return {
        angle: (Math.atan2(deltaY, deltaX) * 180 / Math.PI + 360) % 360,
        length: Math.hypot(deltaX, deltaY),
      };
    }

    function drawLiveSegment(target, start, end) {
      const metrics = segmentMetrics(start, end);
      target.save();
      target.strokeStyle = "#55d6ff";
      target.lineWidth = 3 / viewScale;
      target.setLineDash([]);
      target.beginPath();
      target.moveTo(start.x, start.y);
      target.lineTo(end.x, end.y);
      target.stroke();

      const label = `${metrics.angle.toFixed(2)} deg | ${Math.round(metrics.length)} px`;
      const fontSize = 14 / viewScale;
      target.font = `600 ${fontSize}px Segoe UI, Arial, sans-serif`;
      const padding = 5 / viewScale;
      const textWidth = target.measureText(label).width;
      const labelX = (start.x + end.x) / 2;
      const labelY = (start.y + end.y) / 2 - 12 / viewScale;
      target.fillStyle = "rgba(17, 20, 26, .88)";
      target.fillRect(
        labelX - textWidth / 2 - padding,
        labelY - fontSize,
        textWidth + padding * 2,
        fontSize + padding * 2,
      );
      target.fillStyle = "#eaf9ff";
      target.textAlign = "center";
      target.textBaseline = "alphabetic";
      target.fillText(label, labelX, labelY + padding / 2);
      target.restore();
    }

    function canvasPoint(event) {
      const rect = canvas.getBoundingClientRect();
      return {x: event.clientX - rect.left, y: event.clientY - rect.top};
    }
    function imagePoint(event) {
      const point = canvasPoint(event);
      return {x: Math.max(0, Math.min(project.width, (point.x - panX) / viewScale)), y: Math.max(0, Math.min(project.height, (point.y - panY) / viewScale))};
    }
    function drawingStartPoint(path) {
      if (path?.curve === "t" && path.points.length === 2) {
        return tJunction(path);
      }
      return path?.points[path.points.length - 1] || null;
    }
    function drawingPoint(event) {
      const raw = imagePoint(event);
      const path = activePath();
      if (!path?.points.length || event.altKey) return raw;
      const snapDegrees = Number(document.getElementById("angleSnap").value) || 0;
      if (!snapDegrees) return raw;
      const start = drawingStartPoint(path);
      const deltaX = raw.x - start.x;
      const deltaY = raw.y - start.y;
      const length = Math.hypot(deltaX, deltaY);
      if (length < .01) return raw;
      const step = snapDegrees * Math.PI / 180;
      const angle = Math.round(Math.atan2(deltaY, deltaX) / step) * step;
      return {
        x: Math.max(0, Math.min(project.width, start.x + Math.cos(angle) * length)),
        y: Math.max(0, Math.min(project.height, start.y + Math.sin(angle) * length)),
      };
    }
    function updateSegmentReadout() {
      const path = activePath();
      let start = null;
      let end = null;
      if (drawing && path?.points.length && livePoint) {
        start = drawingStartPoint(path);
        end = livePoint;
      } else if (path?.curve === "t" && path.points.length >= 3) {
        start = tJunction(path);
        end = path.points[2];
      } else if (path?.points.length >= 2) {
        start = path.points[path.points.length - 2];
        end = path.points[path.points.length - 1];
      }
      const readout = document.getElementById("segmentReadout");
      if (!start || !end) {
        readout.textContent = "Angle: -- | Length: --";
        return;
      }
      const metrics = segmentMetrics(start, end);
      readout.textContent = `Angle: ${metrics.angle.toFixed(2)} degrees | Length: ${metrics.length.toFixed(1)} px`;
    }
    function hitPoint(event) {
      const path = activePath();
      if (!path) return -1;
      const point = canvasPoint(event);
      const radius = 13;
      return path.points.findIndex(candidate => Math.hypot(panX + candidate.x * viewScale - point.x, panY + candidate.y * viewScale - point.y) <= radius);
    }

    function pointToSegmentDistance(point, start, end) {
      const deltaX = end.x - start.x;
      const deltaY = end.y - start.y;
      const lengthSquared = deltaX * deltaX + deltaY * deltaY;
      if (!lengthSquared) return Math.hypot(point.x - start.x, point.y - start.y);
      const amount = Math.max(0, Math.min(1, ((point.x - start.x) * deltaX + (point.y - start.y) * deltaY) / lengthSquared));
      return Math.hypot(point.x - (start.x + amount * deltaX), point.y - (start.y + amount * deltaY));
    }

    function hitActivePath(event) {
      const path = activePath();
      if (!path?.visible || !pathIsRenderable(path) || !path.finished) return false;
      const point = imagePoint(event);
      const threshold = path.width / 2 + 12 / viewScale;
      for (const points of pathPointRuns(path)) {
        const samples = centerlineSamples(
          {...path, points, curve: path.curve === "t" ? "straight" : path.curve},
          Math.max(4, 10 / viewScale),
        );
        for (let index = 0; index < samples.length - 1; index++) {
          if (pointToSegmentDistance(point, samples[index], samples[index + 1]) <= threshold) return true;
        }
      }
      return false;
    }

    function movementIndexes() {
      const path = activePath();
      if (!path) return [];
      if (!document.getElementById("moveLinked").checked || !path.linkGroup) return [activePathIndex];
      return paths.map((candidate, index) => candidate.linkGroup === path.linkGroup ? index : -1).filter(index => index >= 0);
    }

    function movedPointSets(originals, deltaX, deltaY) {
      const allPoints = originals.flatMap(item => item.points);
      if (!allPoints.length) return {deltaX, deltaY};
      const minX = Math.min(...allPoints.map(point => point.x));
      const maxX = Math.max(...allPoints.map(point => point.x));
      const minY = Math.min(...allPoints.map(point => point.y));
      const maxY = Math.max(...allPoints.map(point => point.y));
      return {
        deltaX: Math.max(-minX, Math.min(project.width - maxX, deltaX)),
        deltaY: Math.max(-minY, Math.min(project.height - maxY, deltaY)),
      };
    }

    function beginPathMove(event) {
      const indexes = movementIndexes();
      dragPathStart = imagePoint(event);
      dragPathOriginals = indexes.map(index => ({index, points: paths[index].points.map(point => ({...point}))}));
      draggingPath = true;
      setStatus(indexes.length > 1 ? `Moving ${indexes.length} linked trim layers.` : `Moving ${activePath().name}.`);
    }

    function updatePathMove(event) {
      if (!draggingPath || !dragPathStart || !dragPathOriginals) return;
      const current = imagePoint(event);
      const delta = movedPointSets(dragPathOriginals, current.x - dragPathStart.x, current.y - dragPathStart.y);
      dragPathOriginals.forEach(item => {
        paths[item.index].points = item.points.map(point => ({x: point.x + delta.deltaX, y: point.y + delta.deltaY}));
      });
      updateSegmentReadout();
      queueDraw();
    }

    function moveSelectedLayers(deltaX, deltaY) {
      const originals = movementIndexes().map(index => ({index, points: paths[index].points.map(point => ({...point}))}));
      const delta = movedPointSets(originals, deltaX, deltaY);
      originals.forEach(item => {
        paths[item.index].points = item.points.map(point => ({x: point.x + delta.deltaX, y: point.y + delta.deltaY}));
      });
      updateSegmentReadout();
      saveLocalPaths();
      queueDraw();
    }

    canvas.addEventListener("pointerdown", event => {
      if (!project?.hasPattern) return;
      canvas.setPointerCapture(event.pointerId);
      if (event.button === 2) {
        finishPath();
        return;
      }
      if (event.button === 1 || event.shiftKey) {
        panning = true;
        const point = canvasPoint(event);
        panStart = {x: point.x, y: point.y, panX, panY};
        return;
      }
      const hit = hitPoint(event);
      if (hit >= 0) {
        selectedPointIndex = hit;
        draggingPoint = true;
        queueDraw();
        return;
      }
      const path = activePath();
      if (drawing && path && !path.finished) {
        path.points.push(drawingPoint(event));
        selectedPointIndex = path.points.length - 1;
        livePoint = null;
        if (path.curve === "t" && path.points.length >= 3) {
          finishPath();
          return;
        }
        updateSegmentReadout();
        saveLocalPaths();
        updatePathList();
        queueDraw();
      } else if (hitActivePath(event)) {
        selectedPointIndex = -1;
        beginPathMove(event);
      } else {
        selectedPointIndex = -1;
        queueDraw();
      }
    });
    canvas.addEventListener("pointermove", event => {
      if (panning && panStart) {
        const point = canvasPoint(event);
        panX = panStart.panX + point.x - panStart.x;
        panY = panStart.panY + point.y - panStart.y;
        queueDraw();
      } else if (draggingPoint && selectedPointIndex >= 0 && activePath()) {
        activePath().points[selectedPointIndex] = imagePoint(event);
        updateSegmentReadout();
        queueDraw();
      } else if (draggingPath) {
        updatePathMove(event);
      } else if (drawing && activePath() && !activePath().finished && activePath().points.length) {
        livePoint = drawingPoint(event);
        updateSegmentReadout();
        queueDraw();
      }
    });
    canvas.addEventListener("pointerup", () => {
      if (draggingPoint || draggingPath) saveLocalPaths();
      panning = false;
      panStart = null;
      draggingPoint = false;
      draggingPath = false;
      dragPathStart = null;
      dragPathOriginals = null;
    });
    canvas.addEventListener("pointerleave", () => {
      if (!panning && !draggingPoint && !draggingPath) {
        livePoint = null;
        updateSegmentReadout();
        queueDraw();
      }
    });
    canvas.addEventListener("contextmenu", event => event.preventDefault());
    canvas.addEventListener("wheel", event => {
      event.preventDefault();
      const point = canvasPoint(event);
      const beforeX = (point.x - panX) / viewScale;
      const beforeY = (point.y - panY) / viewScale;
      viewScale = Math.max(minScale * .5, Math.min(12, viewScale * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
      panX = point.x - beforeX * viewScale;
      panY = point.y - beforeY * viewScale;
      queueDraw();
    }, {passive: false});

    function newPath() {
      paths.push(defaultPath());
      activePathIndex = paths.length - 1;
      selectedPointIndex = -1;
      livePoint = null;
      drawing = true;
      syncControls();
      updatePathList();
      setStatus("Click multiple points along the trim center, then right-click or click Finish Path.");
      queueDraw();
    }
    function finishPath() {
      const path = activePath();
      if (!path || path.points.length < minimumPathPoints(path)) {
        setStatus(path?.curve === "t" ? "A T shape needs two crossbar ends and one stem end." : "Add at least two points before finishing the path.");
        return;
      }
      path.finished = true;
      drawing = false;
      selectedPointIndex = -1;
      livePoint = null;
      updateSegmentReadout();
      saveLocalPaths();
      updatePathList();
      setStatus(`${path.name} finished. Drag any point to refine the shape.`);
      queueDraw();
    }
    function undoPoint() {
      const path = activePath();
      if (!path?.points.length) return;
      path.points.pop();
      path.finished = false;
      drawing = true;
      selectedPointIndex = path.points.length - 1;
      livePoint = null;
      updateSegmentReadout();
      saveLocalPaths();
      updatePathList();
      queueDraw();
    }
    function removePath() {
      if (activePathIndex < 0) return;
      paths.splice(activePathIndex, 1);
      activePathIndex = Math.min(activePathIndex, paths.length - 1);
      selectedPointIndex = -1;
      drawing = false;
      livePoint = null;
      updateSegmentReadout();
      saveLocalPaths();
      syncControls();
      updatePathList();
      queueDraw();
    }
    function duplicatePath() {
      const path = activePath();
      if (!path) return;
      const copy = cleanPath(JSON.parse(JSON.stringify(path)), paths.length);
      copy.name = `${path.name} Copy`;
      copy.points = copy.points.map(point => ({x: point.x + 16, y: point.y + 16}));
      copy.linkGroup = null;
      paths.push(copy);
      activePathIndex = paths.length - 1;
      syncControls();
      updatePathList();
      saveLocalPaths();
      queueDraw();
    }

    function createLinkGroup() {
      return `trim-link-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function createDerivedPath(transform, suffix) {
      const source = activePath();
      if (!source || !source.finished || !pathIsRenderable(source)) {
        setStatus("Create or select a finished trim path first.");
        return;
      }
      const copy = cleanPath(transform(source), paths.length);
      copy.name = `${source.name} ${suffix}`;
      copy.finished = true;
      copy.visible = true;
      if (document.getElementById("linkNewCopies").checked) {
        source.linkGroup = source.linkGroup || createLinkGroup();
        copy.linkGroup = source.linkGroup;
      } else {
        copy.linkGroup = null;
      }
      paths.push(copy);
      activePathIndex = paths.length - 1;
      selectedPointIndex = -1;
      drawing = false;
      syncControls();
      updatePathList();
      saveLocalPaths();
      setStatus(`${copy.name} created as its own trim layer.`);
      queueDraw();
    }

    function unlinkSelectedPath() {
      const path = activePath();
      if (!path) return;
      path.linkGroup = null;
      syncControls();
      updatePathList();
      saveLocalPaths();
      setStatus(`${path.name} is now independent.`);
    }

    function moveLayer(direction) {
      if (activePathIndex < 0) return;
      const destination = activePathIndex + direction;
      if (destination < 0 || destination >= paths.length) return;
      [paths[activePathIndex], paths[destination]] = [paths[destination], paths[activePathIndex]];
      activePathIndex = destination;
      syncControls();
      updatePathList();
      saveLocalPaths();
      queueDraw();
    }
    function updatePathList() {
      const list = document.getElementById("pathList");
      list.innerHTML = "";
      if (!paths.length) list.innerHTML = '<div class="small">No paths yet. Click New Path to begin.</div>';
      paths.forEach((path, index) => {
        const button = document.createElement("button");
        button.className = `path-item${index === activePathIndex ? " active" : ""}`;
        const flags = [path.linkGroup ? "linked" : "", path.visible ? "" : "hidden"].filter(Boolean);
        button.textContent = `${index + 1}. ${path.name} | ${path.points.length} points | ${Math.round(path.width)} px${flags.length ? ` | ${flags.join(", ")}` : ""}`;
        button.onclick = () => {
          activePathIndex = index;
          selectedPointIndex = -1;
          drawing = !path.finished;
          livePoint = null;
          syncControls();
          updatePathList();
          queueDraw();
        };
        list.appendChild(button);
      });
    }
    function syncControls() {
      const path = activePath();
      const disabled = !path;
      ["curveMode", "trimWidth", "trimWidthNumber", "patternScale", "patternScaleNumber", "patternOffset", "patternOffsetNumber", "createOppositeCopy", "createXMirror", "pathVisible", "duplicatePath", "removePath", "layerDown", "layerUp", "unlinkPath", "saveSelectedPng"].forEach(id => document.getElementById(id).disabled = disabled);
      document.getElementById("linkStatus").textContent = "Layer is not linked.";
      if (!path) {
        updateSegmentReadout();
        return;
      }
      document.getElementById("curveMode").value = path.curve;
      document.getElementById("trimWidth").value = path.width;
      document.getElementById("patternScale").value = path.patternScale;
      document.getElementById("patternOffset").value = path.patternOffset;
      document.getElementById("pathVisible").checked = path.visible;
      document.getElementById("layerDown").disabled = activePathIndex <= 0;
      document.getElementById("layerUp").disabled = activePathIndex >= paths.length - 1;
      const linkedCount = path.linkGroup ? paths.filter(candidate => candidate.linkGroup === path.linkGroup).length : 0;
      document.getElementById("linkStatus").textContent = linkedCount > 1 ? `Linked group: ${linkedCount} layers.` : "Layer is not linked.";
      updateSegmentReadout();
      updateControlLabels();
    }
    function updateControlLabels() {
      document.getElementById("trimWidthNumber").value = document.getElementById("trimWidth").value;
      document.getElementById("patternScaleNumber").value = document.getElementById("patternScale").value;
      document.getElementById("patternOffsetNumber").value = document.getElementById("patternOffset").value;
      document.getElementById("templateOpacityValue").value = `${document.getElementById("templateOpacity").value}%`;
      document.getElementById("uvOpacityValue").value = `${document.getElementById("uvOpacity").value}%`;
    }
    function bindPathControl(id, property, conversion = value => value) {
      document.getElementById(id).addEventListener("input", event => {
        const path = activePath();
        if (!path) return;
        path[property] = conversion(event.target.type === "checkbox" ? event.target.checked : event.target.value);
        updateControlLabels();
        updatePathList();
        saveLocalPaths();
        queueDraw();
      });
    }
    function changePathShape(event) {
      const path = activePath();
      if (!path) return;
      path.curve = ["smooth", "straight", "t"].includes(event.target.value)
        ? event.target.value
        : "straight";
      if (path.curve === "t") {
        path.points = path.points.slice(0, 3);
        path.finished = path.points.length >= 3;
        drawing = !path.finished;
        setStatus(path.finished
          ? `${path.name} changed to a T shape.`
          : "T shape: click two crossbar ends, then click the stem end.");
      } else if (path.points.length < 2) {
        path.finished = false;
        drawing = true;
      }
      selectedPointIndex = -1;
      livePoint = null;
      updateSegmentReadout();
      updatePathList();
      saveLocalPaths();
      queueDraw();
    }
    function bindNumericRange(rangeId, numberId, property, minimum, maximum) {
      const range = document.getElementById(rangeId);
      const number = document.getElementById(numberId);
      const applyValue = rawValue => {
        const path = activePath();
        if (!path) return;
        const parsed = Number(rawValue);
        const value = Math.max(minimum, Math.min(maximum, Number.isFinite(parsed) ? parsed : path[property]));
        path[property] = value;
        range.value = value;
        number.value = value;
        updatePathList();
        saveLocalPaths();
        queueDraw();
      };
      range.addEventListener("input", event => applyValue(event.target.value));
      number.addEventListener("change", event => applyValue(event.target.value));
      number.addEventListener("keydown", event => {
        if (event.key === "Enter") event.target.blur();
      });
    }

    function renderExport(renderPaths = paths) {
      const output = document.createElement("canvas");
      output.width = project.width;
      output.height = project.height;
      const outputContext = output.getContext("2d");
      renderPaths.filter(path => path.visible && pathIsRenderable(path)).forEach(path => renderPatternPath(outputContext, path, 1));
      return output;
    }
    function savePng() {
      if (!paths.some(pathIsRenderable)) { setStatus("Create at least one path before saving."); return; }
      const garmentName = safeFileName(project?.garment || "uniform");
      renderExport().toBlob(blob => downloadBlob(blob, `${garmentName}_trim_paths.png`), "image/png");
      setStatus(`Saved ${project.width} x ${project.height} transparent trim PNG.`);
    }
    function safeFileName(value) {
      return String(value || "trim_path").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "trim_path";
    }
    function saveSelectedPng() {
      const path = activePath();
      if (!path || !pathIsRenderable(path)) { setStatus("Select a finished trim layer first."); return; }
      renderExport([{...path, visible: true}]).toBlob(blob => downloadBlob(blob, `${safeFileName(path.name)}.png`), "image/png");
      setStatus(`Saved ${path.name} as a transparent layer PNG.`);
    }
    function canvasDataUrl(canvas) {
      return canvas.toDataURL("image/png");
    }
    async function sendToGenerator() {
      const renderable = paths.filter(path => path.visible && pathIsRenderable(path));
      if (!renderable.length) { setStatus("Create at least one visible trim layer first."); return; }
      setStatus(`Sending ${renderable.length} trim layer${renderable.length === 1 ? "" : "s"} to Generator...`);
      try {
        const layers = renderable.map(path => ({name: path.name, png: canvasDataUrl(renderExport([{...path, visible: true}]))}));
        const response = await fetch("/api/trim-path/send", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            garment: project.garment || "Shorts",
            templateName: project.templateName || "",
            layers,
          }),
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.message || `Request failed (${response.status}).`);
        setStatus(`Sent ${result.count} trim layer${result.count === 1 ? "" : "s"} to Generator.`);
      } catch (error) {
        setStatus(`Could not send trim layers: ${error.message}`);
      }
    }
    function saveJson() {
      const payload = {version: 1, garment: project.garment, templateName: project.templateName, width: project.width, height: project.height, patternName: project.patternName, paths};
      const garmentName = safeFileName(project?.garment || "uniform");
      downloadBlob(new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"}), `${garmentName}_trim_paths.json`);
    }
    function downloadBlob(blob, filename) {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }
    function loadJsonFile(file) {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const payload = JSON.parse(reader.result);
          if (!Array.isArray(payload.paths)) throw new Error("No paths were found in this file.");
          paths = deserializePaths(payload.paths);
          activePathIndex = paths.length ? 0 : -1;
          selectedPointIndex = -1;
          drawing = false;
          syncControls();
          updatePathList();
          saveLocalPaths();
          queueDraw();
          setStatus(`Loaded ${paths.length} trim path${paths.length === 1 ? "" : "s"}.`);
        } catch (error) { setStatus(`Could not load paths: ${error.message}`); }
      };
      reader.readAsText(file);
    }
    function storageKey() {
      const garment = safeFileName(project?.garment || "uniform");
      const template = safeFileName(project?.templateName || "default");
      return `nba2k-trim-paths-${project?.sessionId || "current"}-${garment}-${template}-${project?.width || 0}x${project?.height || 0}`;
    }
    function saveLocalPaths() { if (project?.width) localStorage.setItem(storageKey(), JSON.stringify(paths)); }
    function deserializePaths(rawPaths) {
      const result = [];
      rawPaths.forEach((raw, index) => {
        const base = cleanPath(raw, index);
        const hadOppositeMirror = Boolean(raw?.mirror);
        const hadXMirror = Boolean(raw?.mirrorX);
        if (!hadOppositeMirror && !hadXMirror) {
          result.push(base);
          return;
        }
        const group = createLinkGroup();
        base.linkGroup = group;
        result.push(base);
        let xCopy = null;
        if (hadXMirror) {
          xCopy = cleanPath(samePanelXMirrorPath(base), result.length);
          xCopy.name = `${base.name} X Mirror`;
          xCopy.linkGroup = group;
          result.push(xCopy);
        }
        if (hadOppositeMirror) {
          const opposite = cleanPath(oppositePanelPath(base), result.length);
          opposite.name = `${base.name} Opposite Panel`;
          opposite.linkGroup = group;
          result.push(opposite);
          if (xCopy) {
            const oppositeX = cleanPath(oppositePanelPath(xCopy), result.length);
            oppositeX.name = `${base.name} Opposite Panel X Mirror`;
            oppositeX.linkGroup = group;
            result.push(oppositeX);
          }
        }
      });
      return result;
    }
    function restoreLocalPaths() {
      try {
        const currentKey = storageKey();
        for (let index = localStorage.length - 1; index >= 0; index -= 1) {
          const key = localStorage.key(index);
          if (key?.startsWith("nba2k-trim-paths-") && key !== currentKey) {
            localStorage.removeItem(key);
          }
        }
        const stored = JSON.parse(localStorage.getItem(storageKey()) || "[]");
        if (Array.isArray(stored)) paths = deserializePaths(stored);
      } catch (_) { paths = []; }
      activePathIndex = paths.length ? 0 : -1;
      syncControls();
      updatePathList();
      saveLocalPaths();
    }

    document.addEventListener("keydown", event => {
      if (event.target.matches("input, select")) return;
      if (event.key === "Escape") { finishPath(); return; }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); undoPoint(); return; }
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      const path = activePath();
      if (!path) return;
      event.preventDefault();
      const amount = event.shiftKey ? 10 : 1;
      const deltaX = event.key === "ArrowLeft" ? -amount : event.key === "ArrowRight" ? amount : 0;
      const deltaY = event.key === "ArrowUp" ? -amount : event.key === "ArrowDown" ? amount : 0;
      if (selectedPointIndex >= 0) {
        const point = path.points[selectedPointIndex];
        point.x = Math.max(0, Math.min(project.width, point.x + deltaX));
        point.y = Math.max(0, Math.min(project.height, point.y + deltaY));
      } else {
        moveSelectedLayers(deltaX, deltaY);
      }
      updateSegmentReadout();
      saveLocalPaths();
      queueDraw();
    });

    document.getElementById("newPath").onclick = newPath;
    document.getElementById("finishPath").onclick = finishPath;
    document.getElementById("undoPoint").onclick = undoPoint;
    document.getElementById("removePath").onclick = removePath;
    document.getElementById("duplicatePath").onclick = duplicatePath;
    document.getElementById("layerDown").onclick = () => moveLayer(-1);
    document.getElementById("layerUp").onclick = () => moveLayer(1);
    document.getElementById("createOppositeCopy").onclick = () => createDerivedPath(oppositePanelPath, "Opposite Panel");
    document.getElementById("createXMirror").onclick = () => createDerivedPath(samePanelXMirrorPath, "X Mirror");
    document.getElementById("unlinkPath").onclick = unlinkSelectedPath;
    document.getElementById("fit").onclick = fitView;
    document.getElementById("zoomOut").onclick = () => { viewScale = Math.max(minScale * .5, viewScale / 1.25); queueDraw(); };
    document.getElementById("zoomIn").onclick = () => { viewScale = Math.min(12, viewScale * 1.25); queueDraw(); };
    document.getElementById("reload").onclick = loadProject;
    document.getElementById("sendToGenerator").onclick = sendToGenerator;
    document.getElementById("savePng").onclick = savePng;
    document.getElementById("saveSelectedPng").onclick = saveSelectedPng;
    document.getElementById("saveJson").onclick = saveJson;
    document.getElementById("loadJson").onclick = () => document.getElementById("loadJsonInput").click();
    document.getElementById("loadJsonInput").onchange = event => event.target.files[0] && loadJsonFile(event.target.files[0]);
    document.getElementById("curveMode").addEventListener("change", changePathShape);
    bindNumericRange("trimWidth", "trimWidthNumber", "width", 2, 300);
    bindNumericRange("patternScale", "patternScaleNumber", "patternScale", 25, 400);
    bindNumericRange("patternOffset", "patternOffsetNumber", "patternOffset", -1024, 1024);
    bindPathControl("pathVisible", "visible", Boolean);
    document.getElementById("moveLinked").onchange = syncControls;
    document.getElementById("angleSnap").onchange = () => {
      livePoint = null;
      updateSegmentReadout();
      queueDraw();
    };
    document.getElementById("templateOpacity").oninput = () => { updateControlLabels(); queueDraw(); };
    document.getElementById("showUvOverlay").onchange = queueDraw;
    document.getElementById("uvOpacity").oninput = () => { updateControlLabels(); queueDraw(); };
    document.getElementById("showPoints").onchange = queueDraw;
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
    updateControlLabels();
    syncControls();
    updatePathList();
    loadProject();
  </script>
</body>
</html>
"""
