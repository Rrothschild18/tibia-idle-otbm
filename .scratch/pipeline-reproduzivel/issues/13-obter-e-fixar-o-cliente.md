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

- [x] `extractor/assets-manifest.json`: tag do release, URL, sha256 do zip e do `assets.json.sha256`
- [x] `fetch-assets` baixa a tag fixada, confere os dois hashes e extrai só `packages/Tibia/assets/`
- [x] Checksum divergente → erro explícito de "cliente de versão diferente", não aviso
- [x] Trocar de versão de cliente é editar a tag no manifesto — em nenhum lugar mais
- [x] README documenta o caminho da máquina nova: `uv sync` → `fetch-assets` → `pipeline --all`

## Comments

`extractor/assets-manifest.json` + `extractor/scripts/fetch_assets.py`.

O manifesto fixa a tag, a URL, o sha256 do zip, o `assets.json.sha256`, a contagem de entradas do
catálogo e o nome do `.dat` de appearances. **Trocar de cliente é editar esse arquivo e nada mais** —
nenhum outro lugar do repo cita versão de cliente.

Os dois hashes não foram copiados do ticket: recalculei contra os arquivos reais nesta máquina.

```
da42a4ff5e3c1bc83c3bb6257a51f20e564c66a0ebb24ed21176a03905aa1d56  Tibia.15.25.0a00a0-original-linux.zip
4cbdf80eee33901f2eb4f3391e23ad02805b65890ca856efcd9c32c54888405a  assets.json.sha256
```

Rodado contra o cliente já baixado:

```
[OK] cliente 15.25.0a00a0 já presente e íntegro em /home/rroth/Projects/tibia-client
```

### Três conferências, não uma

O ticket pedia checksum. Coloquei três, porque cobrem falhas diferentes:

1. **sha256 do zip** — pega download corrompido ou release trocada.
2. **`assets.json.sha256`** — o mecanismo de integridade do próprio cliente. Pega **extração
   truncada**, que o hash do zip não pega, porque a essa altura o zip já foi apagado.
3. **contagem de entradas do catálogo** (4933) — pega um cliente que passasse pelas duas primeiras
   por acidente.

Todas erro, nenhuma aviso. A mensagem diz os dois hashes e manda editar o manifesto se a troca for
intencional.

### O `package.json` entrou no escopo por experiência própria

O `fetch-assets` extrai `packages/Tibia/` inteiro, não só `assets/`, e confere que o `package.json`
chegou. Isso não estava no ticket; entrou porque extrair só `assets/` foi exatamente o erro
cometido ao baixar o cliente à mão nesta sessão, e o RME recusa a pasta com *"The file package.json
is not present"* numa caixa cujo **título fala do `catalog-content.json`**. Custou uma sessão de
depuração; agora o fetch previne e o teste fixa.

`paths.py` ganhou `TIBIA_CLIENT` (`TIBIA_CLIENT_DIR`, default `../tibia-client`), mesma precedência
dos outros dois.

8 testes em `extractor/tests/test_fetch_assets.py`, todos nos caminhos de falha — checksum
divergente, catálogo de tamanho errado, `package.json` ausente, extração truncada — mais um que
valida o cliente real desta máquina e dá skip se não estiver baixado.

### O ponto em aberto continua aberto, de propósito

> Os 18 bundles publicados hoje vieram de um cliente de **versão desconhecida**. Fazer essa
> comparação **antes** de republicar tudo.

Isso é trabalho do ticket 07 (bundle regenerado vs. publicado) e só é verificável com os sprites
extraídos. O manifesto já dá a metade que faltava: a partir de agora a versão do cliente é
conhecida e fixada, então a próxima geração tem procedência mesmo que a anterior não tenha.
