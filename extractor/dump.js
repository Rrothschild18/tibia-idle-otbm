const fs = require("fs");
const path = require("path");

// ajuste o path se estiver usando o repo local clonado

const otbm2json = require("../otbm2json.js");

const INPUT = "./maps/dragon-darashia.otbm";
const OUTPUT = "./dragon-darashia.raw.json";

const data = otbm2json.read(INPUT);

fs.writeFileSync(
  OUTPUT,
  JSON.stringify(data, null, 2),
  "utf-8"
);

console.log("✔ dragon-dar.raw.json gerado");