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
  return payload !== null;
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
  if (!scene) return null;
  return scene as SceneData;
}

/** Report whether a decoded payload carries a non-empty `name` field. */
function hasNonEmptyName(payload: unknown): boolean {
  if (!isRecord(payload)) return false;
  const { name } = payload;
  if (typeof name !== "string") return false;
  return name.length > 0;
}

/**
 * Reinterpret a named bridge payload as scene data, trusting the bridge for the shape.
 * @param payload - Decoded HTTP scene response.
 * @returns A named scene reference, or null if the response has no scene name.
 * @example asSceneData({}); // null
 */
export function asSceneData(payload: unknown): SceneData | null {
  if (!hasNonEmptyName(payload)) return null;
  return payload as SceneData;
}

/**
 * Bucket one layer's blocks by palette key, retaining that layer's identity.
 * @param blocks - Blocks of one visible layer, for example [[0, 0, 0, "2"]].
 * @returns Colour keys mapped to their source blocks in input order.
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
