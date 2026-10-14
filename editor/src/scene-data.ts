/**
 * @file Scene wire types, bridge payload selection, and palette colour lookup.
 *
 * Shared by HTTP/WebSocket loading and voxel/palette rendering. For example,
 * resolveRgb({ "2": [255, 0, 0] }, "2") returns the palette's red colour.
 */
import * as THREE from "three";

export type Block = [number, number, number, string];

export type SceneData = {
  name: string;
  voxel_size?: number;
  palette: Record<string, number[]>;
  active_layer: number;
  layers: Array<{
    name: string;
    visible: boolean;
    blocks: Block[];
  }>;
};

/** Build a colour from palette channel values, or null if any are missing. */
function colourFromChannels(channels: number[] | undefined): THREE.Color | null {
  const [r, g, b] = channels ?? [];
  if (r === undefined) return null;
  if (g === undefined) return null;
  if (b === undefined) return null;
  return new THREE.Color(r / 255, g / 255, b / 255);
}

/** Report whether a palette key is itself a six-digit hex literal. */
function isHexKey(key: string): boolean {
  if (!key.startsWith("#")) return false;
  return key.length === 7;
}

/**
 * Resolve a palette key to a colour, falling back to hex keys then to white.
 * @param palette - Palette keys mapped to RGB channel values.
 * @param key - Palette key or a six-digit hex colour literal.
 * @returns The palette colour, the hex colour, or white for an unknown key.
 * @example resolveRgb({ "2": [255, 0, 0] }, "2").getHexString(); // "ff0000"
 */
export function resolveRgb(palette: Record<string, number[]>, key: string): THREE.Color {
  const fromPalette = colourFromChannels(palette[key]);
  if (fromPalette) return fromPalette;
  if (isHexKey(key)) return new THREE.Color(key);
  return new THREE.Color(0xffffff);
}

/** Report whether a decoded payload is a plain object. */
function isRecord(payload: unknown): payload is Record<string, unknown> {
  if (typeof payload !== "object") return false;
  if (payload === null) return false;
  const prototype = Object.getPrototypeOf(payload);
  return prototype === Object.prototype || prototype === null;
}

/**
 * Extract the scene from a `scene_update` bridge message, if that is what it is.
 * @param payload - Decoded bridge message.
 * @returns Its scene reference, or null for a different or missing message.
 * @example sceneFromMessage({ type: "get_scene" }); // null
 */
export function sceneFromMessage(payload: unknown): SceneData | null {
  if (!isRecord(payload)) return null;
  const { type, scene } = payload;
  if (type !== "scene_update") return null;
  return asSceneData(scene);
}

/**
 * Decode a serialized bridge update, ignoring malformed or unrelated messages.
 * @param message - JSON text received from the bridge WebSocket.
 * @returns A validated scene, or null when decoding or validation fails.
 * @example sceneFromJson("{"); // null
 */
export function sceneFromJson(message: string): SceneData | null {
  try {
    const payload: unknown = JSON.parse(message);
    return sceneFromMessage(payload);
  } catch {
    return null;
  }
}

/** Report whether a decoded payload carries a non-empty `name` field. */
function hasNonEmptyName(payload: unknown): boolean {
  if (!isRecord(payload)) return false;
  const { name } = payload;
  return typeof name === "string" && name.length > 0;
}

/** Report whether one channel is an integer in the RGB byte range. */
function isRgbChannel(payload: unknown): boolean {
  if (!isInteger(payload)) return false;
  return payload >= 0 && payload <= 255;
}

/** Recognize finite numbers without coercing untrusted field values. */
function isFiniteNumber(payload: unknown): payload is number {
  return typeof payload === "number" && Number.isFinite(payload);
}

/** Recognize integral numeric fields shared by channels and layer indices. */
function isInteger(payload: unknown): payload is number {
  return isFiniteNumber(payload) && Number.isInteger(payload);
}

/** Recognize an array of the exact length required by a wire-format tuple. */
function isTuple(payload: unknown, length: number): payload is unknown[] {
  return Array.isArray(payload) && payload.length === length;
}

/** Validate every element of a collection at its scene boundary. */
function isArrayOf(payload: unknown, predicate: (value: unknown) => boolean): boolean {
  return Array.isArray(payload) && payload.every(predicate);
}

/** Report whether a palette colour contains exactly three RGB bytes. */
function isRgb(payload: unknown): boolean {
  return isTuple(payload, 3) && payload.every(isRgbChannel);
}

/** Validate the palette used by both rendering and colour selection. */
function isPalette(payload: unknown): boolean {
  if (!isRecord(payload)) return false;
  return Object.values(payload).every(isRgb);
}

/** Report whether a block has three safe grid coordinates and a colour key. */
function isBlock(payload: unknown): payload is Block {
  if (!isTuple(payload, 4)) return false;
  if (!payload.slice(0, 3).every(Number.isSafeInteger)) return false;
  return typeof payload[3] === "string";
}

/** Validate the fields consumed when rendering one layer's blocks. */
function isLayer(payload: unknown): boolean {
  if (!isRecord(payload)) return false;
  const { name, visible, blocks } = payload;
  if (typeof name !== "string") return false;
  if (typeof visible !== "boolean") return false;
  return isArrayOf(blocks, isBlock);
}

/** Report whether the selected layer index is a non-negative integer. */
function isActiveLayer(payload: unknown): boolean {
  return isInteger(payload) && payload >= 0;
}

/** Accept the optional voxel scale only when it is finite and positive. */
function isVoxelSize(payload: unknown): boolean {
  if (payload === undefined) return true;
  return isFiniteNumber(payload) && payload > 0;
}

/**
 * Validate the scene shape consumed by the editor's rendering boundary.
 * @param payload - An untrusted decoded HTTP or WebSocket scene.
 * @returns Whether all required fields and nested block rows are valid.
 * @example isSceneData({ name: "incomplete" }); // false
 */
export function isSceneData(payload: unknown): payload is SceneData {
  if (!isRecord(payload)) return false;
  if (!hasNonEmptyName(payload)) return false;
  const { palette, active_layer, voxel_size, layers } = payload;
  if (!isPalette(palette)) return false;
  if (!isActiveLayer(active_layer)) return false;
  if (!isVoxelSize(voxel_size)) return false;
  return isArrayOf(layers, isLayer);
}

/**
 * Validate a bridge payload before exposing it to editor rendering.
 * @param payload - Decoded HTTP scene response.
 * @returns Its scene reference, or null if its shape is invalid.
 * @example asSceneData({}); // null
 */
export function asSceneData(payload: unknown): SceneData | null {
  if (!isSceneData(payload)) return null;
  return payload;
}

/**
 * Bucket one layer's blocks by palette key, retaining that layer's identity.
 * @param blocks - Blocks of one visible layer, for example [[0, 0, 0, "2"]].
 * @returns Colour keys mapped to their source blocks in input order.
 * @example groupBlocksByColour([[0, 0, 0, "2"]]).get("2"); // [[0, 0, 0, "2"]]
 */
export function groupBlocksByColour(blocks: readonly Block[]): Map<string, Block[]> {
  const byColour = new Map<string, Block[]>();
  for (const block of blocks) {
    const colour = block[3];
    const bucket = byColour.get(colour);
    if (bucket) bucket.push(block);
    else byColour.set(colour, [block]);
  }
  return byColour;
}
