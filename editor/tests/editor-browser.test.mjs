/** @file Render the Bun-served editor against real, isolated bridge handlers. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { dirname, resolve } from "node:path";
import { createInterface } from "node:readline";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const EDITOR_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPOSITORY_ROOT = resolve(EDITOR_ROOT, "..");

/** Reserve and release a loopback port for the editor process. */
async function allocatePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const { port } = address;
  await new Promise((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
  return port;
}

/** Start the real Python bridge fixture and read its ephemeral listener ports. */
async function startBridge(origin) {
  const child = spawn("uv", ["run", "python", "tests/editor_bridge_fixture.py", origin], {
    cwd: REPOSITORY_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let diagnostics = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    diagnostics += chunk;
  });
  const lines = createInterface({ input: child.stdout });
  try {
    const [line] = await once(lines, "line", { signal: AbortSignal.timeout(15000) });
    return { child, ports: JSON.parse(line) };
  } catch (cause) {
    await stopChild(child);
    throw new Error(`Bridge fixture failed to publish ports: ${diagnostics}`, { cause });
  } finally {
    lines.close();
  }
}

/** Stop and reap only a child process owned by this test. */
async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = once(child, "exit");
  child.kill("SIGTERM");
  await exited;
}

/** Start the real editor server with the bridge fixture's discovered ports. */
async function startEditor(editorPort, bridgePorts) {
  const child = spawn("bun", ["run", "serve.ts"], {
    cwd: EDITOR_ROOT,
    env: {
      ...process.env,
      VOXELFORGE_EDITOR_PORT: String(editorPort),
      VOXELFORGE_BRIDGE_WS_PORT: String(bridgePorts.ws),
      VOXELFORGE_BRIDGE_HTTP_PORT: String(bridgePorts.http),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let diagnostics = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    diagnostics += chunk;
  });
  const lines = createInterface({ input: child.stdout });
  try {
    const [line] = await once(lines, "line", { signal: AbortSignal.timeout(15000) });
    const event = JSON.parse(line);
    assert.equal(event.event, "listening");
    assert.equal(event.port, editorPort);
    return child;
  } catch (cause) {
    await stopChild(child);
    throw new Error(`Bun editor failed to publish its port: ${diagnostics}`, { cause });
  } finally {
    lines.close();
  }
}

/** Wait for the visible count produced by a received scene snapshot. */
async function waitForCount(page, count) {
  await page.waitForFunction((expected) => {
    return document.querySelector("#scene-info")?.textContent?.includes(`· ${expected} voxels ·`);
  }, count);
}

/** Inspect the actual HTTP bridge state independently of the editor's DOM. */
async function snapshot(port) {
  const response = await fetch(`http://127.0.0.1:${port}/scene`);
  assert.equal(response.status, 200);
  return response.json();
}

/** Exercise clicked-layer removal and active-layer placement through actual canvas mouse events. */
async function exerciseEditing(page, ports) {
  await page.waitForFunction(
    () => document.querySelector("#status")?.textContent === "Bridge connected",
  );
  await waitForCount(page, 1);
  assert.equal(
    await page.locator(".swatch").count(),
    Object.keys((await snapshot(ports.http)).palette).length,
  );
  const initial = await snapshot(ports.http);
  assert.equal(initial.active_layer, 1);
  assert.deepEqual(initial.layers[0].blocks, [[0, 0, 0, "2"]]);

  // frameCamera aims the centre ray at the sole voxel; the HUD stays outside this point.
  await page.mouse.click(450, 350, { button: "right" });
  await waitForCount(page, 0);
  const removed = await snapshot(ports.http);
  assert.deepEqual(
    removed.layers.map((layer) => layer.blocks),
    [[], []],
  );
  assert.equal(removed.active_layer, 1);

  await page.locator('.swatch[title="2"]').click();
  await page.mouse.click(450, 350);
  await waitForCount(page, 1);
  const placed = await snapshot(ports.http);
  assert.deepEqual(placed.layers[0].blocks, []);
  assert.equal(placed.layers[1].blocks.length, 1);
  assert.equal(placed.layers[1].blocks[0][3], "2");
}

test("rendered editor loads and publishes layer-aware edits through the real bridge", {
  timeout: 40000,
}, async () => {
  const editorPort = await allocatePort();
  const origin = `http://127.0.0.1:${editorPort}`;
  let fixture;
  let editor;
  let browser;
  try {
    fixture = await startBridge(origin);
    editor = await startEditor(editorPort, fixture.ports);
    const configResponse = await fetch(`${origin}/bridge.json`);
    assert.equal(configResponse.status, 200);
    assert.deepEqual(await configResponse.json(), {
      wsUrl: `ws://127.0.0.1:${fixture.ports.ws}`,
      httpUrl: `http://127.0.0.1:${fixture.ports.http}`,
    });
    browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader"] });
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    const errors = [];
    const updates = [];
    const bridgeOrigin = new URL(`ws://127.0.0.1:${fixture.ports.ws}`).origin;
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("websocket", (socket) => {
      if (new URL(socket.url()).origin !== bridgeOrigin) return;
      socket.on("framereceived", ({ payload }) => updates.push(JSON.parse(String(payload))));
    });
    const initialResponse = page.waitForResponse(`http://127.0.0.1:${fixture.ports.http}/scene`);
    await page.goto(origin);
    assert.equal((await (await initialResponse).json()).name, "browser-regression");
    await exerciseEditing(page, fixture.ports);
    const counts = updates.map(({ scene }) =>
      scene.layers.reduce((sum, layer) => sum + layer.blocks.length, 0),
    );
    assert.ok(counts.includes(0), "removal must arrive as a real WebSocket scene update");
    assert.equal(counts.at(-1), 1, "placement must publish the restored scene");
    assert.deepEqual(errors, []);
  } finally {
    if (browser) await browser.close();
    if (editor) await stopChild(editor);
    if (fixture) await stopChild(fixture.child);
  }
});
