const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { dumpMap, resolveMapDir } = require("./dump_otbm.js");

const SCRIPTS_DIR = __dirname;
const EXTRACTOR_DIR = path.join(SCRIPTS_DIR, "..");
const MAPS_DIR = path.join(EXTRACTOR_DIR, "maps");
const FULL_MAPS_DIR = path.join(EXTRACTOR_DIR, "full-maps");

function discoverCities(root) {
  if (!fs.existsSync(root)) {
    return [];
  }
  return fs
    .readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

// Walks every city folder under maps/<CIDADE>/ automatically — adding a new
// city is purely a new folder, no code change here.
function discoverMapNames() {
  const names = [];
  for (const city of discoverCities(MAPS_DIR)) {
    const cityDir = path.join(MAPS_DIR, city);
    for (const entry of fs.readdirSync(cityDir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const mapDir = path.join(cityDir, entry.name);
      const hasOtbm = fs.readdirSync(mapDir).some((name) => name.endsWith(".otbm"));
      if (hasOtbm) {
        names.push(entry.name);
      }
    }
  }
  return names.sort();
}

// Full-city OTBMs (extractor/full-maps/<CIDADE>/) aren't included in --all —
// they feed the separate travel-graph pipeline, not the hunt-spot rotation —
// but are still reachable by name, same as any maps/<cidade>/<pasta> entry.
function mapExists(mapName) {
  return resolveMapDir(mapName) !== null;
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
    console.error("Uso: node build_map.js <nome-da-pasta-do-mapa>");
    console.error("     node build_map.js <CIDADE>          # mapa cidade-inteira (full-maps/<CIDADE>/)");
    console.error("     node build_map.js --all");
    process.exit(1);
  }

  const mapNames = arg === "--all" ? discoverMapNames() : [arg];

  if (mapNames.length === 0) {
    console.error(`Nenhum mapa encontrado em ${MAPS_DIR}`);
    process.exit(1);
  }

  if (arg !== "--all" && !mapExists(arg)) {
    const cities = Array.from(
      new Set([...discoverCities(MAPS_DIR), ...discoverCities(FULL_MAPS_DIR)])
    ).sort();
    console.error(
      `Mapa "${arg}" não encontrado em nenhuma cidade sob ${MAPS_DIR} nem em ${FULL_MAPS_DIR}.\n` +
      `Cidades disponíveis: ${cities.length ? cities.join(", ") : "(nenhuma)"}`
    );
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
