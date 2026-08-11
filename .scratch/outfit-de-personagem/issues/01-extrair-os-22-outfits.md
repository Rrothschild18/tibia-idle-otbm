Status: ready-for-agent

# 01 — Extrair os 22 outfits de jogador

**What to build:** `extract_sprites.py` passa a extrair os 22 outfits de jogador, e o critério de
exclusão passa a nomear o eixo em vez da contagem.

Hoje `outfit_has_addons_or_mounts` (linha 104) devolve `True` para qualquer appearance com
`pattern_height > 1`, `pattern_depth > 1` **ou** `layers > 1`, e o chamador a usa como "pula".
Os 22 ids batem nos três. Duas coisas mudam:

1. **A pergunta.** Em vez de "esse outfit tem eixos demais?", o extractor pergunta "esse outfit é
   de jogador?" — a lista dos 22 ids é conhecida e finita (128–134, 136–150; o 135 não existe).
   Outfits de criatura continuam saindo pelo caminho de hoje, sem mudança de formato.
2. **A saída dos 22.** Eles precisam dos frames de todos os eixos menos montaria, e do JSON
   declarando quais eixos existem — `{directions: 4, phases: 9, layers: 2, addons: 3, mounts: 1}`.
   Sem esse bloco, o consumidor deduz os eixos da contagem de frames, que é exatamente o hábito
   que produziu a documentação errada.

A lei de índice, agora documentada em `OUTFIT_SPRITES_DOCUMENTATION.md`:

```
index = ((((fase * numZ + z) * numY + y) * numX + x) * layers) + layer
```

O eixo que varia mais rápido é `layer`, o mais lento é `fase` — os frames vêm **intercalados por
direção**, nunca agrupados. Direções: `0=norte, 1=leste, 2=sul, 3=oeste`.

**Blocked by:** nada.

- [ ] Uma função `frame_index(fase, z, y, x, layer)` existe, é pura, e tem teste direto: total de
      432 para os eixos de jogador, `frame_index(0,0,0,2,0) == 4`, e máscara sempre em índice ímpar
- [ ] Os 22 ids extraem; nenhum outfit de criatura muda de saída (conferir contagem de arquivos em
      `sprites/outfits/` antes e depois)
- [ ] O JSON por outfit de jogador declara o bloco `axes`
- [ ] `outfit_has_addons_or_mounts` ou some ou passa a nomear o eixo; o docstring não pode mais
      descrever o corte como "sprite count inflado"
- [ ] Um humano olha o frame `south` de pelo menos um dos 22 e confirma que é a pessoa certa
