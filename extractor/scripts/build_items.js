const path = require("path");
const { spawnSync } = require("child_process");

// Global item bake — NOT wired into build_map.js on purpose, mirroring the
// existing outfit atlas (bake_outfit_atlas.py is also a standalone step, not
// called from build_map.js). Item baking (~2min on real data: ~1m30s atlas +
// ~25s sheets + ~10s index) is global, independent of which map is being
// built, so paying that cost on every single `npm run build-map` invocation
// (including repeated rebuilds of the same map during iteration) would be
// wasteful. Run this whenever items change or a new map introduces items not
// yet baked — see extractor/README.md's "new map" checklist.

const SCRIPTS_DIR = __dirname;

const STEPS = [
  "bake_item_atlas.py",
  "bake_item_sheets.py",
  "build_item_index.py",
];

function runStep(scriptName) {
  console.log(`\n=== ${scriptName} ===`);

  const result = spawnSync("python", [path.join(SCRIPTS_DIR, scriptName)], {
    cwd: SCRIPTS_DIR,
    stdio: "inherit",
  });

  if (result.status !== 0) {
    throw new Error(`${scriptName} falhou (exit ${result.status})`);
  }
}

function main() {
  for (const step of STEPS) {
    runStep(step);
  }
  console.log("\nDONE ✔ (item atlases + sheets + index atualizados)");
}

main();
