const fs = require("fs");
const path = require("path");

const otbm2json = require(path.join(__dirname, "..", "vendor", "otbm2json.js"));

const EXTRACTOR_DIR = path.join(__dirname, "..");
const MAPS_DIR = path.join(EXTRACTOR_DIR, "maps");
const FULL_MAPS_DIR = path.join(EXTRACTOR_DIR, "full-maps");

// Full-city OTBMs (extractor/full-maps/<name>/) feed the travel-graph
// pipeline instead of a single hunt spot (extractor/maps/<name>/) — same
// dump step, different source tree. maps/ is tried first so an ordinary
// hunt map name never accidentally resolves to a same-named full-city one.
function _sourceDir(mapName) {
  if (fs.existsSync(path.join(MAPS_DIR, mapName, `${mapName}.otbm`))) {
    return MAPS_DIR;
  }
  if (fs.existsSync(path.join(FULL_MAPS_DIR, mapName, `${mapName}.otbm`))) {
    return FULL_MAPS_DIR;
  }
  return MAPS_DIR;
}

function dumpMap(mapName) {
  const input = path.join(_sourceDir(mapName), mapName, `${mapName}.otbm`);
  const outputDir = path.join(EXTRACTOR_DIR, "raw-maps");
  const output = path.join(outputDir, `${mapName}.raw.json`);

  if (!fs.existsSync(input)) {
    throw new Error(`OTBM não encontrado: ${input}`);
  }

  fs.mkdirSync(outputDir, { recursive: true });

  const data = otbm2json.read(input);
  fs.writeFileSync(output, JSON.stringify(data, null, 2), "utf-8");

  console.log(`✔ ${mapName}.raw.json gerado`);
  return output;
}

module.exports = { dumpMap };

if (require.main === module) {
  const mapName = process.argv[2];
  if (!mapName) {
    console.error("Uso: node dump_otbm.js <nome-do-mapa>");
    process.exit(1);
  }
  dumpMap(mapName);
}
