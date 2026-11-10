"""The page shown in the Line Art Studio tab."""
from .oneline_ui import CSS

_PAGE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
/*ONELINE_CSS*/
[hidden] { display: none !important; }
.app { height: 100vh; display: grid; gap: var(--ol-pad); padding: var(--ol-pad);
  grid-template-columns: 372px minmax(0, 1fr) 300px; grid-template-rows: minmax(0, 1fr) auto;
  grid-template-areas: "controls stage status" "controls stage actions"; }
.controls { grid-area: controls; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; min-height: 0; }
.stagewrap { grid-area: stage; display: flex; flex-direction: column; gap: 12px; min-height: 0; min-width: 0; }
.status { grid-area: status; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; min-height: 0; }
.actions { grid-area: actions; display: grid; gap: var(--ol-gap); }
.stage { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: var(--ol-pad); flex: 1; min-height: 0; }
.source { overflow-y: auto; }
.crop-frame { width: 100%; aspect-ratio: 1; display: flex; align-items: center; justify-content: center; border-radius: var(--ol-radius); background: var(--ol-surface-2); overflow: hidden; }
#crop { width: 100%; display: block; cursor: move; touch-action: none; }
.result { padding: 12px; display: flex; flex-direction: column; min-height: 0; min-width: 0; }
.result header { display: flex; justify-content: space-between; gap: 12px; }
.result .ol-preview { flex: 1; padding: 12px; }
.ol-preview.empty, .ol-preview.shaped { background: var(--ol-surface-2); }
#c { max-width: 100%; max-height: 100%; aspect-ratio: 1; display: block; }
#file { position: absolute; width: 1px; height: 1px; opacity: 0; }
#fileName { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#path { word-break: break-all; }
#styleName { font-weight: 600; }
#modes:not([hidden]) + #styleName { display: none; }
#modes:not([hidden]) ~ #styleNote { margin-top: 8px; }
@media (max-width: 1240px) {
  .app { grid-template-columns: 340px minmax(0, 1fr) 260px; grid-template-rows: minmax(0, 1fr) auto;
    grid-template-areas: "controls stage stage" "controls status actions"; }
  .status { flex-direction: row; max-height: 170px; }
  .status > * { flex: 1; min-width: 0; overflow-y: auto; }
  .stage { grid-template-columns: 220px minmax(0, 1fr); }
  .actions { align-content: end; }
  #checks { display: flex; flex-direction: column; }
  .ol-check.todo { order: -1; }  /* this card is short here: what still needs doing comes first */
}
@media (max-width: 760px) {
  .app { display: block; height: auto; min-height: 100%; }
  .controls, .status, .stagewrap { overflow: visible; margin-bottom: 12px; }
  .stage { grid-template-columns: minmax(0, 1fr); }
  .status { flex-direction: column; max-height: none; }
  #c { width: 100%; }
  .actions { position: sticky; bottom: 0; background: var(--orca-bg); padding: 8px 0; }
}
</style>
</head>
<body>
<form class="app" id="f" onsubmit="return false">
  <div class="controls">
    <h1>Line Art Studio</h1>
    <div class="ol-card">
      <h2>Style</h2>
      <div class="ol-segments" id="modes" hidden></div>
      <div id="styleName"></div>
      <div class="ol-muted" id="styleNote"></div>
    </div>
    <div class="ol-card">
      <h2>Filaments</h2>
      <label class="ol-field">Base <span class="ol-input ol-select"><i id="baseSwatch"></i><select id="base_filament"></select></span></label>
      <label class="ol-field">Line <span class="ol-input ol-select"><i id="artSwatch"></i><select id="art_filament"></select></span></label>
      <label class="ol-field" id="pauseRow">Color change <span class="ol-input ol-select" style="width:150px"><select id="color_change" style="padding-left:8px"><option value="pause">Pause first</option><option value="none">None</option></select></span></label>
    </div>
    <div class="ol-card">
      <h2>Frame, size and layers</h2>
      <div class="ol-field">Frame <span id="shapeName"></span></div>
      <div class="ol-shapes" id="shapes" role="group" aria-label="Frame shape"></div>
      <input id="shape" type="hidden">
      <label class="ol-field"><span id="widthLabel">Art size</span> <span class="ol-input unit"><input id="width" type="number" step="1"><small>mm</small></span></label>
      <label class="ol-field" id="heightRow" hidden>Height <span class="ol-input unit"><input id="height" type="number" step="1"><small>mm</small></span></label>
      <div class="ol-muted" style="margin-bottom:8px">Faces need about 150 mm. Below 100 mm only bold shapes read well.</div>
      <label class="ol-field">Layer height <span class="ol-input unit"><input id="layer_height" type="number" step="0.01" min="0.04"><small>mm</small></span></label>
      <label class="ol-field">Nozzle <span class="ol-input unit"><input id="nozzle" type="number" step="0.05" min="0.1" max="1.2"><small>mm</small></span></label>
      <label class="ol-field">Base layers <span class="ol-input"><input id="base_layers" type="number" step="1" min="1"></span></label>
      <label class="ol-field">Line layers <span class="ol-input"><input id="art_layers" type="number" step="1" min="1" max="10"></span></label>
      <div class="ol-stack" id="stackBar" hidden><i id="stackBase"></i><i id="stackArt"></i></div>
      <div class="ol-muted" id="stack"></div>
    </div>
    <details class="ol-card">
      <summary>Line width, detail and speed</summary>
      <label class="ol-field">Line width <span class="ol-input unit"><input id="line_width" type="number" step="0.01" min="0.05"><small>mm</small></span></label>
      <div class="ol-field ol-slider-row"><label for="spacing">Detail spacing</label><input class="ol-slider" id="spacing_slider" type="range" aria-label="Detail spacing" hidden><span class="ol-input unit"><input id="spacing" type="number"><small>x</small></span></div>
      <label class="ol-field">Print speed <span class="ol-input unit"><input id="speed" type="number" step="1" min="1"><small>mm/s</small></span></label>
    </details>
    <details class="ol-card" open>
      <summary>Tone: automatic, invert, contrast, gamma</summary>
      <label class="ol-field">Light line on a dark base <input id="invert" type="checkbox"></label>
      <label class="ol-field">Automatic tone <input id="auto_tone" type="checkbox"></label>
      <div class="ol-muted" style="margin-bottom:8px">Stretches the picture across its light-to-dark range and sharpens it.</div>
      <div class="ol-field ol-slider-row"><label for="contrast">Contrast</label><input class="ol-slider" id="contrast_slider" type="range" aria-label="Contrast" hidden><span class="ol-input"><input id="contrast" type="number"></span></div>
      <div class="ol-field ol-slider-row"><label for="gamma">Gamma</label><input class="ol-slider" id="gamma_slider" type="range" aria-label="Gamma" hidden><span class="ol-input"><input id="gamma" type="number"></span></div>
    </details>
  </div>

  <div class="stagewrap">
    <div class="stage">
      <div class="ol-card source">
        <h2>Picture</h2>
        <div class="crop-frame"><canvas id="crop" width="540" height="540" title="Drag to move, scroll to zoom"></canvas></div>
        <div class="ol-muted" style="margin:8px 0 12px">Drag to move, scroll to zoom</div>
        <div class="ol-muted" id="fileName" style="margin-bottom:8px">No picture yet</div>
        <label class="ol-field">Zoom <span class="ol-input unit"><input id="zoom" type="number" step="0.1" min="1" max="8" value="1"><small>x</small></span></label>
        <label class="ol-field">Left / right <span class="ol-input unit"><input id="panx" type="number" step="5" min="-100" max="100" value="0"><small>%</small></span></label>
        <label class="ol-field">Up / down <span class="ol-input unit"><input id="pany" type="number" step="5" min="-100" max="100" value="0"><small>%</small></span></label>
        <label class="ol-button quiet" style="margin-top:12px;cursor:pointer" id="fileLabel">Choose a picture<input id="file" type="file" accept="image/*"></label>
      </div>
      <div class="ol-card result">
        <header><h2>The printed line</h2><span class="ol-muted" id="lineState"></span></header>
        <div class="ol-preview empty" id="previewBox"><span class="ol-muted" id="emptyNote">Choose a picture to see its line.</span><canvas id="c" width="360" height="360" hidden></canvas></div>
      </div>
    </div>
    <div class="ol-metrics">
      <div class="ol-metric"><span class="ol-muted">Line length</span><b id="mLength">-</b></div>
      <div class="ol-metric"><span class="ol-muted">Line time</span><b id="mTime">-</b></div>
      <div class="ol-metric"><span class="ol-muted">Points</span><b id="mPoints">-</b></div>
      <div class="ol-metric"><span class="ol-muted">Peak flow</span><b id="mFlow">-</b></div>
    </div>
    <div class="ol-muted" id="speedNote"></div>
  </div>

  <div class="status">
    <div class="ol-card">
      <h2>Before you slice</h2>
      <div id="checks"></div>
    </div>
    <div class="ol-card">
      <h2>Last slice</h2>
      <div class="ol-muted" id="lastSlice">No slice yet. Slice the base, then check here.</div>
    </div>
  </div>

  <div class="actions">
    <div class="ol-muted" id="msg"></div>
    <div class="ol-muted" id="path"></div>
    <button type="button" class="ol-button" id="save">Save job and add base to plate</button>
    <button type="button" class="ol-button quiet" id="refresh">Check last slice</button>
  </div>
</form>
<script>
var fields = ["base_filament","art_filament","color_change","shape","width","height","nozzle","layer_height","base_layers","art_layers","line_width","spacing","speed","invert","auto_tone","contrast","gamma"];
var SLIDER_FIELDS = ["spacing", "contrast", "gamma"];
var SLIDER_STEP = 0.05;  // fine enough to land on every default the core uses; a range input's grid starts at its low limit
var PICTURE_LONGEST_SIDE = 600;  // pixels the core receives along the picture's longer side
var CROP_CANVAS_LONGEST_SIDE = 540;
var CROP_VEIL_OPACITY = 0.72;  // dark enough to read as "not printed", light enough to still aim the crop by
var CROP_OUTLINE_WIDTH = 4;
var PREVIEW_OUTLINE_SHARE = 0.005;  // of the canvas side, so the edge keeps its weight when the core changes the preview size
var CORNER_TOLERANCE = 0.01;  // a vertex this close to a box corner is on it; the core's margin is well inside this
var SUB_PIXEL = 0.5;  // less free picture than this is rounding, not room to pan
var SVG_NAMESPACE = "http://www.w3.org/2000/svg";
var ICON_BOX = 28, ICON_INSET = 3;
var TWO_SIDED_ICON_ASPECT = 1.5;  // a two-sided shape has no aspect of its own, and at 1:1 a rectangle would look like the square
var sliders = {};  // field id to its range input, only once the core has given that field's limits
var shapes = [], shape = null, minSide = 0;
var sides = { width: 0, height: 0 };  // the last committed sizes: a half-typed number must not reach the core or the crop
var image = null, timer = null, ready = false, wantSave = false, mode = "tsp", modes = [];
var source = null, encodeTimer = null, filaments = [], filamentKey = "";
var printer = null, selected = null, onPlate = null, savedImage = null, savedParams = "";
var send = function (m) { window.orca.postMessage(m); };
var el = function (i) { return document.getElementById(i); };

function msg(t, err) { var m = el("msg"); m.textContent = t || ""; m.className = err ? "ol-error" : "ol-muted"; }

function fieldValue(f) {
  var e = el(f);
  if (f === "height") return artHeight();
  if (f === "width") return sides.width;
  if (sliders[f]) return parseFloat(sliders[f].value);  // a half-typed number can be out of range; its slider never is
  return e.type === "checkbox" ? e.checked : (e.tagName === "SELECT" || e.type === "hidden" ? e.value : parseFloat(e.value));
}

function params() {
  var p = {};
  fields.forEach(function (f) { p[f] = fieldValue(f); });
  p.mode = mode;
  p.margin = 0.4;
  return p;
}

function filamentAt(id) { return filaments[parseInt(el(id).value, 10) - 1]; }

function fillFilaments(list) {
  var key = JSON.stringify(list);
  if (key === filamentKey) return;
  filamentKey = key;
  ["base_filament", "art_filament"].forEach(function (id) {
    var e = el(id), keep = e.value;
    e.innerHTML = "";
    list.forEach(function (f) {
      var o = document.createElement("option");
      o.value = f.slot; o.textContent = f.slot + ": " + f.name;
      e.appendChild(o);
    });
    if (keep && parseInt(keep, 10) <= list.length) e.value = keep;
  });
  filaments = list;
  showFilaments();
}

function showFilaments() {
  el("pauseRow").style.display = el("base_filament").value === el("art_filament").value ? "" : "none";
  var base = filamentAt("base_filament"), art = filamentAt("art_filament");
  if (base) { el("baseSwatch").style.background = base.color; el("stackBase").style.background = base.color; }
  if (art) { el("artSwatch").style.background = art.color; el("stackArt").style.background = art.color; }
}

function luminance(hex) {
  var n = parseInt(hex.slice(1), 16);
  return 0.299 * (n >> 16 & 255) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255);
}

function setParams(p) {
  fields.forEach(function (f) {
    var e = el(f);
    if (e.type === "checkbox") e.checked = !!p[f]; else e.value = p[f];
  });
  SLIDER_FIELDS.forEach(settleSlider);
  mode = p.mode;
  sides.width = p.width; sides.height = p.height;
  setShape(p.shape);
  showShape();
  drawCrop();
}

function artAspect() { return shape.sides === 1 ? shape.aspect : sides.width / sides.height; }

function artHeight() { return shape.sides === 1 ? sides.width / shape.aspect : sides.height; }

function setShape(id) {
  shape = shapes.filter(function (s) { return s.id === id; })[0] || shapes[0];  // a job saved with a shape this version dropped
  el("shape").value = shape.id;
}

function iconPoints(s) {
  var aspect = s.sides === 1 ? s.aspect : TWO_SIDED_ICON_ASPECT, room = ICON_BOX - 2 * ICON_INSET;
  var width = room * Math.min(1, aspect), height = room * Math.min(1, 1 / aspect);
  var left = (ICON_BOX - width) / 2, top = (ICON_BOX - height) / 2;
  return s.outline.map(function (p) { return (left + p[0] * width).toFixed(2) + "," + (top + p[1] * height).toFixed(2); }).join(" ");
}

function shapeIcon(s) {
  var svg = document.createElementNS(SVG_NAMESPACE, "svg"), polygon = document.createElementNS(SVG_NAMESPACE, "polygon");
  svg.setAttribute("viewBox", "0 0 " + ICON_BOX + " " + ICON_BOX);
  svg.setAttribute("aria-hidden", "true");
  polygon.setAttribute("points", iconPoints(s));
  svg.appendChild(polygon);
  return svg;
}

function buildShapePicker() {
  var box = el("shapes");
  box.innerHTML = "";
  shapes.forEach(function (s) {
    var b = document.createElement("button");
    b.type = "button"; b.dataset.shape = s.id; b.title = s.label;
    b.setAttribute("aria-label", s.label);
    b.appendChild(shapeIcon(s));
    b.addEventListener("click", function () { chooseShape(s.id); });
    box.appendChild(b);
  });
}

function shapeCaption() {
  if (shape.sides !== 1 || shape.aspect === 1) return shape.label;
  return shape.label + ", " + Math.round(artHeight()) + " mm tall";  // its height has no field, so say what the art size gives
}

function showShape() {
  var oneSided = shape.sides === 1;
  el("widthLabel").textContent = oneSided ? "Art size" : "Width";
  el("heightRow").hidden = oneSided;
  el("shapeName").textContent = shapeCaption();
  Array.prototype.forEach.call(el("shapes").children, function (b) {
    var on = b.dataset.shape === shape.id;
    b.className = on ? "on" : "";
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function chooseShape(id) {
  setShape(id);
  showShape();
  reframe();
}

function settleSide(id) {
  var typed = parseFloat(el(id).value);
  if (!isNaN(typed)) sides[id] = Math.max(minSide, typed);
  el(id).value = sides[id];
}

function wireSide(id) {
  el(id).addEventListener("change", function () {
    settleSide(id);
    showShape();
    if (shape.sides === 2) reframe();  // these two set the picture's aspect, so the crop changes with them
  });
}

function paintSlider(slider) {
  var low = parseFloat(slider.min), span = parseFloat(slider.max) - low;
  slider.style.setProperty("--ol-slider-fill", (parseFloat(slider.value) - low) / span * 100 + "%");
}

function applyLimits(limits) {
  if (limits && limits.min_side) {
    minSide = limits.min_side;
    el("width").min = minSide; el("height").min = minSide;
  }
  SLIDER_FIELDS.forEach(function (id) {
    var range = limits && limits[id];
    if (!range) return;
    var slider = el(id + "_slider");
    [slider, el(id)].forEach(function (input) { input.min = range[0]; input.max = range[1]; input.step = SLIDER_STEP; });
    slider.hidden = false;
    sliders[id] = slider;
  });
}

function moveSliderToField(id) {
  var slider = sliders[id], typed = parseFloat(el(id).value);
  if (!slider) return;
  if (!isNaN(typed)) slider.value = typed;
  paintSlider(slider);
}

// A range input clamps and steps whatever it is given, so writing its value back makes the two agree.
function settleSlider(id) {
  if (!sliders[id]) return;
  moveSliderToField(id);
  el(id).value = sliders[id].value;
}

function wireSlider(id) {
  var slider = el(id + "_slider"), field = el(id);
  slider.addEventListener("input", function () { field.value = slider.value; paintSlider(slider); renderChecks(); request(); });
  field.addEventListener("input", function () { moveSliderToField(id); });
  field.addEventListener("change", function () { settleSlider(id); });
}

function showModes() {
  var box = el("modes");
  box.innerHTML = "";
  box.hidden = modes.length < 2;  // a single style is shown as a name: there is nothing to press
  modes.forEach(function (m) {
    var b = document.createElement("button");
    b.type = "button"; b.textContent = m.label; b.className = m.id === mode ? "on" : "";
    b.addEventListener("click", function () { mode = m.id; showModes(); renderChecks(); request(); });
    box.appendChild(b);
    if (m.id === mode) { el("styleName").textContent = m.label; el("styleNote").textContent = m.note; }
  });
}

function check(done, title, detail) {
  var row = document.createElement("div"), mark = document.createElement("i"), body = document.createElement("div");
  row.className = done ? "ol-check" : "ol-check todo";
  mark.textContent = done ? "✓" : "!";
  body.textContent = title;
  if (detail) {
    var note = document.createElement("div");
    note.className = "ol-muted"; note.textContent = detail;
    body.appendChild(note);
  }
  row.appendChild(mark); row.appendChild(body);
  el("checks").appendChild(row);
}

function renderChecks() {
  el("checks").innerHTML = "";
  check(!!image, image ? "Picture loaded" : "Pick a picture");
  if (printer) {
    var layer = parseFloat(el("layer_height").value), nozzle = parseFloat(el("nozzle").value);
    var layerOk = Math.abs(layer - printer.layer_height) <= 0.005, nozzleOk = Math.abs(nozzle - printer.nozzle) <= 0.001;
    check(layerOk, layerOk ? "Layer height matches the process preset" : "Layer height differs from the process preset",
      layerOk ? "" : "The preset uses " + printer.layer_height + " mm and the job " + layer + " mm. Match them, or the slice stops with an error.");
    check(nozzleOk, nozzleOk ? "Nozzle matches the printer preset" : "Nozzle differs from the printer preset",
      nozzleOk ? "" : "The preset has a " + printer.nozzle + " mm nozzle and the job " + nozzle + " mm. Match them, or the slice stops with an error.");
  }
  if (selected !== null) {
    check(selected, selected ? "Slicing step is selected" : "Select the slicing step",
      selected ? "" : "Process preset, Others, Slicing Pipeline Plugin: add Line Art Studio G-code.");
  }
  var base = filamentAt("base_filament"), art = filamentAt("art_filament");
  if (base && art && el("base_filament").value !== el("art_filament").value) {
    var dark = luminance(art.color) < luminance(base.color), invert = el("invert").checked, good = dark !== invert;
    check(good, good ? "Tone suits the filament colors" : (invert ? "Turn off Light line on a dark base" : "Turn on Light line on a dark base"),
      good ? "" : (invert ? "The line filament is darker than the base." : "The line filament is lighter than the base, so the picture would be a negative."));
  }
  if (image) {
    var saved = image === savedImage && JSON.stringify(params()) === savedParams;
    check(saved, saved ? "Job saved with these settings" : "Save the job",
      saved ? "" : "The slice uses the last saved job, not what is on this page.");
  }
  if (onPlate !== null) {
    check(onPlate, onPlate ? "Base is on the plate" : "Put the base on the plate", onPlate ? "" : "The save button adds it.");
  }
}

function renderStatus(status) {
  var e = el("lastSlice");
  if (!status) { e.textContent = "No slice yet. Slice the base, then check here."; e.className = "ol-muted"; return; }
  e.textContent = status.message;
  e.className = status.ok ? "ol-muted" : "ol-error";
}

function renderStack(stack) {
  el("stack").textContent = "Base " + stack.base.toFixed(2) + " mm + line " + stack.art.toFixed(2) + " mm = " + stack.total.toFixed(2) + " mm";
  el("stackBar").hidden = false;
  el("stackBase").style.width = (stack.base / stack.total * 100) + "%";
  el("stackArt").style.width = (stack.art / stack.total * 100) + "%";
}

function renderMetrics(s) {
  el("mLength").textContent = (s.length_mm / 1000).toFixed(1) + " m";
  el("mTime").textContent = Math.round(s.time_s / 60) + " min";
  el("mPoints").textContent = s.points.toLocaleString("en-US");
  el("mFlow").textContent = s.max_flow.toFixed(1) + " mm³/s";
  var limited = s.speed < parseFloat(el("speed").value) - 0.05;
  el("speedNote").textContent = limited ? "The filament's flow limit holds the speed at " + s.speed.toFixed(0) + " mm/s." : "";
}

function compute() {
  clearTimeout(timer);
  el("lineState").textContent = "Computing the line. A detailed picture can take up to a minute.";
  send({ cmd: "preview", params: params(), image: image });
}

function request() {
  if (!ready) return;
  clearTimeout(timer);
  if (image) timer = setTimeout(compute, 700);
}

function bytes(b64) {
  var s = atob(b64), a = new Uint8Array(s.length);
  for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
  return a;
}

function atBoxEdge(v) { return v <= CORNER_TOLERANCE || v >= 1 - CORNER_TOLERANCE; }

// Only then is there nothing outside the art to mark, wherever the outline came from.
function fillsBox(outline) { return outline.every(function (p) { return atBoxEdge(p[0]) && atBoxEdge(p[1]); }); }

function traceOutline(g, outline, width, height) {
  outline.forEach(function (p, i) { g[i ? "lineTo" : "moveTo"](p[0] * width, p[1] * height); });
  g.closePath();
}

function themeColor(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function shapePreview(g, size, outline) {
  g.globalCompositeOperation = "destination-in";
  g.beginPath(); traceOutline(g, outline, size, size); g.fill();
  g.globalCompositeOperation = "source-over";
  g.strokeStyle = themeColor("--orca-muted"); g.lineWidth = size * PREVIEW_OUTLINE_SHARE; g.stroke();
}

function drawPreview(size, data, outline) {
  var c = el("c"), g = c.getContext("2d"), a = bytes(data), invert = el("invert").checked;
  c.width = size; c.height = size;
  var img = g.createImageData(size, size);
  for (var i = 0; i < a.length; i++) {
    var v = a[i] / 255, j = i * 4, d = invert ? 30 + 215 * v : 245 - 215 * v;
    img.data[j] = d; img.data[j + 1] = d; img.data[j + 2] = d; img.data[j + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  var full = fillsBox(outline);
  if (!full) shapePreview(g, size, outline);
  c.hidden = false;
  el("emptyNote").hidden = true;
  el("previewBox").className = full ? "ol-preview" : "ol-preview shaped";
  el("previewBox").style.background = invert && full ? "rgb(30, 30, 30)" : "";
  fitPreview();
}

function fitPreview() {
  var box = el("previewBox"), side = Math.min(box.clientWidth, box.clientHeight) - 24;
  if (side > 0) { el("c").style.width = side + "px"; el("c").style.height = side + "px"; }
}
window.addEventListener("resize", fitPreview);

function applyState(m) {
  if (m.filaments) fillFilaments(m.filaments);
  if (m.printer) printer = m.printer;
  if (typeof m.selected === "boolean") selected = m.selected;
  if (typeof m.on_plate === "boolean") onPlate = m.on_plate;
  renderChecks();
}

window.orca.onMessage(function (m) {
  if (m.type === "init") {
    modes = m.modes; shapes = m.shapes; buildShapePicker(); fillFilaments(m.filaments); applyLimits(m.limits); setParams(m.params); showFilaments(); showModes(); ready = true; msg("");
    applyState({ printer: { nozzle: m.machine.nozzle, layer_height: m.machine.layer_height }, selected: m.selected, on_plate: m.on_plate });
    request();
  } else if (m.type === "state") {
    applyState(m);
    renderStatus(m.status);
  } else if (m.type === "preview") {
    drawPreview(m.size, m.data, m.outline); msg(""); el("lineState").textContent = "";
    renderStack(m.stack);
    renderMetrics(m.stats);
    applyState(m);
    if (wantSave) { wantSave = false; send({ cmd: "save", params: params(), image: image }); }
  } else if (m.type === "saved") {
    var notes = {
      added: "Saved. The base is being added to the plate; slice it when it appears.",
      present: "Saved. The base is already on the plate; slice it.",
      stale: "Saved, but the base on the plate has the old size or shape. Delete it from the plate and press the button again.",
      manual: "Saved. The base could not be added automatically; drop this file on the plate:"
    };
    msg(notes[m.plate], m.plate === "stale");
    el("path").textContent = m.plate === "manual" ? m.stl : "";
    savedImage = image; savedParams = JSON.stringify(params());
    renderChecks();
  } else if (m.type === "need_route") {
    wantSave = true; compute();
  } else if (m.type === "status") {
    renderStatus(m.status);
  } else if (m.type === "error") {
    wantSave = false; el("lineState").textContent = ""; msg(m.message, true);
  }
});

function num(id, low, high, fallback) {
  var v = parseFloat(el(id).value);
  return isNaN(v) ? fallback : Math.min(high, Math.max(low, v));
}

function freeRoom(whole, part) {
  var free = (whole - part) / 2;
  return free < SUB_PIXEL ? 0 : free;
}

function cropBox() {
  var aspect = artAspect(), height = Math.min(source.height, source.width / aspect) / num("zoom", 1, 8, 1), width = height * aspect;
  var freeX = freeRoom(source.width, width), freeY = freeRoom(source.height, height);
  return { width: width, height: height, freeX: freeX, freeY: freeY,
    x: freeX + freeX * num("panx", -100, 100, 0) / 100, y: freeY + freeY * num("pany", -100, 100, 0) / 100 };
}

function overlayShape(g, width, height) {
  if (fillsBox(shape.outline)) return;
  g.beginPath(); g.rect(0, 0, width, height); traceOutline(g, shape.outline, width, height);
  g.fillStyle = themeColor("--orca-bg"); g.globalAlpha = CROP_VEIL_OPACITY; g.fill("evenodd"); g.globalAlpha = 1;
  g.beginPath(); traceOutline(g, shape.outline, width, height);
  g.strokeStyle = themeColor("--orca-accent"); g.lineWidth = CROP_OUTLINE_WIDTH; g.stroke();
}

function drawCrop() {
  var c = el("crop"), aspect = artAspect(), widthShare = Math.min(1, aspect);
  c.width = Math.round(CROP_CANVAS_LONGEST_SIDE * widthShare);
  c.height = Math.round(CROP_CANVAS_LONGEST_SIDE * Math.min(1, 1 / aspect));
  c.style.width = widthShare * 100 + "%";
  var g = c.getContext("2d");
  if (source) { var b = cropBox(); g.drawImage(source, b.x, b.y, b.width, b.height, 0, 0, c.width, c.height); }
  overlayShape(g, c.width, c.height);
}

function encode() {
  clearTimeout(encodeTimer); encodeTimer = null;
  if (!source) return;
  var b = cropBox(), scale = Math.min(1, PICTURE_LONGEST_SIDE / Math.max(b.width, b.height));
  var width = Math.max(1, Math.round(b.width * scale)), height = Math.max(1, Math.round(b.height * scale));
  var c = document.createElement("canvas"); c.width = width; c.height = height;
  var g = c.getContext("2d");
  g.drawImage(source, b.x, b.y, b.width, b.height, 0, 0, width, height);
  var d = g.getImageData(0, 0, width, height).data, out = new Uint8Array(width * height);
  for (var i = 0; i < out.length; i++) out[i] = Math.round(0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2]);
  var s = ""; for (var k = 0; k < out.length; k += 8192) s += String.fromCharCode.apply(null, out.subarray(k, k + 8192));
  image = { width: width, height: height, data: btoa(s) };
  renderChecks();
  request();
}

function reframe() { drawCrop(); encode(); }

function moved() {
  drawCrop();
  clearTimeout(encodeTimer);
  encodeTimer = setTimeout(encode, 200);
}

["zoom", "panx", "pany"].forEach(function (id) { el(id).addEventListener("input", moved); });

var drag = null;
el("crop").addEventListener("pointerdown", function (ev) {
  if (!source) return;
  drag = { x: ev.clientX, y: ev.clientY, panx: num("panx", -100, 100, 0), pany: num("pany", -100, 100, 0) };
  el("crop").setPointerCapture(ev.pointerId);
});
el("crop").addEventListener("pointermove", function (ev) {
  if (!drag) return;
  var b = cropBox(), scale = b.width / el("crop").clientWidth;
  if (b.freeX > 0) el("panx").value = Math.round(Math.min(100, Math.max(-100, drag.panx - (ev.clientX - drag.x) * scale / b.freeX * 100)));
  if (b.freeY > 0) el("pany").value = Math.round(Math.min(100, Math.max(-100, drag.pany - (ev.clientY - drag.y) * scale / b.freeY * 100)));
  moved();
});
el("crop").addEventListener("pointerup", function () { drag = null; });
el("crop").addEventListener("wheel", function (ev) {
  if (!source) return;
  ev.preventDefault();
  el("zoom").value = (Math.min(8, Math.max(1, num("zoom", 1, 8, 1) * (ev.deltaY < 0 ? 1.1 : 0.9)))).toFixed(2);
  moved();
}, { passive: false });

["base_filament", "art_filament"].forEach(function (id) { el(id).addEventListener("change", showFilaments); });
el("nozzle").addEventListener("change", function () {
  var n = parseFloat(el("nozzle").value);
  if (!(n > 0)) return;
  el("line_width").value = (n * 1.05).toFixed(2);
  request();
});

el("file").addEventListener("change", function (ev) {
  var file = ev.target.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function () {
    var img = new Image();
    img.onload = function () {
      source = img;
      el("fileName").textContent = file.name;
      el("fileLabel").firstChild.textContent = "Choose another picture";
      el("zoom").value = 1; el("panx").value = 0; el("pany").value = 0;
      reframe();
    };
    img.onerror = function () { msg("This image could not be read.", true); };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
});

SLIDER_FIELDS.forEach(wireSlider);  // before the listeners below, so a typed value is clamped when they run
["width", "height"].forEach(wireSide);
fields.forEach(function (f) { el(f).addEventListener("change", function () { renderChecks(); request(); }); });
el("save").addEventListener("click", function () { if (encodeTimer !== null) encode(); send({ cmd: "save", params: params(), image: image }); });
el("refresh").addEventListener("click", function () { send({ cmd: "state" }); });

// The presets and the plate change on other tabs, so re-read them when this tab comes back and while it is shown.
document.addEventListener("visibilitychange", function () { if (!document.hidden) send({ cmd: "state" }); });
setInterval(function () { if (!document.hidden) send({ cmd: "state" }); }, 4000);
send({ cmd: "init" });
</script>
</body>
</html>
"""

PAGE_HTML = _PAGE.replace("/*ONELINE_CSS*/", CSS)
