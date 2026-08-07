# 07 — Re-exportação em v6: antes e depois

Gerado por `extractor/scripts/map_v6_migration_report.py` depois de
`node extractor/scripts/build_map.js --all`. Para regerar:

```
python extractor/scripts/map_v6_migration_report.py \
  --out .scratch/modelo-render-rme/reports/07-reexportacao-v6.md
```

## Resumo

- Mapas presentes nos dois formatos: **20**.
- Com alguma tile cujo conteúdo mudou entre v5 e v6: **0**.
- Com folha acima do limite seguro de textura (2048px): **0**.

## Por mapa

| mapa | folhas v5 → v6 | posicionamentos v5 → v6 | tamanho v5 → v6 | tiles divergentes |
|---|---:|---:|---:|---:|
| `ROOK-HUNT-0001_rats-sewers-2-rookguard` | 12 → 2 | 6126 → 6126 | 421 KB → 435 KB | 0 |
| `ROOK-HUNT-0002_rats-sewers` | 10 → 2 | 3314 → 3314 | 389 KB → 220 KB | 0 |
| `ROOK-HUNT-0003_troll-rookguard` | 10 → 2 | 7233 → 7233 | 744 KB → 473 KB | 0 |
| `ROOK-HUNT-0004_skeletons-rookguard` | 9 → 2 | 5605 → 5605 | 621 KB → 345 KB | 0 |
| `ROOK-HUNT-0005_wasps-rookguard` | 8 → 2 | 1370 → 1370 | 214 KB → 117 KB | 0 |
| `ROOK-HUNT-0006_wolfs-rookguard` | 4 → 2 | 2468 → 2468 | 130 KB → 177 KB | 0 |
| `ROOK-HUNT-0007_spiders-boat-rookguard` | 5 → 2 | 2468 → 2468 | 167 KB → 188 KB | 0 |
| `ROOK-HUNT-0009_orcs-rookguard` | 11 → 2 | 5359 → 5359 | 585 KB → 396 KB | 0 |
| `ROOK-HUNT-0010_bears-rookguard` | 9 → 2 | 2437 → 2437 | 114 KB → 192 KB | 0 |
| `ROOK-HUNT-0011_minotaur-room-rookguard` | 8 → 2 | 1495 → 1495 | 73 KB → 118 KB | 0 |
| `ROOK-HUNT-0012_orcs-cave-rookguard` | 6 → 2 | 1293 → 1293 | 72 KB → 107 KB | 0 |
| `ROOK-HUNT-0013_rats-rookguard` | 10 → 2 | 2559 → 2559 | 256 KB → 164 KB | 0 |
| `ROOK-HUNT-0015_trolls-tower-rookguard` | 7 → 2 | 2523 → 2523 | 346 KB → 184 KB | 0 |
| `ROOK-HUNT-0016_wolfs-east-rookguard` | 9 → 2 | 1798 → 1798 | 108 KB → 137 KB | 0 |
| `ROOK-HUNT-0017_wolfs-south-rookguard` | 8 → 2 | 2339 → 2339 | 217 KB → 182 KB | 0 |
| `ROOK-HUNT-0018_bugs-rookguard` | 12 → 2 | 11873 → 11873 | 1025 KB → 786 KB | 0 |
| `TEST-HUNT-0001_dragon-darashia` | 9 → 2 | 11448 → 11448 | 1352 KB → 641 KB | 0 |
| `TEST-HUNT-0002_grim-reaper` | 8 → 2 | 6928 → 6928 | 886 KB → 389 KB | 0 |
| `TEST-HUNT-0003_larva-ankrah` | 8 → 2 | 8764 → 8764 | 868 KB → 404 KB | 0 |
| `TEST-HUNT-0004_sea-serpent` | 9 → 2 | 8881 → 8881 | 872 KB → 499 KB | 0 |
| **total** | **172 → 40** | | **9461 KB → 6153 KB** | **0** |

Uma tile só conta como divergente quando o **conjunto de aparências** muda. A ordem dentro
da pilha muda de propósito — é a mudança inteira — e não conta.
