const fs = require("fs");
const path = require("path");

const otbm2json = require(path.join(__dirname, "..", "vendor", "otbm2json.js"));

const EXTRACTOR_DIR = path.join(__dirname, "..");

function dumpMap(mapName) {
  const input = path.join(EXTRACTOR_DIR, "maps", mapName, `${mapName}.otbm`);
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
