/**
 * @file Discover bridge endpoints and validate the editor's initial HTTP snapshot.
 *
 * Used by the editor at startup and reconnect. Failed discovery keeps the last
 * known endpoints, while failed snapshots leave scene recovery to WebSocket
 * updates. Results carry safe status messages without exposing payload contents.
 */
import { asSceneData } from "./scene-data";
import type { SceneData } from "./scene-data";

type BridgeConfig = { wsUrl: string; httpUrl: string };
type BridgeDiscovery = { config: BridgeConfig; warning: string };
type SceneSnapshot = { scene: SceneData | null; warning: string };

/** Fallback endpoints for a bridge on its standalone default ports. */
export const DEFAULT_BRIDGE: BridgeConfig = {
  wsUrl: "ws://127.0.0.1:8765",
  httpUrl: "http://127.0.0.1:8766",
};

/** Report whether a decoded payload carries both bridge endpoint URLs. */
function isBridgeConfig(payload: unknown): payload is BridgeConfig {
  if (typeof payload !== "object" || payload === null) return false;
  const record = payload as Record<string, unknown>;
  if (typeof record["wsUrl"] !== "string") return false;
  return typeof record["httpUrl"] === "string";
}

/**
 * Discover the bridge endpoints, retaining the last known endpoints on failure.
 * @param previous - Endpoints used when discovery is unavailable or invalid.
 * @returns Validated endpoints and a safe warning when discovery fails.
 * @example await loadBridgeConfig(DEFAULT_BRIDGE); // default ports if discovery fails
 */
export async function loadBridgeConfig(previous: BridgeConfig): Promise<BridgeDiscovery> {
  const fallback = {
    config: previous,
    warning: "Bridge discovery unavailable; using previous or default endpoints",
  };
  try {
    const res = await fetch("/bridge.json");
    if (!res.ok) return fallback;
    const payload: unknown = await res.json();
    if (!isBridgeConfig(payload)) return fallback;
    return { config: payload, warning: "" };
  } catch {
    return fallback;
  }
}

/**
 * Fetch a validated scene snapshot while allowing WebSocket recovery on failure.
 * @param httpUrl - Discovered or fallback HTTP bridge endpoint.
 * @returns The initial scene, or a safe warning explaining that it is unavailable.
 * @example await loadSceneSnapshot(DEFAULT_BRIDGE.httpUrl); // null scene if offline
 */
export async function loadSceneSnapshot(httpUrl: string): Promise<SceneSnapshot> {
  const fallback = {
    scene: null,
    warning: "Initial scene snapshot unavailable; waiting for bridge updates",
  };
  try {
    const res = await fetch(`${httpUrl}/scene`);
    if (!res.ok) return fallback;
    const payload: unknown = await res.json();
    const scene = asSceneData(payload);
    if (!scene) return fallback;
    return { scene, warning: "" };
  } catch {
    return fallback;
  }
}
