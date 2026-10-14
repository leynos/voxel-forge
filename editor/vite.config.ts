/**
 * @file Vite configuration for the voxel editor front end.
 *
 * Serves `src/` from the editor directory and binds the dev server to the
 * loopback interface on the port the desktop shell and docs expect.
 */
import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  server: { port: 5173, host: "127.0.0.1" },
});
