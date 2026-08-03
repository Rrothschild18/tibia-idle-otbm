# 01 — Documentar a convenção de pastas (cidade + id-na-pasta)

**What to build:** Atualizar `extractor/README.md` com a convenção definitiva de nomenclatura, antes
de qualquer código mudar (fundação de todos os tickets seguintes — todo o resto valida/aplica o que
este ticket documenta):

- `extractor/maps/<CIDADE>/<CIDADE-TIPO-SEQ>_nome-descritivo/` — ex:
  `extractor/maps/ROOK/ROOK-HUNT-0002_bears-rookguard/`. A cidade nunca é adivinhada do nome do mapa
  — é sempre a pasta-pai.
- `extractor/ready-maps/<CIDADE>/<mesmo-nome>/` — espelha `maps/` 1:1 (mesmo path relativo, raiz
  diferente).
- `extractor/full-maps/<CIDADE>/` — um mapa cidade-inteira por cidade, pasta = só o código da cidade
  (sem sufixo `-full`), conteúdo renomeado (`ROOK.otbm`, `ROOK-house.xml`, `ROOK-monster.xml`,
  `ROOK-npc.xml`, `ROOK-zones.xml`, `map.json` gerado no mesmo lugar).
- Mapas de teste/descartáveis (hoje `dragon-darashia`, `grim-reaper`, `larva-ankrah`, `sea-serpent`)
  moram sob a cidade fictícia `TEST` — mesmo mecanismo de pasta, sem sistema de tag separado.
- O id da subpasta de um hunt é redundante com a cidade-pai de propósito — permite copiar o mesmo
  texto da sign do editor de mapa direto pro nome da pasta, sem montar nada de cabeça.

**Blocked by:** None — pode começar imediatamente, é só documentação.

- [ ] `extractor/README.md` documenta a convenção `maps/<CIDADE>/<ID>_nome` com pelo menos um
      exemplo completo (cidade real + cidade `TEST`)
- [ ] Documenta que `ready-maps/`/`full-maps/` espelham a mesma lógica, com exemplos de path
      completo pra cada um
- [ ] Documenta que o id da pasta nunca é auto-gerado — é sempre escolhido à mão (mesmo texto da
      sign no editor de mapa)
- [ ] Documenta a cidade fictícia `TEST` pros mapas descartáveis, e que o front-end filtra por ela
- [ ] Nenhum código muda neste ticket — é preparação pros tickets 02-06 terem uma convenção escrita
      pra implementar contra
