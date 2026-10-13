/**
 * @file Browser voxel editor front end.
 *
 * Renders the scene held by the MCP bridge with three.js, keeps it in step over
 * the bridge WebSocket, and turns mouse input into placement and removal
 * requests. Responsibilities:
 *
 * - build instanced voxel meshes grouped by palette colour;
 * - frame the camera on the scene and render the palette strip;
 * - maintain the bridge connection, reconnecting when it drops;
 * - translate pointer events into grid cells and send edit messages.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { asSceneData, resolveRgb, sceneFromMessage } from "./scene-data";
import type { Block, SceneData } from "./scene-data";

const WS_URL = "ws://127.0.0.1:8765";
const BRIDGE_HTTP = "http://127.0.0.1:8766";
const RECONNECT_DELAY_MS = 2000;
/** Fraction of a voxel cell filled by its cube, leaving a visible seam. */
const VOXEL_GAP = 0.96;
/** `userData` key under which an instanced mesh records its source blocks. */
const USER_DATA_BLOCKS = "blocks";
const MOUSE_BUTTON = { LEFT: 0, MIDDLE: 1, RIGHT: 2 } as const;

type GridCell = { x: number; y: number; z: number };

type PickedVoxel = GridCell & {
  layer: number; color: string; normal: THREE.Vector3 | null };

type Bounds = { min: THREE.Vector3; max: THREE.Vector3 };

let sceneData: SceneData | null = null;
let activeColor = "1";
let ws: WebSocket | null = null;

/** Look up an element the page is required to provide, failing loudly if absent. */
function requireElement(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing required element #${id}`);
  return el;
}

/** Look up a required element and confirm it is a canvas. */
function requireCanvas(id: string): HTMLCanvasElement {
  const el = requireElement(id);
  if (!(el instanceof HTMLCanvasElement)) throw new Error(`Element #${id} is not a canvas`);
  return el;
}

const canvas = requireCanvas("canvas");
const statusEl = requireElement("status");
const sceneInfoEl = requireElement("scene-info");
const paletteEl = requireElement("palette");

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
// Left and right drags belong to the editor, so only the middle button orbits.
controls.mouseButtons = {
  LEFT: null,
  MIDDLE: THREE.MOUSE.ROTATE,
  RIGHT: null,
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

/** Edge length of one voxel in world units. */
function voxelSize(): number {
  return sceneData?.voxel_size ?? 1;
}

/** Centre of a grid cell in world space. */
function worldPos(gx: number, gy: number, gz: number): THREE.Vector3 {
  const vs = voxelSize();
  return new THREE.Vector3((gx + 0.5) * vs, (gy + 0.5) * vs, (gz + 0.5) * vs);
}

/** Release the GPU resources held by a mesh material. */
function disposeMaterial(material: THREE.Material | THREE.Material[]): void {
  if (!Array.isArray(material)) {
    material.dispose();
    return;
  }
  for (const entry of material) entry.dispose();
}

/** Empty the voxel group, disposing the geometry and materials it held. */
function disposeVoxelMeshes(): void {
  for (const child of voxelGroup.children) {
    if (!(child instanceof THREE.InstancedMesh)) continue;
    child.geometry.dispose();
    disposeMaterial(child.material);
  }
  voxelGroup.clear();
}

/** Bucket the blocks of every visible layer by their palette key. */
function groupBlocksByColour(blocks: readonly Block[]): Map<string, Block[]> {
  const byColour = new Map<string, Block[]>();
  for (const block of blocks) {
    const colour = block[3];
    const bucket = byColour.get(colour);
    if (bucket) bucket.push(block);
    else byColour.set(colour, [block]);
  }
  return byColour;
}

/** Build one instanced mesh holding every block of a single colour. */
function buildColourMesh(
  geometry: THREE.BoxGeometry,
  palette: Record<string, number[]>,
  colour: string,
  blocks: Block[],
  layerIndex: number,
): THREE.InstancedMesh {
  const material = new THREE.MeshStandardMaterial({
    color: resolveRgb(palette, colour),
    roughness: 0.85,
    metalness: 0.05,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, blocks.length);
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  const dummy = new THREE.Object3D();
  blocks.forEach(([x, y, z, c], i) => {
    dummy.position.copy(worldPos(x, y, z));
    dummy.updateMatrix();
    mesh.setMatrixAt(i, dummy.matrix);
    mesh.userData[`v_${i}`] = { x, y, z, color: c };
  });
  mesh.instanceMatrix.needsUpdate = true;
  mesh.userData[USER_DATA_BLOCKS] = blocks;
  mesh.userData["layer"] = layerIndex;
  return mesh;
}

/** Refresh the status line describing the scene, its size and active layer. */
function updateSceneInfo(data: SceneData, vs: number): void {
  const detail = vs < 1 ? `${Math.round(1 / vs)}x` : "1x";
  const layerName = data.layers[data.active_layer]?.name ?? "?";
  const count = countBlocks();
  const summary = `${data.name} · ${count} voxels · detail ${detail} · layer ${layerName}`;
  sceneInfoEl.textContent = `Scene: ${summary}`;
}

/** Rebuild every voxel mesh from the current scene and refresh the chrome. */
function rebuildVoxels(): void {
  disposeVoxelMeshes();
  const data = sceneData;
  if (!data) return;

  const vs = voxelSize();
  const box = vs * VOXEL_GAP;
  const baseGeo = new THREE.BoxGeometry(box, box, box);
  data.layers.forEach((layer, layerIndex) => {
    if (!layer.visible) return;
    for (const [colour, blocks] of groupBlocksByColour(layer.blocks)) {
      voxelGroup.add(buildColourMesh(baseGeo, data.palette, colour, blocks, layerIndex));
    }
  });

  frameCamera();
  updateSceneInfo(data, vs);
  renderPalette();
}

/** Grid-space bounding box of every block in the scene, visible or not. */
function sceneBounds(data: SceneData): Bounds {
  const min = new THREE.Vector3(Infinity, Infinity, Infinity);
  const max = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
  const point = new THREE.Vector3();
  for (const layer of data.layers) {
    for (const [x, y, z] of layer.blocks) {
      point.set(x, y, z);
      min.min(point);
      max.max(point);
    }
  }
  return { min, max };
}

/** Point the camera at the centre of the scene from a comfortable distance. */
function frameCamera(): void {
  const data = sceneData;
  if (!data) return;
  if (countBlocks() === 0) return;
  const vs = voxelSize();
  const { min, max } = sceneBounds(data);
  const cx = ((min.x + max.x + 1) / 2) * vs;
  const cy = ((min.y + max.y + 1) / 2) * vs;
  const cz = ((min.z + max.z + 1) / 2) * vs;
  const span = Math.max(max.x - min.x, max.y - min.y, max.z - min.z, 4) * vs;
  controls.target.set(cx, cy, cz);
  camera.position.set(cx + span * 1.4, cy + span * 1.1, cz + span * 1.4);
  controls.update();
}

/** Total number of blocks across the visible layers. */
function countBlocks(): number {
  if (!sceneData) return 0;
  return sceneData.layers.reduce((n, l) => n + (l.visible ? l.blocks.length : 0), 0);
}

/** Build one palette swatch that selects its colour when clicked. */
function createSwatch(key: string, rgb: number[]): HTMLDivElement {
  const sw = document.createElement("div");
  sw.className = key === activeColor ? "swatch active" : "swatch";
  sw.style.background = `rgb(${rgb.join(",")})`;
  sw.title = key;
  sw.onclick = () => {
    activeColor = key;
    renderPalette();
  };
  return sw;
}

/** Redraw the palette strip, highlighting the active colour. */
function renderPalette(): void {
  paletteEl.innerHTML = "";
  const data = sceneData;
  if (!data) return;
  for (const [key, rgb] of Object.entries(data.palette)) {
    paletteEl.appendChild(createSwatch(key, rgb));
  }
}

/** Open the bridge WebSocket, retrying whenever the connection drops. */
function connectWs(): void {
  const socket = new WebSocket(WS_URL);
  ws = socket;
  socket.onopen = () => {
    statusEl.textContent = "Bridge connected";
    socket.send(JSON.stringify({ type: "get_scene" }));
  };
  socket.onmessage = (ev: MessageEvent<string>) => {
    const payload: unknown = JSON.parse(ev.data);
    const scene = sceneFromMessage(payload);
    if (!scene) return;
    sceneData = scene;
    rebuildVoxels();
  };
  socket.onclose = () => {
    statusEl.textContent = "Bridge disconnected — retry in 2s";
    setTimeout(connectWs, RECONNECT_DELAY_MS);
  };
  socket.onerror = () => {
    statusEl.textContent = "Bridge error — start MCP server first";
  };
}

/** Seed the view from the bridge's HTTP snapshot, ignoring a bridge that is down. */
async function fetchInitialScene(): Promise<void> {
  try {
    const res = await fetch(`${BRIDGE_HTTP}/scene`);
    const payload: unknown = await res.json();
    const data = asSceneData(payload);
    if (!data) return;
    sceneData = data;
    rebuildVoxels();
  } catch {
    /* bridge not up yet */
  }
}

/** Aim the shared raycaster at the pointer position of a mouse event. */
function screenToRay(e: MouseEvent): void {
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
}

/** Block recorded at an instance index of a voxel mesh. */
function blockAt(mesh: THREE.InstancedMesh, index: number): Block | undefined {
  const blocks = mesh.userData[USER_DATA_BLOCKS] as Block[] | undefined;
  return blocks?.[index];
}

/** Voxel under the current ray, along with the normal of the face that was hit. */
function pickVoxel(): PickedVoxel | null {
  const hit = raycaster.intersectObjects(voxelGroup.children, false)[0];
  if (!hit) return null;
  const mesh = hit.object;
  if (!(mesh instanceof THREE.InstancedMesh)) return null;
  const block = blockAt(mesh, hit.instanceId ?? 0);
  if (!block) return null;
  const [x, y, z, color] = block;
  return { x, y, z, color, layer: Number(mesh.userData["layer"]), normal: hit.face?.normal ?? null };
}

/** Grid cell on the ground plane under the current ray. */
function groundCell(): GridCell | null {
  const target = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(plane, target)) return null;
  const vs = voxelSize();
  return { x: Math.floor(target.x / vs), y: 0, z: Math.floor(target.z / vs) };
}

/** Grid cell sitting against the hit face of a picked voxel. */
function adjacentCell(voxel: PickedVoxel): GridCell | null {
  const normal = voxel.normal;
  if (!normal) return null;
  const vs = voxelSize();
  const wx = (voxel.x + 0.5) * vs + Math.round(normal.x) * vs;
  const wy = (voxel.y + 0.5) * vs + Math.round(normal.y) * vs;
  const wz = (voxel.z + 0.5) * vs + Math.round(normal.z) * vs;
  return { x: Math.floor(wx / vs), y: Math.floor(wy / vs), z: Math.floor(wz / vs) };
}

/** Grid cell that a new voxel should occupy for the current ray. */
function placementCell(): GridCell | null {
  const voxel = pickVoxel();
  if (!voxel) return groundCell();
  return adjacentCell(voxel);
}

/** Ask the bridge to place a voxel of the active colour under the cursor. */
function placeVoxel(): void {
  const cell = placementCell();
  if (!cell) return;
  const message = { type: "editor_place", x: cell.x, y: cell.y, z: cell.z, color: activeColor };
  ws?.send(JSON.stringify(message));
}

/** Ask the bridge to remove the voxel under the cursor. */
function removeVoxel(): void {
  const voxel = pickVoxel();
  if (!voxel) return;
  const data = sceneData;
  if (!data) return;
  ws?.send(
    JSON.stringify({
      type: "editor_remove",
      x: voxel.x,
      y: voxel.y,
      z: voxel.z,
      scene_name: data.name,
      layer_index: voxel.layer,
      layer_index: data.active_layer,
    }),
  );
}

canvas.addEventListener("contextmenu", (e) => e.preventDefault());

canvas.addEventListener("mousedown", (e) => {
  if (e.button === MOUSE_BUTTON.MIDDLE) return;
  screenToRay(e);
  if (e.button === MOUSE_BUTTON.LEFT) {
    placeVoxel();
    return;
  }
  if (e.button === MOUSE_BUTTON.RIGHT) removeVoxel();
});

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

/** Drive the render loop. */
function animate(): void {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

fetchInitialScene();
connectWs();
animate();
