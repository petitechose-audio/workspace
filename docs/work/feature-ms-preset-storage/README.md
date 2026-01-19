# Feature: Preset Storage System

**Scope**: midi-studio, open-control  
**Status**: planned  
**Created**: 2026-01-19  
**Updated**: 2026-01-19 - v1.1: Ajout CRC32, migration legacy, clarifications async WASM  

## Objectif

Implémenter un système de persistence complet pour midi-studio avec :

1. **Presets** : Configurations sauvegardées avec nombre de pages variable
2. **Settings globaux** : Juste le nom/slot du preset actif
3. **Parité plateforme** : Comportement identique sur Teensy, Native, WASM
4. **Échange Teensy/Desktop** : Sync des presets via protocole dédié

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CODE APPLICATIF                                 │
│                      (midi-studio)                                   │
│                                                                      │
│   PresetManager ────► IStorageBackend (settings)                    │
│        │                                                             │
│        └────────────► IPresetStorage (presets)                      │
└───────────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│    TEENSY     │   │    NATIVE     │   │     WASM      │
├───────────────┤   ├───────────────┤   ├───────────────┤
│ EEPROM        │   │ File          │   │ HTTP →        │
│ (settings)    │   │ (settings)    │   │ Bridge →      │
│               │   │               │   │ File          │
│ LittleFS      │   │ Files         │   │               │
│ (presets)     │   │ (presets)     │   │               │
└───────────────┘   └───────────────┘   └───────────────┘
```

## Comportement

### Démarrage
1. Lit `activePresetSlot` depuis EEPROM/settings
2. Si aucun preset n'existe → **Migration données legacy** (CoreSettings 8 pages)
3. Tente de charger le preset correspondant depuis Flash/dossier
4. Échec ou checksum invalide → Crée preset fallback (1 page, routing défaut)

### Runtime
- Modifications → dirty flag → auto-save après timeout (3s)
- Écrase le preset actif sur Flash/dossier

### Opérations
- **Créer preset** : 1 page défaut, devient actif
- **Charger preset** : Remplace preset actif
- **Supprimer preset** : Supprime fichier, fallback si actif
- **Ajouter page** : Ajoute au preset actif
- **Supprimer page** : Retire du preset actif (min 1 page)

## Phases

### Phase 1 : Fondations (Priorité haute)
- [ ] Interface `IPresetStorage` dans framework
- [ ] `FileStorageBackend` pour Native
- [ ] `FilePresetStorage` pour Native
- [ ] `PresetManager` dans midi-studio (avec CRC32)
- [ ] **Migration données legacy** (CoreSettings → Preset)
- [ ] Intégration main-native.cpp

### Phase 2 : Bridge HTTP (Priorité haute)
- [ ] Routes HTTP storage dans bridge (axum)
- [ ] `HttpStorageBackend` pour WASM
- [ ] `HttpPresetStorage` pour WASM
- [ ] Intégration main-wasm.cpp

### Phase 3 : Teensy (Priorité haute)
- [ ] `LittleFSPresetStorage` dans hal-teensy
- [ ] Intégration main.cpp (Teensy)
- [ ] Tests sur hardware

### Phase 4 : Échange Teensy/Desktop (Priorité moyenne)
- [ ] Protocole sync (messages dédiés)
- [ ] ArduinoJson pour conversion binaire ↔ JSON
- [ ] Handler Teensy
- [ ] Client Desktop (UI ou CLI)

### Phase 5 : Nommage avancé (Priorité basse)
- [ ] Noms libres (actuellement slots numérotés)
- [ ] Système de tags
- [ ] Auto-increment avec date

## Fichiers

| Fichier | Description |
|---------|-------------|
| `README.md` | Ce fichier - overview |
| `tech-spec.md` | Spécifications techniques détaillées |

## Liens

- [Tech Spec](./tech-spec.md) - Architecture, interfaces, formats
