const fs = require("fs");
const path = require("path");

const otbm2json = require(path.join(__dirname, "..", "vendor", "otbm2json.js"));

const EXTRACTOR_DIR = path.join(__dirname, "..");
const MAPS_DIR = path.join(EXTRACTOR_DIR, "maps");
const FULL_MAPS_DIR = path.join(EXTRACTOR_DIR, "full-maps");

// Every hunt map lives two levels deep — maps/<CIDADE>/<pasta>/ — the city
// is always the physical parent folder, never guessed from the map's own
// name (see extractor/README.md, "Convenção de pastas"). A full-city OTBM
// is one level deep instead: full-maps/<CIDADE>/, folder = city code.
function _findTwoLevelDir(root, mapName) {
  if (!fs.existsSync(root)) {
    return null;
  }
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const candidate = path.join(root, entry.name, mapName);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
      return candidate;
    }
  }
  return null;
}

// maps/ is tried first so an ordinary hunt map name never accidentally
// resolves to a same-named full-city one.
function resolveMapDir(mapName) {
  const hunt = _findTwoLevelDir(MAPS_DIR, mapName);
  if (hunt) {
    return hunt;
  }
  const fullCity = path.join(FULL_MAPS_DIR, mapName);
  if (fs.existsSync(fullCity) && fs.statSync(fullCity).isDirectory()) {
    return fullCity;
  }
  return null;
}

// A hunt map's folder name carries its id (`<ID>_nome-descritivo`) and is
// deliberately NOT required to match the .otbm's own basename inside it —
// only the folder is authoritative. Exactly one .otbm is expected per
// folder; the first (sorted) match is used.
function _findOtbmFile(mapDir) {
  const match = fs
    .readdirSync(mapDir)
    .filter((name) => name.endsWith(".otbm"))
    .sort();
  return match.length ? path.join(mapDir, match[0]) : null;
}

function dumpMap(mapName) {
  const mapDir = resolveMapDir(mapName);
  if (!mapDir) {
    throw new Error(`Mapa "${mapName}" não encontrado em ${MAPS_DIR} nem em ${FULL_MAPS_DIR}`);
  }

  const input = _findOtbmFile(mapDir);
  if (!input) {
    throw new Error(`Nenhum arquivo .otbm encontrado em ${mapDir}`);
  }

  const outputDir = path.join(EXTRACTOR_DIR, "raw-maps");
  const output = path.join(outputDir, `${mapName}.raw.json`);

  fs.mkdirSync(outputDir, { recursive: true });

  const data = otbm2json.read(input);
  fs.writeFileSync(output, JSON.stringify(data, null, 2), "utf-8");

  console.log(`✔ ${mapName}.raw.json gerado`);
  return output;
}

module.exports = { dumpMap, resolveMapDir };

if (require.main === module) {
  const mapName = process.argv[2];
  if (!mapName) {
    console.error("Uso: node dump_otbm.js <nome-do-mapa>");
    process.exit(1);
  }
  dumpMap(mapName);
}
