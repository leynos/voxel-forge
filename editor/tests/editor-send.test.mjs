/**
 * @file Execute the editor's real edit handlers across WebSocket lifecycles.
 * Geometry is fixed so these tests isolate delivery rather than ray casting.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const source = readFileSync(new URL("../src/main.ts", import.meta.url), "utf8");
const syntax = ts.createSourceFile("main.ts", source, ts.ScriptTarget.Latest, true);
const handlers = syntax.statements.filter(
  (statement) =>
    ts.isFunctionDeclaration(statement) &&
    ["placeVoxel", "removeVoxel"].includes(statement.name?.text),
);
assert.equal(handlers.length, 2, "both production handlers must be exercised");
const { outputText } = ts.transpileModule(
  handlers.map((handler) => handler.getText(syntax)).join("\n"),
  { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
);

/** Execute one production handler with a controlled socket and picked voxel. */
function invokeHandler(handler, readyState) {
  const sent = [];
  const socket = {
    readyState,
    send(payload) {
      assert.equal(readyState, 1, "edits may only send on an OPEN socket");
      sent.push(JSON.parse(payload));
    },
  };
  runInNewContext(`${outputText}\n${handler}();`, {
    ws: readyState === null ? null : socket,
    WebSocket: { OPEN: 1 },
    activeColor: "2",
    sceneData: { name: "editor" },
    placementCell: () => ({ x: 1, y: 2, z: 3 }),
    pickVoxel: () => ({ x: 1, y: 2, z: 3, layer: 0 }),
  });
  return sent;
}

for (const handler of ["placeVoxel", "removeVoxel"]) {
  for (const [name, state] of [
    ["absent", null],
    ["CONNECTING", 0],
    ["CLOSING", 2],
    ["CLOSED", 3],
  ]) {
    test(`${handler} sends nothing while ${name}`, () => {
      assert.deepEqual(invokeHandler(handler, state), []);
    });
  }
  test(`${handler} sends the complete edit while OPEN`, () => {
    const expected =
      handler === "placeVoxel"
        ? { type: "editor_place", x: 1, y: 2, z: 3, color: "2" }
        : { type: "editor_remove", x: 1, y: 2, z: 3, scene_name: "editor", layer_index: 0 };
    assert.deepEqual(invokeHandler(handler, 1), [expected]);
  });
}
