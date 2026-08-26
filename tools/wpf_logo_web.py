from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba2k_jersey_modder.logo_web_session import LogoWebSession


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NBA 2K Logo Creator</title>
  <style>
    :root { color-scheme: dark; font-family: "Segoe UI", Arial, sans-serif; --bg:#11151b; --panel:#1b212a; --line:#343d4b; --muted:#9da9ba; --accent:#f0b429; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:#eef2f7; overflow:hidden; }
    header { height:58px; display:flex; align-items:center; gap:8px; padding:0 16px; background:#202731; border-bottom:1px solid var(--line); }
    header strong { font-size:17px; margin-right:8px; }
    button, select, input { font:inherit; }
    button { border:1px solid transparent; border-radius:5px; padding:8px 12px; background:#303947; color:#eef2f7; cursor:pointer; font-weight:600; }
    button:hover { background:#3a4555; }
    button.primary { background:var(--accent); color:#171a20; }
    button.done { background:#2f7655; border-color:#4b9875; color:#fff; }
    button.done:hover { background:#398864; }
    button.danger { color:#ffbdc5; border-color:#633742; }
    .spacer { flex:1; }
    .hint { color:var(--muted); font-size:12px; }
    #layout { height:calc(100vh - 58px); display:grid; grid-template-columns:minmax(0,1fr) 370px; }
    #stage { position:relative; min-width:0; min-height:0; background:#0d1015; }
    canvas { width:100%; height:100%; display:block; cursor:crosshair; }
    aside { background:var(--panel); border-left:1px solid var(--line); overflow:auto; padding:14px; }
    h2 { font-size:14px; margin:0 0 9px; }
    .section { border-bottom:1px solid var(--line); padding-bottom:14px; margin-bottom:14px; }
    .row { display:flex; gap:8px; align-items:center; margin:8px 0; }
    .row > * { flex:1; }
    label { color:#cbd3df; font-size:12px; }
    select, input[type=number] { width:100%; background:#11161d; color:#eef2f7; border:1px solid #465163; border-radius:5px; padding:7px; }
    input[type=range] { width:100%; accent-color:var(--accent); }
    .modes button.active { background:#53677f; border-color:#7f94ad; }
    #staged { display:flex; flex-direction:column; gap:7px; max-height:230px; overflow:auto; }
    .stage-item { width:100%; display:grid; grid-template-columns:48px minmax(0,1fr); gap:9px; text-align:left; align-items:center; padding:6px; border:1px solid var(--line); background:#252d38; }
    .stage-item.active { border-color:var(--accent); background:#30394a; }
    .stage-item img { width:48px; height:48px; object-fit:contain; background:repeating-conic-gradient(#d8d8d8 0 25%,#fff 0 50%) 0/16px 16px; }
    .stage-item b, .stage-item span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .stage-item span { color:var(--muted); font-size:11px; margin-top:3px; }
    #preview { height:165px; width:100%; object-fit:contain; background:repeating-conic-gradient(#d8d8d8 0 25%,#fff 0 50%) 0/20px 20px; border:1px solid var(--line); }
    .checks { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:10px 0; }
    .checks label { display:flex; gap:7px; align-items:center; }
    .status { color:#dce3ee; font-size:12px; min-height:34px; line-height:1.4; }
    .empty { color:var(--muted); font-size:12px; padding:14px 2px; }
    @media (max-width:900px) { #layout { grid-template-columns:minmax(0,1fr) 310px; } .hint { display:none; } }
  </style>
</head>
<body>
  <header>
    <strong>Logo Creator</strong>
    <div class="modes"><button id="lasso" class="active">Lasso</button><button id="box">Box</button></div>
    <button id="zoomOut">Zoom -</button><button id="fit">Fit</button><button id="zoomIn">Zoom +</button>
    <button id="clearSelection">Clear Selection</button>
    <span class="spacer"></span><span class="hint">Wheel zooms. Middle-drag or Shift-drag pans.</span>
    <button id="returnToApp" class="done">Done - Return to App</button>
  </header>
  <div id="layout">
    <main id="stage"><canvas id="canvas"></canvas></main>
    <aside>
      <section class="section">
        <h2>New Logo</h2>
        <label>Logo type</label><select id="newType"></select>
        <div class="row"><button id="stageSelection" class="primary">Stage Selection</button></div>
        <div id="status" class="status">Loading reference...</div>
      </section>
      <section class="section">
        <div class="row"><h2>Staged Logos</h2><button id="clearStaged" class="danger">Clear All</button></div>
        <div id="staged"><div class="empty">No logos staged yet.</div></div>
        <div class="row"><button id="openEditor">Open Staged Logo Editor</button></div>
      </section>
      <section id="editor" hidden>
        <h2>Edit Selected Logo</h2>
        <img id="preview" alt="Selected logo preview">
        <div style="margin-top:10px"><label>Logo type</label><select id="editType"></select></div>
        <div class="checks">
          <label><input id="auto" type="checkbox"> Auto background</label>
          <label><input id="outside" type="checkbox" checked> Outside only</label>
          <label><input id="white" type="checkbox"> Remove white</label>
          <label><input id="black" type="checkbox"> Remove black</label>
        </div>
        <label>Tolerance: <span id="toleranceValue">32</span></label>
        <input id="tolerance" type="range" min="0" max="255" value="32">
        <div style="margin-top:9px"><label>Upscale</label><select id="scale"><option value="1">1x (original pixels)</option><option value="2">2x</option><option value="4">4x</option></select></div>
        <div class="row"><button id="apply" class="primary">Apply Changes</button><button id="remove" class="danger">Remove</button></div>
      </section>
    </aside>
  </div>
  <script>
    const $ = id => document.getElementById(id);
    const canvas=$('canvas'), ctx=canvas.getContext('2d'), stage=$('stage'), image=new Image();
    let project=null, selected=null, mode='lasso', points=[], drawing=false, panning=false, panStart=null, scale=1, minScale=1, panX=0, panY=0, dirty=false;
    async function api(path, payload) {
      const options=payload===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
      const response=await fetch(path,options); const data=await response.json();
      if(!response.ok) throw new Error(data.error||`Request failed: ${response.status}`); return data;
    }
    function setStatus(text){$('status').textContent=text;}
    async function loadProject(initial=false){
      project=await api('/api/project'); populateTypes(); selected=project.items.find(x=>x.id===project.selectedId)||null; renderList(); renderEditor();
      if(initial){image.onload=()=>{fitImage();setStatus('Draw around a logo, choose its type, then stage it.');};image.onerror=()=>setStatus('The reference image could not be displayed.');image.src=`${project.imageUrl}?v=${project.sourceVersion}`;}
    }
    function populateTypes(){
      for(const select of [$('newType'),$('editType')]){const current=select.value;select.innerHTML='';for(const item of project.logoTypes){const option=document.createElement('option');option.value=item.target;option.textContent=item.label;select.append(option);}if(current)select.value=current;}
    }
    function renderList(){
      const host=$('staged');host.innerHTML='';if(!project.items.length){host.innerHTML='<div class="empty">No logos staged yet.</div>';return;}
      project.items.forEach((item,index)=>{const button=document.createElement('button');button.className='stage-item'+(item.id===project.selectedId?' active':'');button.innerHTML=`<img src="${item.previewUrl}?v=${Date.now()}" alt=""><div><b>${index+1}. ${item.typeLabel}</b><span>${item.fileName}</span></div>`;button.onclick=async()=>{project=await api('/api/select',{id:item.id});selected=project.items.find(x=>x.id===project.selectedId);renderList();renderEditor();};host.append(button);});
    }
    function renderEditor(){$('editor').hidden=true;}
    function resize(){const ratio=devicePixelRatio||1;canvas.width=Math.max(1,stage.clientWidth*ratio);canvas.height=Math.max(1,stage.clientHeight*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);draw();}
    function fitImage(){if(!project)return;minScale=Math.max(.03,Math.min(1,(stage.clientWidth-36)/project.width,(stage.clientHeight-36)/project.height));scale=minScale;panX=(stage.clientWidth-project.width*scale)/2;panY=(stage.clientHeight-project.height*scale)/2;draw();}
    function schedule(){if(dirty)return;dirty=true;requestAnimationFrame(()=>{dirty=false;draw();});}
    function draw(){ctx.clearRect(0,0,stage.clientWidth,stage.clientHeight);ctx.fillStyle='#0d1015';ctx.fillRect(0,0,stage.clientWidth,stage.clientHeight);if(!image.complete||!project)return;ctx.imageSmoothingEnabled=true;ctx.drawImage(image,panX,panY,project.width*scale,project.height*scale);if(!points.length)return;ctx.save();ctx.beginPath();points.forEach((p,i)=>{const x=panX+p.x*scale,y=panY+p.y*scale;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});if(!drawing&&points.length>2)ctx.closePath();ctx.fillStyle='rgba(240,180,41,.16)';ctx.strokeStyle='#ffd05a';ctx.lineWidth=2;ctx.fill();ctx.stroke();ctx.restore();}
    function canvasPoint(e){const r=canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
    function imagePoint(e){const p=canvasPoint(e);return{x:Math.max(0,Math.min(project.width-1,Math.round((p.x-panX)/scale))),y:Math.max(0,Math.min(project.height-1,Math.round((p.y-panY)/scale)))};}
    function zoom(factor,center){const bx=(center.x-panX)/scale,by=(center.y-panY)/scale;scale=Math.max(minScale*.5,Math.min(12,scale*factor));panX=center.x-bx*scale;panY=center.y-by*scale;schedule();}
    canvas.onpointerdown=e=>{if(!project)return;canvas.setPointerCapture(e.pointerId);if(e.shiftKey||e.button===1||e.button===2){panning=true;const p=canvasPoint(e);panStart={x:p.x,y:p.y,panX,panY};return;}drawing=true;points=[imagePoint(e)];setStatus(mode==='box'?'Drag to size the box.':'Draw around the logo.');schedule();};
    canvas.onpointermove=e=>{if(panning&&panStart){const p=canvasPoint(e);panX=panStart.panX+p.x-panStart.x;panY=panStart.panY+p.y-panStart.y;schedule();return;}if(!drawing)return;const p=imagePoint(e);if(mode==='box'){const a=points[0];points=[a,{x:p.x,y:a.y},p,{x:a.x,y:p.y}];}else{const last=points.at(-1);if(!last||Math.abs(p.x-last.x)+Math.abs(p.y-last.y)>=2)points.push(p);}schedule();};
    canvas.onpointerup=()=>{if(panning){panning=false;panStart=null;return;}if(!drawing)return;drawing=false;if(points.length<3){points=[];setStatus('Draw a larger selection.');}else setStatus('Selection ready. Choose a logo type and stage it.');schedule();};
    canvas.onwheel=e=>{e.preventDefault();zoom(e.deltaY<0?1.16:1/1.16,canvasPoint(e));};canvas.oncontextmenu=e=>e.preventDefault();
    async function stageSelection(){if(points.length<3){setStatus('Draw around a logo first.');return;}const button=$('stageSelection');button.disabled=true;setStatus('Creating staged logo...');try{project=await api('/api/stage',{points,target:$('newType').value});selected=project.items.find(x=>x.id===project.selectedId);points=[];renderList();renderEditor();draw();setStatus(`Staged ${selected.typeLabel}. Select another logo from the same reference.`);}catch(e){setStatus(e.message);}finally{button.disabled=false;}}
    async function apply(){if(!selected)return;const button=$('apply');button.disabled=true;setStatus('Updating selected logo...');try{project=await api('/api/update',{id:selected.id,target:$('editType').value,auto:$('auto').checked,removeWhite:$('white').checked,removeBlack:$('black').checked,outsideOnly:$('outside').checked,tolerance:+$('tolerance').value,scale:+$('scale').value});selected=project.items.find(x=>x.id===project.selectedId);renderList();renderEditor();setStatus('Selected logo updated from the original reference.');}catch(e){setStatus(e.message);}finally{button.disabled=false;}}
    $('stageSelection').onclick=stageSelection;$('apply').onclick=apply;$('remove').onclick=async()=>{if(!selected)return;project=await api('/api/remove',{id:selected.id});selected=project.items.find(x=>x.id===project.selectedId)||null;renderList();renderEditor();setStatus('Removed staged logo.');};$('clearStaged').onclick=async()=>{if(!project.items.length||!confirm('Remove every staged logo?'))return;project=await api('/api/clear',{});selected=null;renderList();renderEditor();setStatus('Cleared staged logos.');};
    $('clearSelection').onclick=()=>{points=[];draw();setStatus('Selection cleared.');};$('fit').onclick=fitImage;$('zoomIn').onclick=()=>zoom(1.25,{x:stage.clientWidth/2,y:stage.clientHeight/2});$('zoomOut').onclick=()=>zoom(1/1.25,{x:stage.clientWidth/2,y:stage.clientHeight/2});
    $('openEditor').onclick=()=>location.href='/edit';
    $('returnToApp').onclick=async()=>{const button=$('returnToApp');button.disabled=true;try{const result=await api('/api/return',{});setStatus(`${result.items} staged logo${result.items===1?'':'s'} saved. Returning to the app...`);button.textContent='App Ready - Close This Tab';setTimeout(()=>window.close(),350);}catch(e){button.disabled=false;setStatus(e.message);}};
    $('lasso').onclick=()=>{mode='lasso';$('lasso').classList.add('active');$('box').classList.remove('active');points=[];draw();};$('box').onclick=()=>{mode='box';$('box').classList.add('active');$('lasso').classList.remove('active');points=[];draw();};$('tolerance').oninput=()=>$('toleranceValue').textContent=$('tolerance').value;
    window.onresize=resize;resize();loadProject(true).catch(e=>setStatus(e.message));
  </script>
</body></html>"""


EDITOR_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NBA 2K Staged Logo Editor</title>
  <style>
    :root { color-scheme:dark; font-family:"Segoe UI",Arial,sans-serif; --bg:#11151b; --panel:#1b212a; --line:#343d4b; --muted:#9da9ba; --accent:#f0b429; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:#eef2f7; overflow:hidden; }
    header { height:58px; display:flex; align-items:center; gap:9px; padding:0 16px; background:#202731; border-bottom:1px solid var(--line); }
    header strong { font-size:17px; }
    .spacer { flex:1; }
    button,select,input { font:inherit; }
    button { border:1px solid transparent; border-radius:5px; padding:8px 12px; background:#303947; color:#eef2f7; cursor:pointer; font-weight:600; }
    button:hover { background:#3a4555; }
    button.primary { background:var(--accent); color:#171a20; }
    button.done { background:#2f7655; border-color:#4b9875; color:#fff; }
    button.danger { color:#ffbdc5; border-color:#633742; }
    #layout { height:calc(100vh - 58px); display:grid; grid-template-columns:minmax(0,1fr) 390px; }
    #previewStage { min-width:0; min-height:0; padding:28px; display:grid; place-items:center; background:repeating-conic-gradient(#d5d8dc 0 25%,#f5f6f7 0 50%) 0/28px 28px; }
    #preview { max-width:100%; max-height:100%; object-fit:contain; filter:drop-shadow(0 10px 22px rgba(0,0,0,.22)); }
    #emptyPreview { color:#4c5664; font-size:16px; font-weight:600; }
    aside { background:var(--panel); border-left:1px solid var(--line); overflow:auto; padding:14px; }
    h2 { font-size:14px; margin:0 0 9px; }
    .section { border-bottom:1px solid var(--line); padding-bottom:14px; margin-bottom:14px; }
    .row { display:flex; gap:8px; align-items:center; margin:8px 0; }
    .row > * { flex:1; }
    label { display:block; color:#cbd3df; font-size:12px; margin-bottom:4px; }
    select { width:100%; background:#11161d; color:#eef2f7; border:1px solid #465163; border-radius:5px; padding:7px; }
    input[type=range] { width:100%; accent-color:var(--accent); }
    .checks { display:grid; grid-template-columns:1fr 1fr; gap:9px; margin:11px 0; }
    .checks label { display:flex; gap:7px; align-items:center; }
    #staged { display:flex; flex-direction:column; gap:7px; max-height:260px; overflow:auto; }
    .stage-item { width:100%; display:grid; grid-template-columns:52px minmax(0,1fr); gap:9px; text-align:left; align-items:center; padding:6px; border:1px solid var(--line); background:#252d38; }
    .stage-item.active { border-color:var(--accent); background:#30394a; }
    .stage-item img { width:52px; height:52px; object-fit:contain; background:repeating-conic-gradient(#d8d8d8 0 25%,#fff 0 50%) 0/14px 14px; }
    .stage-item b,.stage-item span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .stage-item span { color:var(--muted); font-size:11px; margin-top:3px; }
    .status { min-height:34px; color:#dce3ee; font-size:12px; line-height:1.4; }
    .empty { color:var(--muted); font-size:12px; padding:12px 2px; }
  </style>
</head>
<body>
  <header>
    <strong>Staged Logo Editor</strong>
    <button id="selector">Back to Logo Selector</button>
    <span class="spacer"></span>
    <button id="returnToApp" class="done">Done - Return to App</button>
  </header>
  <div id="layout">
    <main id="previewStage"><div id="emptyPreview">Select a staged logo to edit.</div><img id="preview" alt="Selected staged logo" hidden></main>
    <aside>
      <section class="section">
        <div class="row"><h2>Staged Logos</h2><button id="clear" class="danger">Clear All</button></div>
        <div id="staged"><div class="empty">No logos have been staged.</div></div>
      </section>
      <section id="controls" hidden>
        <h2>Selected Logo</h2>
        <label>Logo type</label><select id="type"></select>
        <div class="checks">
          <label><input id="auto" type="checkbox"> Auto background</label>
          <label><input id="outside" type="checkbox" checked> Outside only</label>
          <label><input id="white" type="checkbox"> Remove white</label>
          <label><input id="black" type="checkbox"> Remove black</label>
        </div>
        <label>Tolerance: <span id="toleranceValue">32</span></label>
        <input id="tolerance" type="range" min="0" max="255" value="32">
        <div style="margin-top:10px"><label>Upscale</label><select id="scale"><option value="1">1x (original pixels)</option><option value="2">2x</option><option value="4">4x</option></select></div>
        <div class="row"><button id="apply" class="primary">Apply Changes</button><button id="remove" class="danger">Remove Logo</button></div>
      </section>
      <div id="status" class="status">Loading staged logos...</div>
    </aside>
  </div>
  <script>
    const $=id=>document.getElementById(id);let project=null,selected=null;
    async function api(path,payload){const options=payload===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};const response=await fetch(path,options);const data=await response.json();if(!response.ok)throw new Error(data.error||`Request failed: ${response.status}`);return data;}
    function status(text){$('status').textContent=text;}
    function fillTypes(){const current=$('type').value;$('type').innerHTML='';project.logoTypes.forEach(item=>{const option=document.createElement('option');option.value=item.target;option.textContent=item.label;$('type').append(option);});if(current)$('type').value=current;}
    async function load(){project=await api('/api/project');selected=project.items.find(item=>item.id===project.selectedId)||project.items[0]||null;if(selected&&selected.id!==project.selectedId)project=await api('/api/select',{id:selected.id});fillTypes();render();status(project.items.length?`${project.items.length} staged logo${project.items.length===1?'':'s'} ready to edit.`:'Return to the selector to stage a logo.');}
    function render(){renderList();const has=!!selected;$('controls').hidden=!has;$('preview').hidden=!has;$('emptyPreview').hidden=has;if(!has)return;$('preview').src=`${selected.previewUrl}?v=${Date.now()}`;$('type').value=selected.target;$('auto').checked=selected.auto;$('white').checked=selected.removeWhite;$('black').checked=selected.removeBlack;$('outside').checked=selected.outsideOnly;$('tolerance').value=selected.tolerance;$('toleranceValue').textContent=selected.tolerance;$('scale').value=selected.scale;}
    function renderList(){const host=$('staged');host.innerHTML='';if(!project.items.length){host.innerHTML='<div class="empty">No logos have been staged.</div>';return;}project.items.forEach((item,index)=>{const button=document.createElement('button');button.className='stage-item'+(selected?.id===item.id?' active':'');button.innerHTML=`<img src="${item.previewUrl}?v=${Date.now()}" alt=""><div><b>${index+1}. ${item.typeLabel}</b><span>${item.fileName}</span></div>`;button.onclick=async()=>{project=await api('/api/select',{id:item.id});selected=project.items.find(value=>value.id===item.id);render();status(`Editing ${selected.typeLabel}.`);};host.append(button);});}
    $('apply').onclick=async()=>{if(!selected)return;const button=$('apply');button.disabled=true;status('Regenerating from the original reference...');try{project=await api('/api/update',{id:selected.id,target:$('type').value,auto:$('auto').checked,removeWhite:$('white').checked,removeBlack:$('black').checked,outsideOnly:$('outside').checked,tolerance:+$('tolerance').value,scale:+$('scale').value});selected=project.items.find(item=>item.id===project.selectedId);render();status('Logo changes applied from the original pixels.');}catch(e){status(e.message);}finally{button.disabled=false;}};
    $('remove').onclick=async()=>{if(!selected)return;project=await api('/api/remove',{id:selected.id});selected=project.items.find(item=>item.id===project.selectedId)||null;render();status('Removed staged logo.');};
    $('clear').onclick=async()=>{if(!project.items.length||!confirm('Remove every staged logo?'))return;project=await api('/api/clear',{});selected=null;render();status('Cleared staged logos.');};
    $('selector').onclick=()=>location.href='/';$('tolerance').oninput=()=>$('toleranceValue').textContent=$('tolerance').value;
    $('returnToApp').onclick=async()=>{const button=$('returnToApp');button.disabled=true;try{const result=await api('/api/return',{});status(`${result.items} staged logo${result.items===1?'':'s'} saved. Returning to the app...`);button.textContent='App Ready - Close This Tab';setTimeout(()=>window.close(),350);}catch(e){button.disabled=false;status(e.message);}};
    load().catch(e=>status(e.message));
  </script>
</body></html>"""


def handler_class(session: LogoWebSession):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *args):
            return

        def do_GET(self):  # noqa: N802
            try:
                path = urlparse(self.path).path
                if path in ("/", "/logo"):
                    self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/edit":
                    self._send(EDITOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/api/project":
                    self._json(session.project())
                elif path == "/api/reference":
                    self._send(*session.reference_bytes())
                elif path.startswith("/api/preview/"):
                    self._send(*session.preview_bytes(unquote(path.rsplit("/", 1)[1])))
                else:
                    self.send_error(404)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)

        def do_POST(self):  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                path = urlparse(self.path).path
                action = {
                    "/api/stage": lambda: session.stage(payload),
                    "/api/import": lambda: session.import_image(payload),
                    "/api/update": lambda: session.update(payload),
                    "/api/select": lambda: session.select(payload),
                    "/api/remove": lambda: session.remove(payload),
                    "/api/clear": session.clear,
                    "/api/return": session.request_return,
                }.get(path)
                if action is None:
                    self.send_error(404)
                    return
                self._json(action())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 400)

        def _json(self, value: dict, status: int = 200):
            self._send(json.dumps(value).encode("utf-8"), "application/json", status)

        def _send(self, data: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store" if content_type == "application/json" else "private, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()
    session = LogoWebSession(Path(args.reference), Path(args.state))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class(session))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(json.dumps({"url": url}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
