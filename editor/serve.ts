/**
 * @file Bun entry point for the VoxelForge web editor.
 *
 * Serves the Three.js editor as a bundled single-page application and
 * reports the port it actually bound as a structured JSON event on
 * stdout, so a supervising process can discover it. Bridge endpoints
 * are passed in through environment variables and republished to the
 * page at `/bridge.json`.
 */
import indexHtml from "./index.html";

/** Read a port number from the environment, falling back when unset. */
function envPort(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}

const requestedPort = envPort("VOXELFORGE_EDITOR_PORT", 0);
const bridgeWsPort = envPort("VOXELFORGE_BRIDGE_WS_PORT", 8765);
const bridgeHttpPort = envPort("VOXELFORGE_BRIDGE_HTTP_PORT", 8766);

const server = Bun.serve({
  hostname: "127.0.0.1",
  port: requestedPort,
  routes: {
    "/": indexHtml,
    "/bridge.json": () =>
      Response.json({
        wsUrl: `ws://127.0.0.1:${bridgeWsPort}`,
        httpUrl: `http://127.0.0.1:${bridgeHttpPort}`,
      }),
  },
});

console.log(JSON.stringify({ event: "listening", port: server.port }));
