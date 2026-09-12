const fs = require("fs");
const path = require("path");

const REPO_DIR = path.join(__dirname, "..", "..");

/**
 * O interpretador Python que tem as deps do pipeline.
 *
 * Os runners spawnavam `"python"` cru, que resolvia por acaso via shim do mise
 * e quebrava diferente em cada máquina — e quebrou de vez quando as deps
 * passaram a viver na env do uv declarada em pyproject.toml.
 *
 * Precedência: $PYTHON > .venv/bin/python do repo > `uv run python`.
 */
function resolvePython() {
  if (process.env.PYTHON) {
    return { command: process.env.PYTHON, prefixArgs: [] };
  }

  const venvPython = path.join(REPO_DIR, ".venv", "bin", "python");
  if (fs.existsSync(venvPython)) {
    return { command: venvPython, prefixArgs: [] };
  }

  // Sem .venv, deixa o uv resolver (e criar, se preciso) a env do projeto.
  return { command: "uv", prefixArgs: ["run", "python"] };
}

/** Erro legível quando o interpretador não existe — antes virava ENOENT cru. */
function missingPythonError(python) {
  return new Error(
    `não encontrei o interpretador Python ("${python.command}"). ` +
      `Rode "uv sync" na raiz do repo, ou aponte PYTHON para um interpretador com Pillow e protobuf.`
  );
}

module.exports = { resolvePython, missingPythonError };
