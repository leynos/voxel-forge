/** @file Render the built editor against real, isolated HTTP and WebSocket bridge handlers. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, extname, resolve, sep } from "node:path";
import { createInterface } from "node:readline";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const EDITOR_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPOSITORY_ROOT = resolve(EDITOR_ROOT, "..");
const DIST_ROOT = resolve(EDITOR_ROOT, "dist");
const MIME_TYPES = new Map([
  [".html", "text/html"],
  [".js", "text/javascript"],
  [".css", "text/css"],
]);

/** Serve only the built editor, keeping test transport ports independent of local development. */
async function serveAsset(request, response) {
  const pathname = new URL(request.url, "http://localhost").pathname;
  const target = resolve(DIST_ROOT, `.${pathname === "/" ? "/index.html" : pathname}`);
  if (!target.startsWith(`${DIST_ROOT}${sep}`)) {
    response.writeHead(403).end();
    return;
  }
  try {
    const body = await readFile(target);
    response.writeHead(200, {
      "Content-Type": MIME_TYPES.get(extname(target)) ?? "application/octet-stream",
    });
    response.end(body);
  } catch {
    response.writeHead(404).end();
  }
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
    await stopBridge(child);
    throw new Error(`Bridge fixture failed to publish ports: ${diagnostics}`, { cause });
  } finally {
    lines.close();
  }
}

/** Stop and reap only the fixture process owned by this test. */
async function stopBridge(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = once(child, "exit");
  child.kill("SIGTERM");
  await exited;
}

/** Rewrite only the app's fixed bridge addresses; requests still use real browser networking. */
async function configureTransport(page, ports) {
  await page.addInitScript(({ http, ws }) => {
    const NativeWebSocket = window.WebSocket;
    window.WebSocket = class extends NativeWebSocket {
      constructor(url, protocols) {
        super(String(url).replace("127.0.0.1:8765", `127.0.0.1:${ws}`), protocols);
      }
    };
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, options) => {
      const redirected =
        typeof input === "string" ? input.replace("127.0.0.1:8766", `127.0.0.1:${http}`) : input;
      return nativeFetch(redirected, options);
    };
  }, ports);
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
  const staticServer = createServer(serveAsset);
  staticServer.listen(0, "127.0.0.1");
  await once(staticServer, "listening");
  const origin = `http://127.0.0.1:${staticServer.address().port}`;
  let fixture;
  let browser;
  try {
    fixture = await startBridge(origin);
    browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader"] });
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    const errors = [];
    const updates = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("websocket", (socket) => {
      socket.on("framereceived", ({ payload }) => updates.push(JSON.parse(String(payload))));
    });
    await configureTransport(page, fixture.ports);
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
    if (fixture) await stopBridge(fixture.child);
    await new Promise((done, reject) =>
      staticServer.close((error) => (error ? reject(error) : done())),
    );
  }
});
