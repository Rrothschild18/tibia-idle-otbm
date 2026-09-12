Status: ready-for-agent

# 06 — Deletar o caminho v5 do full-map

**What to build:** Com o 05 no lugar, o full-map não tem mais consumidor de mapa. Hoje ele gera 20,3
MB de `map.json` (10 andares de tiles, 13 sheets, 2 tilesets, 168 animações) + 1,8 MB de
`metadata.json` pra alimentar uma tabela de 2158 entradas. Tudo isso sai.

O v6 nunca foi gerado pra full-map de propósito (`build_phaser_map.py:107-113`, `:1438-1441`), e
continua não sendo — não porque falte trabalho, mas porque não existe consumidor.

**Blocked by:** 05.

- [ ] `full-maps/<CIDADE>/map.json` e `metadata.json` removidos do git e não são mais gerados
- [ ] O caminho de full-map produz só a tabela de flags (05) e o `monsters/respawn.json` que já
      produzia
- [ ] `build_travel_fragment.py ROOK` roda fim-a-fim sem que exista `map.json` nenhum
- [ ] Fragmento continua idêntico ao golden
- [ ] README e `CONTEXT.md` deixam de descrever o full-map como produtor de mapa
