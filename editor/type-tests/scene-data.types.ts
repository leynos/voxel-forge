/** @file Compile-time contracts for scene types, narrowing, and strict access. */
import { isSceneData, sceneFromJson } from "../src/scene-data";
import type { Block, SceneData } from "../src/scene-data";

/** Require the expression to be assignable to the stated public type. */
function expectType<T>(value: T): void {
  void value;
}

const block: Block = [0, 0, 0, "1"];
const scene: SceneData = {
  name: "example",
  palette: { "1": [255, 255, 255] },
  active_layer: 0,
  layers: [{ name: "base", visible: true, blocks: [block] }],
};
const unknownColour = "missing";

expectType<number>(block[0]);
expectType<string>(block[3]);
expectType<SceneData>({ ...scene, voxel_size: 0.5 });

// @ts-expect-error -- A Block requires three coordinates and a colour key.
expectType<Block>([0, 0, 0]);
// @ts-expect-error -- A colour key is text, not a numeric palette index.
expectType<Block>([0, 0, 0, 1]);
// @ts-expect-error -- A scene must contain every required snapshot field.
expectType<SceneData>({ name: "incomplete" });
// @ts-expect-error -- exactOptionalPropertyTypes rejects explicit undefined.
expectType<SceneData>({ ...scene, voxel_size: undefined });
// @ts-expect-error -- noUncheckedIndexedAccess requires checking layer presence.
expectType<SceneData["layers"][number]>(scene.layers[0]);
// @ts-expect-error -- An unknown palette entry cannot supply an assured channel.
expectType<number>(scene.palette[unknownColour]?.[0]);
// @ts-expect-error -- Index-signature palette entries require bracket access.
void scene.palette.missing;

const firstLayer = scene.layers[0];
if (firstLayer) expectType<SceneData["layers"][number]>(firstLayer);

const payload: unknown = {};
// @ts-expect-error -- An untrusted payload must be narrowed by the scene guard.
expectType<SceneData>(payload);
if (isSceneData(payload)) expectType<SceneData>(payload);

const decoded = sceneFromJson("{}");
if (decoded) expectType<SceneData>(decoded);
