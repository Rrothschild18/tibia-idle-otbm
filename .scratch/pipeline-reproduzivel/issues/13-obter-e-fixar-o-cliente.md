Status: ready-for-agent

# 13 — Obter o cliente, fixar a versão, distribuir pro VPS

**What to build:** O ticket 08 troca o insumo de "quatro `.aec`" por "a pasta `assets/` de um cliente
Tibia". Ela continua sendo grande e não-versionável, então continua valendo o desenho do bucket: um
`fetch-assets` baixa de um bucket privado, confere contra um manifesto versionado, e falha alto
quando diverge.

O manifesto grava **a versão do cliente**, não só o checksum. O risco é específico e silencioso: um
cliente mais novo desloca ids de aparência, e o sintoma aparece seis estágios adiante como sprite
trocado — nunca como erro.

## Fonte confirmada

O docs do OpenTibiaBR não distribui cliente (o site são 5 páginas, nenhuma cita `assets/`), mas o
tutorial do OTClient aponta pra fonte real, e ela é **pública e imutável**:

    https://github.com/dudantas/tibia-client/releases/download/15.25.0a00a0/Tibia.15.25.0a00a0-original-linux.zip

- Tag `15.25.0a00a0` (2026-07-03), 403,5 MB, sha256
  `da42a4ff5e3c1bc83c3bb6257a51f20e564c66a0ebb24ed21176a03905aa1d56`
- Dentro: `packages/Tibia/assets/` (131 MB depois de extraído) com `catalog-content.json`,
  `appearances-<sha>.dat` e 4927 `sprites-<sha>.bmp.lzma`, mais `assets.json.sha256`
  (`4cbdf80eee33901f2eb4f3391e23ad02805b65890ca856efcd9c32c54888405a`), que é o próprio mecanismo de
  integridade do cliente
- Já baixado e extraído nesta máquina em `~/Projects/tibia-client/`

**Isso elimina o bucket privado.** Não há credencial, env var secreta nem infra: o `fetch-assets`
baixa uma URL pública de tag fixa e confere o sha256 que já está versionado no manifesto. A pasta do
cliente continua fora do git; qualquer clone a busca sozinho.

## Ponto em aberto

Os 18 bundles publicados hoje vieram de um cliente de **versão desconhecida**. Regenerar com o 15.25
é o caminho, mas a conferência do ticket 07 (bundle regenerado vs. publicado) é o que diz se algum id
de aparência se deslocou. Fazer essa comparação **antes** de republicar tudo.

- [ ] `extractor/assets-manifest.json`: tag do release, URL, sha256 do zip e do `assets.json.sha256`
- [ ] `fetch-assets` baixa a tag fixada, confere os dois hashes e extrai só `packages/Tibia/assets/`
- [ ] Checksum divergente → erro explícito de "cliente de versão diferente", não aviso
- [ ] Trocar de versão de cliente é editar a tag no manifesto — em nenhum lugar mais
- [ ] README documenta o caminho da máquina nova: `uv sync` → `fetch-assets` → `pipeline --all`
