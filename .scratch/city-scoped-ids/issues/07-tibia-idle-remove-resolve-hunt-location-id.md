# 07 — `tibia-idle`: remover `resolveHuntLocationId`, hunt/location resolvem por id idêntico

**What to build:** Repo `tibia-idle`. Com `hunt.mapId === location.id` sempre verdadeiro (garantido
pelo pipeline do extractor, ticket 04/06), `resolveHuntLocationId`
(`libs/data-access/src/lib/locations/resolve-hunt-location-id.ts`) fica sem propósito — qualquer
código que hoje chama essa função pra achar a location de um hunt passa a usar `hunt.mapId`
diretamente como o id da location. `getHuntTravelTimeMs`
(`libs/data-access/src/lib/locations/travel-time.ts`) perde o parâmetro `locations`/a chamada a
`resolveHuntLocationId` — vira só `findTileCount(edges, currentLocationId, hunt.mapId, level)`.

**Blocked by:** 06 (`tibia-idle-otbm`) — precisa que `db.json` já tenha os ids no formato novo, senão
essa mudança quebra o travel-time pros 9 hunts que hoje só resolvem via derivação.

- [ ] `resolveHuntLocationId` e seu arquivo (`resolve-hunt-location-id.ts`) removidos, junto do teste
      correspondente
- [ ] `getHuntTravelTimeMs` simplificado — não recebe mais `locations`, usa `hunt.mapId` direto
- [ ] `HuntsWindow` (e qualquer outro consumidor) atualizado pra nova assinatura
- [ ] Teste de `getHuntTravelTimeMs` cobre resolução direta por `mapId`, sem qualquer fixture de
      `Location` "derivada"
- [ ] Regressão: tempo de viagem calculado bate com o mesmo resultado de antes pros hunts já
      resolvidos (só que agora sem passar pela derivação)
