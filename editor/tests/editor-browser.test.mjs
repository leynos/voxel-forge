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
    if (editorPort !== 0) assert.equal(event.port, editorPort);
    assert.ok(event.port > 0 && event.port <= 65535);
    child.editorPort = event.port;
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

for (const invalidPort of ["8765junk", "-1", "65536", "1.5", "", " 8765", "8765\n"]) {
  test(`Bun rejects invalid bridge ports ${JSON.stringify(invalidPort)} and preserves ephemeral editor binding`, async () => {
    const child = await startEditor(0, { ws: invalidPort, http: invalidPort });
    try {
      const response = await fetch(`http://127.0.0.1:${child.editorPort}/bridge.json`);
      assert.deepEqual(await response.json(), {
        wsUrl: "ws://127.0.0.1:8765",
        httpUrl: "http://127.0.0.1:8766",
      });
    } finally {
      await stopChild(child);
    }
  });
}

for (const validPort of ["0", "65535"]) {
  test(`Bun preserves valid bridge port boundary ${validPort}`, async () => {
    const child = await startEditor(0, { ws: validPort, http: validPort });
    try {
      const response = await fetch(`http://127.0.0.1:${child.editorPort}/bridge.json`);
      assert.deepEqual(await response.json(), {
        wsUrl: `ws://127.0.0.1:${validPort}`,
        httpUrl: `http://127.0.0.1:${validPort}`,
      });
    } finally {
      await stopChild(child);
    }
  });
}

for (const configResponse of [
  { status: 404, body: "not found" },
  { status: 200, contentType: "application/json", body: JSON.stringify({ wsUrl: 123 }) },
  { body: "network failure", abort: true },
]) {
  test(`editor starts with default bridge endpoints after discovery returns ${configResponse.body}`, {
    timeout: 40000,
  }, async () => {
    let editor;
    let browser;
    try {
      editor = await startEditor(0, { ws: 12345, http: 12346 });
      browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader"] });
      const page = await browser.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/bridge.json", (route) =>
        configResponse.abort ? route.abort() : route.fulfill(configResponse),
      );
      await page.route("http://127.0.0.1:8766/scene", (route) =>
        route.fulfill({
          status: 200,
          headers: { "access-control-allow-origin": "*" },
          contentType: "application/json",
          body: JSON.stringify({
            name: "fallback-scene",
            voxel_size: 1,
            active_layer: 0,
            palette: { 1: [255, 255, 255] },
            layers: [{ name: "base", visible: true, blocks: [[0, 0, 0, "1"]] }],
          }),
        }),
      );
      const websocket = page.waitForEvent("websocket", {
        predicate: (socket) => socket.url() === "ws://127.0.0.1:8765/",
      });
      await page.goto(`http://127.0.0.1:${editor.editorPort}`);
      await websocket;
      await waitForCount(page, 1);
      await page.waitForFunction(() =>
        document.querySelector("#status")?.textContent?.includes("Bridge discovery unavailable"),
      );
      assert.deepEqual(errors, []);
    } finally {
      if (browser) await browser.close();
      if (editor) await stopChild(editor);
    }
  });
}

test("editor rediscovers ephemeral bridge ports after a restart", { timeout: 40000 }, async () => {
  const editorPort = await allocatePort();
  const origin = `http://127.0.0.1:${editorPort}`;
  let fixture;
  let editor;
  let browser;
  try {
    fixture = await startBridge(origin);
    editor = await startEditor(editorPort, fixture.ports);
    browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader"] });
    const page = await browser.newPage();
    await page.route("**/bridge.json", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          wsUrl: `ws://127.0.0.1:${fixture.ports.ws}`,
          httpUrl: `http://127.0.0.1:${fixture.ports.http}`,
        }),
      }),
    );
    await page.goto(origin);
    await page.waitForFunction(
      () => document.querySelector("#status")?.textContent === "Bridge connected",
    );
    const oldFixture = fixture;
    fixture = await startBridge(origin);
    assert.notEqual(fixture.ports.ws, oldFixture.ports.ws);
    const websocket = page.waitForEvent("websocket", {
      predicate: (socket) => socket.url() === `ws://127.0.0.1:${fixture.ports.ws}/`,
    });
    const snapshotResponse = page.waitForResponse(`http://127.0.0.1:${fixture.ports.http}/scene`);
    await stopChild(oldFixture.child);
    await websocket;
    assert.equal((await snapshotResponse).status(), 200);
    await page.waitForFunction(
      () => document.querySelector("#status")?.textContent === "Bridge connected",
    );
  } finally {
    if (browser) await browser.close();
    if (editor) await stopChild(editor);
    if (fixture) await stopChild(fixture.child);
  }
});

for (const snapshotFailure of ["http", "payload", "network"]) {
  test(`editor reports initial scene snapshot ${snapshotFailure} failure while connecting`, {
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
      browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader"] });
      const page = await browser.newPage();
      await page.addInitScript(() => {
        window.bridgeStatusHistory = [];
        new MutationObserver(() => {
          const status = document.querySelector("#status")?.textContent;
          if (status) window.bridgeStatusHistory.push(status);
        }).observe(document, { childList: true, subtree: true, characterData: true });
      });
      await page.route(`http://127.0.0.1:${fixture.ports.http}/scene`, (route) => {
        if (snapshotFailure === "network") return route.abort();
        return route.fulfill({
          status: snapshotFailure === "http" ? 503 : 200,
          headers: { "access-control-allow-origin": "*" },
          contentType: "application/json",
          body: "{}",
        });
      });
      await page.goto(origin);
      await page.waitForFunction(() =>
        window.bridgeStatusHistory.some((status) =>
          status.includes("Initial scene snapshot unavailable"),
        ),
      );
      await waitForCount(page, 1);
      await page.waitForFunction(
        () => document.querySelector("#status")?.textContent === "Bridge connected",
      );
    } finally {
      if (browser) await browser.close();
      if (editor) await stopChild(editor);
      if (fixture) await stopChild(fixture.child);
    }
  });
}
