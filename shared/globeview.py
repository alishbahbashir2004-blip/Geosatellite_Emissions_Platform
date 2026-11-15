# globeview.py
# Decorative idle-state globe for the map column (no gas data here). Phases:
# "idle" (markup is byte-identical every rerun so Streamlit won't restart the
# iframe), "launch" (while EE queries), "zoom" (push-in on the result).

import base64
import functools
import json
import os

import streamlit.components.v1 as components

TEXTURE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "earth_texture.jpg")  # baked into the page as a data URI

IDLE_SPIN = 0.13     # radians/second, a slow drift
FAST_SPIN = 0.55     # radians/second once a query is running
RAMP = 0.7           # seconds to reach the fast spin
ZOOM_SECONDS = 1.5   # length of the push-in; frontend sleeps to match
PIN_COUNT = 14       # scattered markers, fixed seed so they don't wander
ZOOM_SCALE = 7.5     # how far in the push-in travels


@functools.lru_cache(maxsize=1)
def _texture_uri():
    with open(TEXTURE_FILE, "rb") as fh:
        return "data:image/jpeg;base64," + base64.b64encode(fh.read()).decode()


_HTML = """
<style>
  html, body { margin:0; padding:0; background:transparent; overflow:hidden; }
  #wrap { width:100%; height:100vh; }
  #globe { width:100%; height:100%; display:block; }
</style>
<div id="wrap"><canvas id="globe"></canvas></div>
<script>
(function(){
  var CFG = __CONFIG__;
  var TWO_PI = Math.PI * 2;
  var PAGE_START = Date.now() / 1000;
  var cvs = document.getElementById('globe');
  var ctx = cvs.getContext('2d');
  var DPR = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0;

  function resize(){
    W = cvs.clientWidth; H = cvs.clientHeight;
    cvs.width = Math.round(W * DPR); cvs.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  window.addEventListener('resize', resize);
  // Streamlit resizes the iframe after load without firing a window resize.
  if (window.ResizeObserver) new ResizeObserver(resize).observe(cvs);
  resize();

  // ---- texture -----------------------------------------------------------
  var TW = 0, TH = 0, TEX = null;
  var img = new Image();
  img.onload = function(){
    TW = img.naturalWidth; TH = img.naturalHeight;
    var tc = document.createElement('canvas');
    tc.width = TW; tc.height = TH;
    var tctx = tc.getContext('2d', { willReadFrequently: true });
    tctx.drawImage(img, 0, 0);
    TEX = tctx.getImageData(0, 0, TW, TH).data;
  };
  img.src = CFG.texture;

  // ---- pins --------------------------------------------------------------
  function mulberry32(a){
    return function(){
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  var rnd = mulberry32(CFG.seed);
  var PINS = [];
  for (var p = 0; p < CFG.pins; p++){
    PINS.push({ lat: (rnd() * 128 - 62) * Math.PI / 180,
                lon: (rnd() * 360 - 180) * Math.PI / 180 });
  }
  // Zoom has one subject; scattered markers would just clutter it.
  if (CFG.phase === 'zoom' && CFG.focus){
    PINS = [{ lat: CFG.focus[0] * Math.PI / 180,
              lon: CFG.focus[1] * Math.PI / 180 }];
  }

  // ---- sphere ------------------------------------------------------------
  var TILT = -0.36;                 // tips the north pole toward the viewer
  var off = document.createElement('canvas');
  var octx = off.getContext('2d');
  var D = 0, buf = null, lutRow = null, lutLon = null, lutShade = null,
      lutAlpha = null;

  // Each pixel maps to a fixed lat/lon *offset*; spin just slides it, so the
  // trig is precomputed once per size into a lookup table, not per frame.
  function buildLUT(d){
    D = d; off.width = D; off.height = D;
    buf = octx.createImageData(D, D);
    var n = D * D;
    lutRow = new Int32Array(n); lutLon = new Float32Array(n);
    lutShade = new Float32Array(n); lutAlpha = new Float32Array(n);
    var R = D / 2, ct = Math.cos(TILT), st = Math.sin(TILT);
    var lx = -0.40, ly = 0.40, lz = 0.82;
    var ln = Math.sqrt(lx*lx + ly*ly + lz*lz);
    for (var py = 0; py < D; py++){
      for (var px = 0; px < D; px++){
        var i = py * D + px;
        var nx = (px + 0.5 - R) / R, ny = (py + 0.5 - R) / R;
        var d2 = nx * nx + ny * ny;
        if (d2 >= 1){ lutAlpha[i] = 0; continue; }
        var X = nx, Y = -ny, Z = Math.sqrt(1 - d2);
        var y = Y * ct + Z * st, z = -Y * st + Z * ct;
        var lat = Math.asin(Math.max(-1, Math.min(1, y)));
        lutLon[i] = Math.atan2(X, z);
        lutRow[i] = Math.round((0.5 - lat / Math.PI) * (TH - 1)) * TW;
        var dot = (X * lx + Y * ly + Z * lz) / ln;
        lutShade[i] = 0.34 + 0.92 * Math.max(0, dot);
        lutAlpha[i] = Math.min(1, (1 - Math.sqrt(d2)) * R * 1.5);
      }
    }
  }

  function paintSphere(rot){
    var px = buf.data, n = D * D;
    var shift = 0.5 - rot / TWO_PI;
    for (var i = 0; i < n; i++){
      var a = lutAlpha[i];
      var o = i * 4;
      if (a <= 0){ px[o + 3] = 0; continue; }
      var u = lutLon[i] / TWO_PI + shift;
      u -= Math.floor(u);
      var s = (lutRow[i] + ((u * TW) | 0)) * 4;
      var sh = lutShade[i];
      px[o]     = TEX[s]     * sh;
      px[o + 1] = TEX[s + 1] * sh;
      px[o + 2] = TEX[s + 2] * sh;
      px[o + 3] = a * 255;
    }
    octx.putImageData(buf, 0, 0);
  }

  function project(lat, lon, rot, R, cx, cy){
    var x = Math.cos(lat) * Math.sin(lon), y = Math.sin(lat),
        z = Math.cos(lat) * Math.cos(lon);
    var c = Math.cos(rot), s = Math.sin(rot);
    var x2 = x * c + z * s, z2 = -x * s + z * c;
    var ct = Math.cos(TILT), st = Math.sin(TILT);
    return [cx + R * x2, cy - R * (y * ct - z2 * st), y * st + z2 * ct];
  }

  function drawPin(sx, sy, depth, k){
    var w = 5.8 * k, h = 15.5 * k;
    ctx.globalAlpha = Math.min(1, depth * 3.2);
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.beginPath(); ctx.ellipse(sx, sy, w * 0.75, w * 0.3, 0, 0, TWO_PI); ctx.fill();
    ctx.fillStyle = '#ff2d20';
    ctx.beginPath(); ctx.arc(sx, sy - h, w, 0, TWO_PI); ctx.fill();
    ctx.beginPath();
    ctx.moveTo(sx - w * 0.66, sy - h + w * 0.62);
    ctx.lineTo(sx, sy);
    ctx.lineTo(sx + w * 0.66, sy - h + w * 0.62);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    ctx.beginPath(); ctx.arc(sx, sy - h, w * 0.36, 0, TWO_PI); ctx.fill();
    ctx.globalAlpha = 1;
  }

  // ---- timeline ----------------------------------------------------------
  // Closed form (not per-frame accumulation), so a second iframe starting
  // mid-flight lands on the same angle.
  function freeRot(t){
    if (t <= 0) return 0;
    var i = CFG.idleSpin, f = CFG.fastSpin, T = CFG.ramp;
    if (CFG.phase === 'idle') return i * t;
    if (t < T) return i * t + (f - i) * t * t * t / (3 * T * T);
    return i * T + (f - i) * T / 3 + f * (t - T);
  }
  function wrap(a){
    a = (a + Math.PI) % TWO_PI;
    if (a < 0) a += TWO_PI;
    return a - Math.PI;
  }
  var zoomStartRot = 0, zoomDelta = 0;
  if (CFG.phase === 'zoom' && CFG.focus){
    zoomStartRot = freeRot(CFG.zoomAt - CFG.anchor);
    // Shortest rotation to bring the focus longitude to face the viewer.
    zoomDelta = wrap(-CFG.focus[1] * Math.PI / 180 - zoomStartRot);
  }
  function easeInOut(e){
    return e < 0.5 ? 4*e*e*e : 1 - Math.pow(-2*e + 2, 3) / 2;
  }

  function frame(){
    var now = Date.now() / 1000;
    var t = now - (CFG.phase === 'idle' ? PAGE_START : CFG.anchor);
    var rot, e = 0;
    if (CFG.phase === 'zoom' && CFG.focus){
      e = Math.min(1, Math.max(0, (now - CFG.zoomAt) / CFG.zoomSeconds));
      // Base spin continues at launch speed; homing turn eases in on top.
      rot = freeRot(t) + zoomDelta * easeInOut(e);
    } else {
      rot = freeRot(t);
    }

    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);

    var R = Math.min(W, H) * 0.46;
    var cx = W / 2, cy = H / 2;

    if (TEX){
      var want = Math.min(540, Math.round(2 * R * DPR));
      if (want !== D || lutRow === null) buildLUT(want);
      paintSphere(rot);
    }

    ctx.save();
    if (e > 0){
      var k = 1 + (CFG.zoomScale - 1) * Math.pow(e, 2.2);
      var pan = easeInOut(e);
      var f = project(CFG.focus[0] * Math.PI / 180, CFG.focus[1] * Math.PI / 180,
                      rot, R, cx, cy);
      ctx.translate(cx, cy);
      ctx.scale(k, k);
      ctx.translate(-(cx + (f[0] - cx) * pan), -(cy + (f[1] - cy) * pan));
    }

    if (TEX){
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(off, cx - R, cy - R, R * 2, R * 2);
    }

    var front = [];
    for (var j = 0; j < PINS.length; j++){
      var v = project(PINS[j].lat, PINS[j].lon, rot, R, cx, cy);
      if (v[2] > 0.04) front.push(v);
    }
    front.sort(function(a, b){ return a[2] - b[2]; });
    for (var m = 0; m < front.length; m++){
      drawPin(front[m][0], front[m][1], front[m][2], 0.6 + 0.4 * front[m][2]);
    }
    ctx.restore();

    // Whiteout over the tail of the push-in hides the swap to the real map.
    if (e > 0.5){
      ctx.globalAlpha = Math.min(0.94, (e - 0.5) / 0.5 * 0.94);
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, W, H);
      ctx.globalAlpha = 1;
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
</script>
"""


def render_globe(phase="idle", focus=None, height=430, anchor=0.0, zoom_at=0.0):
    """Draw the placeholder globe. `anchor`/`zoom_at` must be shared across
    both phases of one transition, else the globe jumps at handover. Idle's
    markup must stay byte-identical every rerun, or Streamlit restarts it."""
    config = {
        "phase": phase,
        "seed": 20260825,
        "pins": PIN_COUNT,
        "idleSpin": IDLE_SPIN,
        "fastSpin": FAST_SPIN,
        "ramp": RAMP,
        "zoomSeconds": ZOOM_SECONDS,
        "zoomScale": ZOOM_SCALE,
        "focus": [round(focus[0], 4), round(focus[1], 4)] if focus else None,
        "anchor": round(anchor, 3),
        "zoomAt": round(zoom_at, 3),
        "texture": _texture_uri(),
    }
    if phase == "idle":
        config["focus"] = None
        config["anchor"] = 0.0
        config["zoomAt"] = 0.0
    components.html(_HTML.replace("__CONFIG__", json.dumps(config)),
                    height=height)
