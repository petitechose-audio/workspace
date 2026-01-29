# Feature: Preset Storage System

**Scope**: midi-studio, open-control
**Status**: planned/in progress (storage backends implemented; preset system pending)
**Created**: 2026-01-19
**Updated**: 2026-01-29 - Align docs with current code (IStorage + SD/File/Memory backends)

## Objectif

Implémenter la persistence des presets sur toutes les plateformes.

## Approche

**V1** : Persistence simple et fonctionnelle
**V2** : Extensions (multi-presets, LittleFS, sync, GUI)

V2 étend V1 sans breaking changes.

## Scope

### V1 (priorité haute)

| Feature | Description |
|---------|-------------|
| Persistence Native | `oc::impl::FileStorage` → fichier local (✅ implémenté, utilisé) |
| Persistence WASM | `desktop::MemoryStorage` → RAM (✅ implémenté, volatile) |
| Persistence Teensy | `oc::hal::teensy::SDCardBackend` → SD card (✅ implémenté, non-bloquant) |
| Zero-boilerplate | `Persistent<T>` avec dirty auto-detection |
| Migration legacy | CoreSettings 8 pages → PresetData |
| Pages variables | 1-8 pages par preset |

**Estimation V1** : ~16h

### V2 (après V1 stable)

| Feature | Description |
|---------|-------------|
| Multi-presets | IPresetBank, slots 1-99 |
| Multi-fichiers SD | Presets sur SD card |
| Bridge HTTP | Routes REST pour WASM |
| Sync Teensy↔Desktop | Protocole serial |
| Noms personnalisés | Metadata presets |
| GUI Manager | Interface web |

**Estimation V2** : ~30-45h

## Architecture

```
V1 (today):
  CoreState/CoreSettings → Settings<T> → oc::interface::IStorage
                                                     │
                          ┌──────────────────────────┼────────────────────┐
                          ▼                          ▼                    ▼
                   SDCardBackend                FileStorage          MemoryStorage
                     (Teensy)                   (Native)               (WASM)

V2 (extension):
  PresetManager → IPresetBank (multi-presets)
                       │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     FilePresetBank  SDCardBank   HttpPresetBank
```

## Fichiers

| Fichier | Description |
|---------|-------------|
| `README.md` | Ce fichier - overview |
| `v1-tech-spec.md` | Spec technique V1 (storage backends + intégration actuelle) |
| `v1-optimizations.md` | Optimisations V1 (Persistent<T>, etc.) |
| `v2-roadmap.md` | Roadmap V2 (futur) |
| `draft-generic-preset-system.md` | **Draft** - Architecture générique presets |

## Liens

- [V1 Tech Spec](./v1-tech-spec.md) - Architecture et implémentation V1
- [V2 Roadmap](./v2-roadmap.md) - Extensions futures
- [Draft Generic System](./draft-generic-preset-system.md) - Réflexion sur système générique
