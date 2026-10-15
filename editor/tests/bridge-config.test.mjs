/** @file Property-test bridge discovery validation and endpoint selection. */
import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";
import { DEFAULT_BRIDGE, loadBridgeConfig } from "../src/bridge-config.ts";

/** Resolve bridge discovery against one generated JSON payload, without network I/O. */
async function discoverFromPayload(payload) {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify(payload), { status: 200 });
  try {
    return await loadBridgeConfig(DEFAULT_BRIDGE);
  } finally {
    globalThis.fetch = previousFetch;
  }
}

test("bridge discovery preserves generated WebSocket and HTTP endpoints", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.record({
        wsPort: fc.integer({ min: 1, max: 65535 }),
        httpPort: fc.integer({ min: 1, max: 65535 }),
      }),
      async ({ wsPort, httpPort }) => {
        const config = {
          wsUrl: `ws://127.0.0.1:${wsPort}`,
          httpUrl: `http://127.0.0.1:${httpPort}`,
        };

        assert.deepEqual(await discoverFromPayload(config), { config, warning: "" });
      },
    ),
  );
});

test("bridge discovery rejects generated non-string endpoints", async () => {
  const invalidEndpoint = fc.oneof(
    fc.boolean(),
    fc.integer(),
    fc.constant(null),
    fc.array(fc.integer()),
  );
  await fc.assert(
    fc.asyncProperty(invalidEndpoint, async (wsUrl) => {
      const result = await discoverFromPayload({ wsUrl, httpUrl: DEFAULT_BRIDGE.httpUrl });

      assert.deepEqual(result, {
        config: DEFAULT_BRIDGE,
        warning: "Bridge discovery unavailable; using previous or default endpoints",
      });
    }),
  );
});
