/*
 * 3D view of the four panel setups (three.js). Geometry only: every angle and power
 * number shown comes from solar-model.js. Units are meters. x = east, y = up, z = south.
 * The array is 12 modules of about 1 m x 2 m, as in the modeled system.
 */
(function (root) {
  "use strict";
  var R_SUN = 17.5, XS = [-13.5, -4.5, 4.5, 13.5];

  function moduleTexture(T, longAlongX) {
    var c = document.createElement("canvas"); c.width = longAlongX ? 512 : 256; c.height = longAlongX ? 256 : 512;
    var g = c.getContext("2d"), W = c.width, H = c.height;
    g.fillStyle = "#c9ced4"; g.fillRect(0, 0, W, H);                       // aluminum frame
    var m = 7; g.fillStyle = "#0d1a33"; g.fillRect(m, m, W - 2 * m, H - 2 * m);
    var nx = longAlongX ? 12 : 6, ny = longAlongX ? 6 : 12, cw = (W - 2 * m) / nx, ch = (H - 2 * m) / ny;
    for (var i = 0; i < nx; i++) for (var j = 0; j < ny; j++) {
      var x = m + i * cw, y = m + j * ch, gr = g.createLinearGradient(x, y, x + cw, y + ch);
      gr.addColorStop(0, "#16305f"); gr.addColorStop(1, "#0f2247");
      g.fillStyle = gr; g.fillRect(x + 1.2, y + 1.2, cw - 2.4, ch - 2.4);
    }
    g.strokeStyle = "rgba(210,220,235,.35)"; g.lineWidth = 1;               // busbars
    for (var k = 1; k < (longAlongX ? ny : nx) * 3; k++) {
      g.beginPath();
      if (longAlongX) { var yy = m + k * ch / 3; g.moveTo(m, yy); g.lineTo(W - m, yy); }
      else { var xx = m + k * cw / 3; g.moveTo(xx, m); g.lineTo(xx, H - m); }
      g.stroke();
    }
    var t = new T.CanvasTexture(c); t.wrapS = t.wrapT = T.RepeatWrapping; t.encoding = T.sRGBEncoding; t.anisotropy = 8;
    return t;
  }
  function groundTexture(T) {
    var c = document.createElement("canvas"); c.width = c.height = 512; var g = c.getContext("2d");
    g.fillStyle = "#c4b594"; g.fillRect(0, 0, 512, 512);
    var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var i = 0; i < 9000; i++) {
      var s = rnd() * 2.2 + 0.4; g.fillStyle = "rgba(" + (rnd() < .5 ? "120,105,80," : "250,244,230,") + (rnd() * .16).toFixed(3) + ")";
      g.fillRect(rnd() * 512, rnd() * 512, s, s);
    }
    var t = new T.CanvasTexture(c); t.wrapS = t.wrapT = T.RepeatWrapping; t.repeat.set(5, 5); t.encoding = T.sRGBEncoding;
    return t;
  }
  function glowTexture(T) {
    var c = document.createElement("canvas"); c.width = c.height = 128; var g = c.getContext("2d");
    var gr = g.createRadialGradient(64, 64, 4, 64, 64, 64);
    gr.addColorStop(0, "rgba(255,236,170,1)"); gr.addColorStop(.25, "rgba(255,214,110,.55)"); gr.addColorStop(1, "rgba(255,206,84,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    return new T.CanvasTexture(c);
  }
  function textSprite(T, text) {
    var c = document.createElement("canvas"); c.width = c.height = 64; var g = c.getContext("2d");
    g.font = "600 40px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = "#5D6269"; g.fillText(text, 32, 34);
    var s = new T.Sprite(new T.SpriteMaterial({ map: new T.CanvasTexture(c), depthTest: false, toneMapped: false })); s.scale.set(2.2, 2.2, 1);
    return s;
  }

  function create(canvas, labelBox, setups, colors, names) {
    var T = root.THREE;
    if (!T) return null;
    var renderer;
    try { renderer = new T.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true }); } catch (err) { return null; }
    renderer.setPixelRatio(Math.min(root.devicePixelRatio || 1, 2));
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.toneMapping = T.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.92;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;

    var scene = new T.Scene();
    var camera = new T.PerspectiveCamera(34, 1.6, 0.5, 300);
    camera.position.set(-8, 13.5, 47);
    var target = new T.Vector3(0, 5.2, 0); camera.lookAt(target);

    var hemi = new T.HemisphereLight(0xdfeaf7, 0xb9ae98, 0.6); scene.add(hemi);
    var sunLight = new T.DirectionalLight(0xfff2d6, 1.5);
    sunLight.castShadow = true; sunLight.shadow.mapSize.set(2048, 2048);
    var sc = sunLight.shadow.camera; sc.left = -26; sc.right = 26; sc.top = 26; sc.bottom = -26; sc.near = 1; sc.far = 120;
    sunLight.shadow.bias = -0.0006; sunLight.shadow.normalBias = 0.03;
    scene.add(sunLight); scene.add(sunLight.target);

    // ground: a round slab, like a site model on a table
    var ground = new T.Mesh(new T.CylinderGeometry(20.5, 20.5, 0.5, 96), [
      new T.MeshStandardMaterial({ color: 0xb8ad98, roughness: 1 }),
      new T.MeshStandardMaterial({ map: groundTexture(T), roughness: 1 }),
      new T.MeshStandardMaterial({ color: 0xb8ad98, roughness: 1 })]);
    ground.position.y = -0.25; ground.receiveShadow = true; scene.add(ground);
    [["N", 0, -19], ["S", 0, 19], ["E", 19, 0], ["W", -19, 0]].forEach(function (m) {
      var s = textSprite(T, m[0]); s.position.set(m[1], 0.5, m[2]); scene.add(s);
    });

    var steel = new T.MeshStandardMaterial({ color: 0x8d9299, roughness: 0.55, metalness: 0.7 });
    var frameMat = new T.MeshStandardMaterial({ color: 0xbfc4ca, roughness: 0.45, metalness: 0.8 });
    var back = new T.MeshStandardMaterial({ color: 0xe9e9e6, roughness: 0.8 });
    function cyl(r, h) { var m = new T.Mesh(new T.CylinderGeometry(r, r, h, 16), steel); m.castShadow = true; m.receiveShadow = true; return m; }
    function box(w, h, d, mat) { var m = new T.Mesh(new T.BoxGeometry(w, h, d), mat); m.castShadow = true; m.receiveShadow = true; return m; }

    // an array of modules lying in its own x-z plane, facing +y
    function makeArray(w, d, color, longAlongX) {
      var grp = new T.Group();
      var slab = box(w, 0.08, d, [frameMat, frameMat, frameMat, back, frameMat, frameMat]); slab.position.y = -0.04; grp.add(slab);
      var tex = moduleTexture(T, longAlongX); tex.repeat.set(longAlongX ? w / 2 : w, longAlongX ? d : d / 2);
      var glass = new T.Mesh(new T.PlaneGeometry(w - 0.04, d - 0.04),
        new T.MeshPhysicalMaterial({ map: tex, roughness: 0.18, metalness: 0.35, clearcoat: 1, clearcoatRoughness: 0.08 }));
      glass.rotation.x = -Math.PI / 2; glass.position.y = 0.004; glass.receiveShadow = true; grp.add(glass);
      var trim = new T.MeshStandardMaterial({ color: new T.Color(color), roughness: 0.6 });
      [[w + 0.1, 0.1, 0, d / 2 + 0.03], [w + 0.1, 0.1, 0, -d / 2 - 0.03]].forEach(function (b) { var m = box(b[0], 0.1, b[1], trim); m.position.set(b[2], -0.04, b[3]); grp.add(m); });
      [[0.1, d, w / 2 + 0.03], [0.1, d, -w / 2 - 0.03]].forEach(function (b) { var m = box(b[0], 0.1, b[1], trim); m.position.set(b[2], -0.04, 0); grp.add(m); });
      return grp;
    }

    var mounts = {};
    setups.forEach(function (k, i) {
      var base = new T.Group(); base.position.x = XS[i]; scene.add(base);
      var arr, h;
      if (k === "Flat") {
        h = 0.7; arr = makeArray(6, 4, colors[k], false);
        [[-2.6, -1.6], [2.6, -1.6], [-2.6, 1.6], [2.6, 1.6]].forEach(function (p) { var c = cyl(0.06, h); c.position.set(p[0], h / 2, p[1]); base.add(c); });
      } else if (k === "Fixed, best tilt") {
        h = 1.9; arr = makeArray(6, 4, colors[k], false);
        [-2, 2].forEach(function (x) {
          var c = cyl(0.09, h); c.position.set(x, h / 2, 0); base.add(c);
          var foot = box(0.5, 0.12, 0.5, steel); foot.position.set(x, 0.06, 0); base.add(foot);
        });
        var beam = box(4.4, 0.12, 0.12, steel); beam.position.y = h - 0.1; base.add(beam);
      } else if (k === "Single axis") {
        h = 2.4; arr = makeArray(4, 6, colors[k], true);
        [-2.6, 0, 2.6].forEach(function (z) { var c = cyl(0.1, h); c.position.set(0, h / 2, z); base.add(c); });
        var tube = cyl(0.11, 6.6); tube.rotation.x = Math.PI / 2; tube.position.y = h - 0.14; base.add(tube);
        var motor = box(0.45, 0.4, 0.5, steel); motor.position.set(0, h - 0.3, 0); base.add(motor);
      } else {
        h = 3.0; arr = makeArray(6, 4, colors[k], false);
        var ped = cyl(0.2, h - 0.2); ped.position.y = (h - 0.2) / 2; base.add(ped);
        var foot2 = cyl(0.7, 0.14); foot2.position.y = 0.07; base.add(foot2);
        var head = box(0.6, 0.4, 0.6, steel); head.position.y = h - 0.3; base.add(head);
      }
      arr.position.y = h; base.add(arr);
      mounts[k] = { arr: arr, base: base, h: h };
    });

    // sun
    var sunGrp = new T.Group(); scene.add(sunGrp);
    var disc = new T.Mesh(new T.SphereGeometry(0.9, 24, 16), new T.MeshBasicMaterial({ color: 0xffc23d, toneMapped: false })); sunGrp.add(disc);
    var glow = new T.Sprite(new T.SpriteMaterial({ map: glowTexture(T), transparent: true, depthWrite: false, toneMapped: false })); glow.scale.set(9, 9, 1); sunGrp.add(glow);
    var pathLine = null;

    var labels = {};
    setups.forEach(function (k) {
      var d = document.createElement("div"); d.className = "lab3d";
      var n = document.createElement("b"); n.textContent = names[k];
      var i = document.createElement("i"); i.style.background = colors[k]; n.insertBefore(i, n.firstChild);
      var p = document.createElement("span"); d.appendChild(n); d.appendChild(p); labelBox.appendChild(d);
      labels[k] = { el: d, p: p };
    });

    var controls = null;
    if (T.OrbitControls && !(root.matchMedia && root.matchMedia("(pointer: coarse)").matches)) {
      controls = new T.OrbitControls(camera, canvas);
      controls.target.copy(target); controls.enablePan = false; controls.minDistance = 22; controls.maxDistance = 70;
      controls.maxPolarAngle = Math.PI * 0.49; controls.update();
      controls.addEventListener("change", draw);
    }

    var up = new T.Vector3(0, 1, 0), vx = new T.Vector3(), vy = new T.Vector3(), vz = new T.Vector3(), mat = new T.Matrix4(), tmp = new T.Vector3();
    function dirOf(zenith, azimuth) {
      var z = zenith * Math.PI / 180, a = azimuth * Math.PI / 180;
      return new T.Vector3(Math.sin(z) * Math.sin(a), Math.cos(z), -Math.sin(z) * Math.cos(a));
    }
    function orient(k, o) {
      vy.copy(dirOf(o.tilt, o.azimuth));
      if (k === "Single axis") { vz.set(0, 0, 1); vx.crossVectors(vy, vz).normalize(); }
      else {
        vx.crossVectors(up, vy); if (vx.lengthSq() < 1e-6) vx.set(1, 0, 0); vx.normalize();
        if (k !== "Dual axis" && vx.x < 0) vx.negate();
        vz.crossVectors(vx, vy).normalize();
      }
      mat.makeBasis(vx, vy, vz); mounts[k].arr.quaternion.setFromRotationMatrix(mat);
    }
    function size() {
      var w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== Math.round(w * renderer.getPixelRatio()) || canvas.height !== Math.round(h * renderer.getPixelRatio())) renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.fov = w / h < 1.25 ? 44 : 34;                 // narrow screens: widen the view
      camera.updateProjectionMatrix();
    }
    function draw() {
      size();
      renderer.render(scene, camera);
      var w = canvas.clientWidth, h = canvas.clientHeight;
      setups.forEach(function (k, i) {
        tmp.set(XS[i], 0, 5.6).project(camera);
        var L = labels[k].el;
        L.style.display = tmp.z < 1 ? "block" : "none";
        L.style.left = ((tmp.x + 1) / 2 * w) + "px"; L.style.top = ((1 - tmp.y) / 2 * h) + "px";
      });
    }
    function setPath(sunPath) {
      if (pathLine) { scene.remove(pathLine); pathLine.geometry.dispose(); }
      var pts = [];
      sunPath.forEach(function (s) { if (s.zenith < 90.5) pts.push(dirOf(s.zenith, s.azimuth).multiplyScalar(R_SUN)); });
      if (pts.length < 2) { pathLine = null; return; }
      pathLine = new T.Line(new T.BufferGeometry().setFromPoints(pts), new T.LineDashedMaterial({ color: 0x46607f, dashSize: 0.5, gapSize: 0.5, transparent: true, opacity: 0.55 }));
      pathLine.computeLineDistances(); scene.add(pathLine);
    }
    // e: {sun, w, res} from the page; res[k] = {o: orientation, r: step result}
    function update(e) {
      var el = 90 - e.sun.zenith, day = el > 0, d = dirOf(e.sun.zenith, e.sun.azimuth);
      sunGrp.visible = el > -1; sunGrp.position.copy(d).multiplyScalar(R_SUN);
      sunLight.position.copy(d).multiplyScalar(60); sunLight.target.position.set(0, 0, 0);
      var beam = day ? Math.min(1, e.w.dni / 900) : 0, low = day ? Math.min(1, el / 12) : 0;
      sunLight.intensity = 1.7 * beam * (0.35 + 0.65 * low);
      sunLight.color.setRGB(1, 0.86 + 0.1 * low, 0.66 + 0.2 * low);            // warmer near the horizon
      sunLight.castShadow = beam > 0.05;
      hemi.intensity = day ? 0.3 + 0.3 * Math.min(1, e.w.dhi / 250) + 0.12 * low : 0.14;
      setups.forEach(function (k) {
        orient(k, e.res[k].o);
        labels[k].p.textContent = (e.res[k].r.pac / 1000).toFixed(2) + " kW";
      });
      draw();
      return { day: day, cloudy: e.w.ghi > 0 ? Math.min(1, e.w.dhi / Math.max(e.w.ghi, 1)) : 0, low: low };
    }
    return { update: update, setPath: setPath, draw: draw };
  }
  root.Scene3D = { create: create };
})(this);
