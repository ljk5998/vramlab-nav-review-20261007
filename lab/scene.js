/* Conceptual geometry, not an RTX board model, memory allocation, or telemetry. */
const host = document.getElementById('lab-scene');
if (host) {
  const fallback = host.querySelector('.scene-fallback');
  const controls = document.querySelector('.scene-controls');
  const motionButton = document.getElementById('scene-motion');
  const layoutButton = document.getElementById('scene-layout');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let started = false;
  let visible = false;
  let draw = () => {};
  const observer = new IntersectionObserver(async ([entry]) => {
    visible = entry.isIntersecting;
    if (started) { draw(); return; }
    if (!visible) return;
    started = true;
    try {
      const THREE = await import('./vendor/three.module.min.js');
      const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.6;
      renderer.domElement.setAttribute('aria-hidden', 'true');
      host.append(renderer.domElement);
      fallback.hidden = true;
      controls.hidden = false;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(32, 1, .1, 100);
      camera.position.set(8.2, 7.1, 10.8);
      camera.lookAt(0, .45, 0);
      scene.add(new THREE.HemisphereLight(0xf5ffe4, 0x28312c, 4));
      const key = new THREE.DirectionalLight(0xf6fff2, 6);
      key.position.set(1, 7, 6); scene.add(key);
      const rim = new THREE.DirectionalLight(0xceff9c, 5);
      rim.position.set(-5, 2, -3); scene.add(rim);
      const fill = new THREE.DirectionalLight(0xb3d4ff, 2);
      fill.position.set(6, 0, -2); scene.add(fill);
      const study = new THREE.Group();
      study.rotation.y = -.35;
      scene.add(study);
      const metal = new THREE.MeshStandardMaterial({ color: 0x747f78, metalness: .75, roughness: .36 });
      const dark = new THREE.MeshStandardMaterial({ color: 0x1b2620, metalness: .48, roughness: .35 });
      const pale = new THREE.MeshStandardMaterial({ color: 0xb8c4ae, metalness: .5, roughness: .28 });
      const lime = new THREE.MeshStandardMaterial({ color: 0xc6e67e, emissive: 0x5f7b27, emissiveIntensity: .3, metalness: .45, roughness: .3 });
      const edgeMaterial = new THREE.LineBasicMaterial({ color: 0xa3b697, transparent: true, opacity: .55 });
      const limeEdge = new THREE.LineBasicMaterial({ color: 0xd3ed89, transparent: true, opacity: .8 });
      const layers = [];
      const addBox = (parent, width, height, depth, material, x = 0, y = 0, z = 0, edge = false) => {
        const geometry = new THREE.BoxGeometry(width, height, depth);
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(x, y, z);
        parent.add(mesh);
        if (edge) { const lines = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edge === 'lime' ? limeEdge : edgeMaterial); mesh.add(lines); }
        return mesh;
      };
      for (let i = 0; i < 4; i += 1) {
        const layer = new THREE.Group();
        layer.userData = { open: -1.15 + i * .97, closed: -.4 + i * .22 };
        layer.position.y = layer.userData.open;
        layers.push(layer); study.add(layer);
        const size = 4.7 - i * .36;
        addBox(layer, size, .1, size * .69, i === 1 ? pale : dark, 0, 0, 0, true);
        if (i === 0) {
          for (let pin = 0; pin < 18; pin += 1) addBox(layer, .095, .07, .29, metal, -1.95 + pin * .23, -.03, 1.74);
          for (const x of [-1.9, 1.9]) for (const z of [-1.2, 1.2]) addBox(layer, .16, .11, .16, pale, x, .09, z);
        } else if (i === 1) {
          for (const x of [-1.4, 1.4]) for (let z = -1; z <= 1; z += .5) addBox(layer, .44, .16, .3, dark, x, .1, z, true);
        } else if (i === 2) {
          addBox(layer, 1.45, .16, 1.45, metal, 0, .12, 0, true);
          for (let col = -2; col <= 2; col += 1) for (let row = -2; row <= 2; row += 1) addBox(layer, .14, .1, .14, lime, col * .21, .26, row * .21);
        } else {
          addBox(layer, 1.3, .2, 1.3, lime, 0, .14, 0, 'lime');
          addBox(layer, .95, .025, .95, pale, 0, .25, 0, true);
        }
      }
      const grid = new THREE.GridHelper(9, 18, 0x53644d, 0x26352c);
      grid.position.y = -1.75;
      grid.material.transparent = true;
      grid.material.opacity = .22;
      scene.add(grid);
      let paused = reduced.matches;
      let exploded = true;
      let rotation = -.35;
      let pointer = 0;
      let frame = 0;
      let previous = 0;
      let alive = true;
      const updateMotionLabel = () => { motionButton.textContent = paused ? 'Play' : 'Pause'; motionButton.setAttribute('aria-pressed', String(paused)); };
      updateMotionLabel();
      const render = (time = 0) => {
        frame = 0;
        if (!alive) return;
        const active = visible && !document.hidden;
        const dt = Math.min((time - previous) / 1000 || 0, .04);
        previous = time;
        if (!paused && active) rotation += dt * .075;
        study.rotation.y = rotation + pointer;
        let transitioning = false;
        for (const layer of layers) {
          const target = exploded ? layer.userData.open : layer.userData.closed;
          const delta = target - layer.position.y;
          if (reduced.matches || paused) layer.position.y = target;
          else { layer.position.y += delta * Math.min(1, dt * 9); transitioning ||= Math.abs(delta) > .002; }
        }
        renderer.render(scene, camera);
        if (active && (!paused || transitioning)) frame = requestAnimationFrame(render);
      };
      draw = () => { if (alive && !frame) frame = requestAnimationFrame(render); };
      const resize = new ResizeObserver(() => {
        const width = host.clientWidth;
        const height = host.clientHeight;
        if (!width || !height) return;
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.position.set(8.2, 7.1, 10.8);
        if (camera.aspect < 1.1) camera.position.multiplyScalar(1.15);
        camera.lookAt(0, .45, 0); camera.updateProjectionMatrix(); draw();
      });
      resize.observe(host);
      motionButton.addEventListener('click', () => { paused = !paused; updateMotionLabel(); draw(); });
      layoutButton.addEventListener('click', () => { exploded = !exploded; layoutButton.textContent = exploded ? 'Assemble' : 'Separate'; layoutButton.setAttribute('aria-pressed', String(exploded)); draw(); });
      host.addEventListener('pointermove', (event) => {
        if (reduced.matches || paused || event.pointerType === 'touch') return;
        const rect = host.getBoundingClientRect();
        pointer = ((event.clientX - rect.left) / rect.width - .5) * .16; draw();
      });
      host.addEventListener('pointerleave', () => { pointer = 0; draw(); });
      reduced.addEventListener('change', () => { paused = reduced.matches; updateMotionLabel(); draw(); });
      document.addEventListener('visibilitychange', draw);
      document.addEventListener('lab-theme', (event) => { grid.material.opacity = event.detail === 'light' ? .12 : .22; draw(); });
      const dispose = () => {
        if (!alive) return;
        alive = false; cancelAnimationFrame(frame); resize.disconnect(); observer.disconnect();
        scene.traverse((item) => { item.geometry?.dispose(); });
        for (const material of [metal, dark, pale, lime, edgeMaterial, limeEdge, grid.material]) material.dispose();
        renderer.dispose();
      };
      renderer.domElement.addEventListener('webglcontextlost', (event) => {
        event.preventDefault(); dispose(); renderer.domElement.remove(); fallback.hidden = false; controls.hidden = true;
      });
      window.addEventListener('pagehide', (event) => { if (!event.persisted) dispose(); });
      window.addEventListener('pageshow', () => { if (alive) draw(); });
      draw();
    } catch (error) {
      host.querySelector('canvas')?.remove();
      fallback.hidden = false; controls.hidden = true;
      console.info('The conceptual 3D study is unavailable; the static description remains visible.', error.message);
    }
  }, { rootMargin: '120px' });
  observer.observe(host);
}
