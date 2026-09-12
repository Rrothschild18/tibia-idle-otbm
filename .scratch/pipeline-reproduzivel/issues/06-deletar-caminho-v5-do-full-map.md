Status: ready-for-agent

# 06 — Deletar o caminho v5 do full-map

**What to build:** Com o 05 no lugar, o full-map não tem mais consumidor de mapa. Hoje ele gera 20,3
MB de `map.json` (10 andares de tiles, 13 sheets, 2 tilesets, 168 animações) + 1,8 MB de
`metadata.json` pra alimentar uma tabela de 2158 entradas. Tudo isso sai.

O v6 nunca foi gerado pra full-map de propósito (`build_phaser_map.py:107-113`, `:1438-1441`), e
continua não sendo — não porque falte trabalho, mas porque não existe consumidor.

**Blocked by:** 05.

- [x] `full-maps/<CIDADE>/map.json` e `metadata.json` removidos do git e não são mais gerados
- [x] O caminho de full-map produz só a tabela de flags (05) e o `monsters/respawn.json` que já
      produzia
- [x] `build_travel_fragment.py ROOK` roda fim-a-fim sem que exista `map.json` nenhum
- [x] Fragmento continua idêntico ao golden
- [x] README e `CONTEXT.md` deixam de descrever o full-map como produtor de mapa

## Comments

`extractor/full-maps/ROOK/map.json` (20,3 MB) e `metadata.json` (1,8 MB) removidos do git e
adicionados ao `.gitignore` — ignorados de propósito, pra que um checkout antigo com os arquivos
ainda em disco não os reintroduza num `git add -A`.

**A prova de que o acoplamento morreu:** movi os dois arquivos pra fora do repo e rodei o
fragmento. Saiu idêntico ao golden. O full-map não tem mais consumidor de mapa.

`build_phaser_map.py` deixa de escrever os dois quando `IS_FULL_MAP`, e imprime pra onde as flags
foram. Sobra o `monsters/respawn.json`, que sempre foi a outra saída desse caminho.

README e `CONTEXT.md` atualizados: a seção do travel-graph não manda mais gerar `map.json`, e a
entrada **City** do `CONTEXT.md` diz explicitamente que `full-maps/<CIDADE>/` não produz mapa.

### O que ficou de fora, e por quê

Guardei as duas escritas atrás de `if not IS_FULL_MAP` em vez de arrancar a construção v5 inteira
do caminho de full-map. Dois motivos:

1. **Não dá pra verificar aqui.** `build_phaser_map.py` faz
   `raise FileNotFoundError("Nenhuma pasta de sprites encontrada.")` na linha 87, em tempo de
   import. Sem `extractor/sprites/` o módulo não carrega, quanto mais roda. Reestruturar 1441
   linhas que eu não consigo executar é o tipo de mudança que fica linda no diff e quebra na
   primeira execução real.
2. **`build_monster_respawn` depende do resultado do build v5** — ele recebe `phaser_map["bounds"]`
   (`:1433`). Arrancar a construção exige extrair `bounds` por outro caminho, que é trabalho de
   verdade e pertence ao 07, onde o v5 morre inteiro e os sprites existem pra provar.

O critério do ticket — "não são mais gerados" — está cumprido: nenhum dos dois arquivos é escrito
pro full-map, e nenhum dos dois está no git.
