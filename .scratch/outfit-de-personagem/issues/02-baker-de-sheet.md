Status: ready-for-agent

# 02 — Baker de sheet de outfit de personagem

**What to build:** Um script Python dedicado que consome os frames já extraídos pela ticket 01 e
produz, por outfit, um PNG e um JSON. Mesmo corte de responsabilidade que `bake_outfit_atlas.py`
já usa para criaturas: decodificar o `.aec` e empacotar são coisas separadas e testáveis
separadamente.

**Layout.** 216 frames — `4 direções × 3 addons × 2 layers × 9 fases`, montaria descartada —,
células de 64×64 com 1px de padding, grade de 24 colunas. Sai 1561×586px, ~92 KB por outfit,
2,28 MB nos 22. Ordem de empacotamento é a lei de índice, para que a posição na grade seja
previsível a olho.

**Chave de frame**, e este é o ponto da ticket:

```
<outfitId>_<layer>_a<addon>_<direção>_<fase>      ex.: 128_mask_a0_north_2
```

`layer` ∈ `base|mask`, `direção` ∈ `north|east|south|west`. É deliberadamente diferente do
`<id>_<n>` numérico dos atlases de criatura. O motivo está na nota de correção do topo de
`OUTFIT_SPRITES_DOCUMENTATION.md`: a lei de índice ficou errada num `.md` por muito tempo porque
uma chave numérica não denuncia nada — `128_17` está igualmente calado se o índice foi somado
errado, e `128_mask_a0_north_2` não está.

O JSON carrega `frames`, o bloco `axes` e o `meta` no formato que o Phaser lê direto:

```json
{
  "frames": { "128_base_a0_north_0": { "frame": { "x": 1, "y": 1, "w": 64, "h": 64 } } },
  "axes": { "directions": 4, "phases": 9, "layers": 2, "addons": 3, "mounts": 1 },
  "meta": { "image": "128.png", "size": { "w": 1561, "h": 586 } }
}
```

**Blocked by:** `01-extrair-os-22-outfits.md`.

- [ ] Função pura empacotadora — recebe lista de (chave, PNG), devolve `(imagem, mapeamento)` —
      testada com fixtures PIL em `tmp_path`, no estilo de `tests/test_render_baked_row.py`
- [ ] Os 22 sheets geram; um deles conferido a olho contra a grade documentada
- [ ] Duas execuções sobre a mesma entrada produzem PNG e JSON idênticos byte a byte
- [ ] O JSON declara `axes` com `mounts: 1`, e nenhum frame de `z=1` entrou no sheet
- [ ] Nenhum atlas de criatura existente muda — o baker novo não toca `bake_outfit_atlas.py`
