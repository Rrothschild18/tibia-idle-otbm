const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { dumpMap } = require("./dump_otbm.js");

const SCRIPTS_DIR = __dirname;
const EXTRACTOR_DIR = path.join(SCRIPTS_DIR, "..");
const MAPS_DIR = path.join(EXTRACTOR_DIR, "maps");

function discoverMapNames() {
  return fs
    .readdirSync(MAPS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => fs.existsSync(path.join(MAPS_DIR, name, `${name}.otbm`)))
    .sort();
}

function buildMap(mapName) {
  console.log(`\n=== ${mapName} ===`);

  dumpMap(mapName);

  const result = spawnSync(
    "python",
    [path.join(SCRIPTS_DIR, "build_phaser_map.py"), mapName],
    { cwd: SCRIPTS_DIR, stdio: "inherit" }
  );

  if (result.status !== 0) {
    throw new Error(`build_phaser_map.py falhou para "${mapName}" (exit ${result.status})`);
  }
}

function main() {
  const arg = process.argv[2];

  if (!arg) {
    console.error("Uso: node build_map.js <nome-do-mapa>");
    console.error("     node build_map.js --all");
    process.exit(1);
  }

  const mapNames = arg === "--all" ? discoverMapNames() : [arg];

  if (mapNames.length === 0) {
    console.error(`Nenhum mapa encontrado em ${MAPS_DIR}`);
    process.exit(1);
  }

  const failures = [];

  for (const mapName of mapNames) {
    try {
      buildMap(mapName);
    } catch (err) {
      console.error(`[ERRO] ${mapName}: ${err.message}`);
      failures.push(mapName);
    }
  }

  console.log(`\n${mapNames.length - failures.length}/${mapNames.length} mapas gerados com sucesso.`);
  if (failures.length > 0) {
    console.log(`Falharam: ${failures.join(", ")}`);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
