import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const WS_URL = "ws://127.0.0.1:8765";
const BRIDGE_HTTP = "http://127.0.0.1:8766";

type SceneData = {
  name: string;
  voxel_size?: number;
  palette: Record<string, number[]>;
  active_layer: number;
  layers: Array<{
    name: string;
    visible: boolean;
    blocks: [number, number, number, string][];
  }>;
};

let sceneData: SceneData | null = null;
let activeColor = "1";
let ws: WebSocket | null = null;

const canvas = document.getElementById("canvas") as HTMLCanvasElement;
const statusEl = document.getElementById("status")!;
const sceneInfoEl = document.getElementById("scene-info")!;
const paletteEl = document.getElementById("palette")!;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x1a1a2e);
renderer.shadowMap.enabled = true;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.05, 500);
camera.position.set(10, 10, 10);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.mouseButtons = {
  LEFT: null as unknown as THREE.MOUSE,
  MIDDLE: THREE.MOUSE.ROTATE,
  RIGHT: null as unknown as THREE.MOUSE,
};

const ambient = new THREE.AmbientLight(0xffffff, 0.45);
scene.add(ambient);
const dir = new THREE.DirectionalLight(0xffffff, 1.0);
dir.position.set(12, 24, 10);
dir.castShadow = true;
scene.add(dir);
const fill = new THREE.DirectionalLight(0x8899ff, 0.25);
fill.position.set(-8, 6, -6);
scene.add(fill);

const grid = new THREE.GridHelper(32, 32, 0x444466, 0x333355);
scene.add(grid);

const voxelGroup = new THREE.Group();
scene.add(voxelGroup);

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

function voxelSize(): number {
  return sceneData?.voxel_size ?? 1;
}

function resolveRgb(palette: Record<string, number[]>, key: string): THREE.Color {
  const p = palette[key];
  if (p) return new THREE.Color(p[0] / 255, p[1] / 255, p[2] / 255);
  if (key.startsWith("#") && key.length === 7) {
    return new THREE.Color(key);
  }
  return new THREE.Color(0xffffff);
}

function worldPos(gx: number, gy: number, gz: number): THREE.Vector3 {
  const vs = voxelSize();
  return new THREE.Vector3((gx + 0.5) * vs, (gy + 0.5) * vs, (gz + 0.5) * vs);
}

function rebuildVoxels() {
  while (voxelGroup.children.length) {
    const c = voxelGroup.children[0];
    voxelGroup.remove(c);
    if (c instanceof THREE.InstancedMesh) {
      c.geometry.dispose();
      (c.material as THREE.Material).dispose();
    }
  }
  if (!sceneData) return;

  const vs = voxelSize();
  const gap = 0.96;
  const box = vs * gap;
  const baseGeo = new THREE.BoxGeometry(box, box, box);

  // Layers stay separate so each rendered voxel remembers the layer it came
  // from. Merging them by colour loses that identity, which made an editor
  // removal target the active layer instead of the layer actually clicked.
  const visibleLayers: Array<[number, [number, number, number, string][]]> = [];
  sceneData.layers.forEach((layer, layerIndex) => {
    if (layer.visible) {
      visibleLayers.push([layerIndex, layer.blocks]);
    }
  });

  const dummy = new THREE.Object3D();
  for (const layerEntry of visibleLayers) {
    const layerIndex = layerEntry[0];
    const blocks = layerEntry[1];
    const byColor = new Map<string, Array<[number, number, number, string]>>();
    for (const block of blocks) {
      const [x, y, z, color] = block;
      if (!byColor.has(color)) byColor.set(color, []);
      byColor.get(color)!.push([x, y, z, color]);
    }

    for (const colourEntry of Array.from(byColor.entries())) {
      const color = colourEntry[0];
      const colourBlocks = colourEntry[1];
      const mat = new THREE.MeshStandardMaterial({
        color: resolveRgb(sceneData.palette, color),
        roughness: 0.85,
        metalness: 0.05,
      });
      const mesh = new THREE.InstancedMesh(baseGeo, mat, colourBlocks.length);
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      colourBlocks.forEach(([x, y, z, c], i) => {
        const p = worldPos(x, y, z);
        dummy.position.copy(p);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
        mesh.userData[`v_${i}`] = { x, y, z, color: c, layer: layerIndex };
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.userData.blocks = colourBlocks;
      mesh.userData.layer = layerIndex;
      voxelGroup.add(mesh);
    }
  }

  frameCamera();
  const res = vs < 1 ? `${Math.round(1 / vs)}x` : "1x";
  sceneInfoEl.textContent =
    `Scene: ${sceneData.name} · ${countBlocks()} voxels · detail ${res} · layer ${sceneData.layers[sceneData.active_layer]?.name ?? "?"}`;
  renderPalette();
}

function frameCamera() {
  if (!sceneData || countBlocks() === 0) return;
  const vs = voxelSize();
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (const layer of sceneData.layers) {
    for (const [x, y, z] of layer.blocks) {
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      minZ = Math.min(minZ, z);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
      maxZ = Math.max(maxZ, z);
    }
  }
  const cx = ((minX + maxX + 1) / 2) * vs;
  const cy = ((minY + maxY + 1) / 2) * vs;
  const cz = ((minZ + maxZ + 1) / 2) * vs;
  const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 4) * vs;
  controls.target.set(cx, cy, cz);
  camera.position.set(cx + span * 1.4, cy + span * 1.1, cz + span * 1.4);
  controls.update();
}

function countBlocks(): number {
  if (!sceneData) return 0;
  return sceneData.layers.reduce((n, l) => n + (l.visible ? l.blocks.length : 0), 0);
}

function renderPalette() {
  paletteEl.innerHTML = "";
  if (!sceneData) return;
  for (const [key, rgb] of Object.entries(sceneData.palette)) {
    const sw = document.createElement("div");
    sw.className = "swatch" + (key === activeColor ? " active" : "");
    sw.style.background = `rgb(${rgb.join(",")})`;
    sw.title = key;
    sw.onclick = () => {
      activeColor = key;
      renderPalette();
    };
    paletteEl.appendChild(sw);
  }
}

function connectWs() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    statusEl.textContent = "Bridge connected";
    ws!.send(JSON.stringify({ type: "get_scene" }));
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "scene_update" && msg.scene) {
      sceneData = msg.scene as SceneData;
      rebuildVoxels();
    }
  };
  ws.onclose = () => {
    statusEl.textContent = "Bridge disconnected — retry in 2s";
    setTimeout(connectWs, 2000);
  };
  ws.onerror = () => {
    statusEl.textContent = "Bridge error — start MCP server first";
  };
}

async function fetchInitialScene() {
  try {
    const res = await fetch(`${BRIDGE_HTTP}/scene`);
    const data = await res.json();
    if (data.name) {
      sceneData = data as SceneData;
      rebuildVoxels();
    }
  } catch {
    /* bridge not up yet */
  }
}

function screenToRay(e: MouseEvent) {
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
}

function pickVoxel(): { x: number; y: number; z: number; color: string; layer: number } | null {
  const hits = raycaster.intersectObjects(voxelGroup.children, false);
  if (!hits.length) return null;
  const hit = hits[0];
  const mesh = hit.object as THREE.InstancedMesh;
  const idx = hit.instanceId ?? 0;
  const blocks = mesh.userData.blocks as [number, number, number, string][];
  const layer = (mesh.userData.layer as number | undefined) ?? 0;
  if (blocks && blocks[idx]) {
    const [x, y, z, color] = blocks[idx];
    return { x, y, z, color, layer };
  }
  return null;
}

function pickGround(): THREE.Vector3 | null {
  const target = new THREE.Vector3();
  if (raycaster.ray.intersectPlane(plane, target)) {
    return target;
  }
  return null;
}

// Sending on a CONNECTING socket throws, which would surface as a silent lost
// edit rather than the offline state the status bar already reports.
function sendToBridge(message: unknown) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

canvas.addEventListener("contextmenu", (e) => e.preventDefault());

canvas.addEventListener("mousedown", (e) => {
  if (e.button === 1) return;
  screenToRay(e);
  const vs = voxelSize();

  if (e.button === 0) {
    const hit = pickVoxel();
    let x: number, y: number, z: number;
    if (hit) {
      const n = raycaster.intersectObjects(voxelGroup.children, false)[0].face!.normal;
      const wx = (hit.x + 0.5) * vs + Math.round(n.x) * vs;
      const wy = (hit.y + 0.5) * vs + Math.round(n.y) * vs;
      const wz = (hit.z + 0.5) * vs + Math.round(n.z) * vs;
      x = Math.floor(wx / vs);
      y = Math.floor(wy / vs);
      z = Math.floor(wz / vs);
    } else {
      const g = pickGround();
      if (!g) return;
      x = Math.floor(g.x / vs);
      y = 0;
      z = Math.floor(g.z / vs);
    }
    sendToBridge({ type: "editor_place", x, y, z, color: activeColor });
  } else if (e.button === 2) {
    const hit = pickVoxel();
    if (hit && sceneData) {
      sendToBridge({
        type: "editor_remove",
        x: hit.x,
        y: hit.y,
        z: hit.z,
        scene_name: sceneData.name,
        layer_index: hit.layer,
      });
    }
  }
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

fetchInitialScene();
connectWs();
animate();
