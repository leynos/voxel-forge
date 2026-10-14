/** @file Validate scene payload boundaries and colour grouping invariants. */
import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";
import * as sceneData from "../src/scene-data.ts";

/** Build a complete bridge snapshot without sharing mutable test state. */
function validScene() {
  return {
    name: "example",
    voxel_size: 1,
    palette: { red: [255, 0, 0] },
    active_layer: 0,
    layers: [{ name: "base", visible: true, blocks: [[-1, 2, 0, "red"]] }],
  };
}

/** Reject a payload through both HTTP and WebSocket scene boundaries. */
function assertRejected(payload) {
  assert.equal(sceneData.asSceneData(payload), null);
  assert.equal(sceneData.sceneFromMessage({ type: "scene_update", scene: payload }), null);
}

test("both scene boundaries retain complete valid snapshots", () => {
  const payload = validScene();
  assert.equal(sceneData.asSceneData(payload), payload);
  assert.equal(sceneData.sceneFromMessage({ type: "scene_update", scene: payload }), payload);
  delete payload.voxel_size;
  assert.equal(sceneData.asSceneData(payload), payload);
});

test("both scene boundaries reject malformed top-level fields", () => {
  for (const payload of [null, [], true, "scene", {}, { name: "incomplete" }]) {
    assertRejected(payload);
  }
  const invalidFields = {
    name: [null, 1, ""],
    palette: [
      null,
      [],
      "red",
      { red: [255, 0] },
      { red: [255, 0, "0"] },
      { red: [-1, 0, 0] },
      { red: [256, 0, 0] },
      { red: [0.5, 0, 0] },
    ],
    active_layer: [null, true, "0", 0.5, -1],
    layers: [null, {}, "base"],
    voxel_size: [null, "1", 0, -1, Number.NaN, Number.POSITIVE_INFINITY],
  };
  for (const [field, values] of Object.entries(invalidFields)) {
    for (const value of values) assertRejected({ ...validScene(), [field]: value });
  }
});

test("both scene boundaries reject malformed layer and block fields", () => {
  for (const layer of [null, [], {}, { name: "base", visible: true, blocks: "bad" }]) {
    assertRejected({ ...validScene(), layers: [layer] });
  }
  for (const [field, value] of [
    ["name", 3],
    ["visible", "false"],
    ["blocks", null],
  ]) {
    const payload = validScene();
    payload.layers[0][field] = value;
    assertRejected(payload);
  }
  for (const block of [
    null,
    {},
    [1, 2],
    [1, 2, 3, "red", 4],
    ["1", 2, 3, "red"],
    [1, 2, 3, 4],
    [true, 2, 3, "red"],
    [0.5, 2, 3, "red"],
    [Number.MAX_SAFE_INTEGER + 1, 2, 3, "red"],
    [Number.NaN, 2, 3, "red"],
    [1, Number.POSITIVE_INFINITY, 3, "red"],
  ]) {
    const payload = validScene();
    payload.layers[0].blocks = [block];
    assertRejected(payload);
  }
});

test("unrelated messages never become scene snapshots", () => {
  for (const payload of [null, [], {}, { type: "other", scene: validScene() }]) {
    assert.equal(sceneData.sceneFromMessage(payload), null);
  }
});

test("malformed serialized messages do not prevent the next valid update", () => {
  assert.equal(sceneData.sceneFromJson("{"), null);
  const payload = validScene();
  assert.deepEqual(
    sceneData.sceneFromJson(JSON.stringify({ type: "scene_update", scene: payload })),
    payload,
  );
  assert.equal(sceneData.sceneFromJson(JSON.stringify({ type: "scene_update", scene: {} })), null);
});

test("colour grouping retains every occurrence in input order within each colour", () => {
  const block = fc.tuple(fc.integer(), fc.integer(), fc.integer(), fc.string());
  fc.assert(
    fc.property(fc.array(block), (blocks) => {
      const grouped = sceneData.groupBlocksByColour(blocks);
      const colours = [...new Set(blocks.map((entry) => entry[3]))];
      assert.deepEqual([...grouped.keys()], colours);
      for (const colour of colours) {
        assert.deepEqual(
          grouped.get(colour),
          blocks.filter((entry) => entry[3] === colour),
        );
      }
      const occurrenceCount = [...grouped.values()].reduce(
        (total, bucket) => total + bucket.length,
        0,
      );
      assert.equal(occurrenceCount, blocks.length);
    }),
  );
  assert.equal(sceneData.groupBlocksByColour([]).size, 0);
});
