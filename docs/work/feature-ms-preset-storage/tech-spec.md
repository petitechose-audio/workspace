# Tech Spec: Preset Storage System

**Version**: 1.1  
**Date**: 2026-01-19  
**Updated**: 2026-01-19 - Ajout CRC32, migration legacy, clarifications async WASM  

## Table des matières

1. [Structures de données](#1-structures-de-données)
2. [Format fichier](#2-format-fichier)
3. [Interfaces](#3-interfaces)
4. [Implémentations](#4-implémentations)
5. [Code applicatif](#5-code-applicatif)
6. [Migration données legacy](#6-migration-données-legacy)
7. [Bridge HTTP API](#7-bridge-http-api)
8. [Système d'échange Teensy/Desktop](#8-système-déchange-teensydesktop)
9. [Impact sur l'existant](#9-impact-sur-lexistant)
10. [Dépendances](#10-dépendances)

---

## 1. Structures de données

### GlobalSettings (EEPROM / fichier settings)

```cpp
// Stocké sur EEPROM (Teensy) ou fichier settings.bin (Desktop)
// Contient uniquement le pointeur vers le preset actif

struct GlobalSettingsData {
    uint8_t activePresetSlot = 1;  // Numéro du preset actif (1-255, 0 = aucun)
    uint8_t reserved[7];           // Padding pour extensions futures
};  // 8 bytes

// Option A: Utiliser Settings<T> du framework (recommandé)
// Bénéfices: CRC32 automatique, migration, dirty tracking
using GlobalSettings = oc::state::Settings<GlobalSettingsData>;

// Option B: Format custom simple (si besoin de contrôle fin)
struct GlobalSettingsCustom {
    uint32_t magic = 0x4D535453;  // "MSTS" - MIDI Studio Settings
    uint8_t version = 1;
    GlobalSettingsData data;
    uint8_t padding[3];
};  // 16 bytes total
```

> **Note**: `Settings<T>` ajoute un header de 12 bytes (magic, version, size, CRC32).
> Total avec Option A: 12 + 8 = 20 bytes. Négligeable sur EEPROM 4KB.

### PresetHeader

```cpp
// En-tête d'un preset (début de chaque fichier preset)

struct PresetHeader {
    uint32_t magic = 0x4D535052;  // "MSPR" - MIDI Studio PResets
    uint8_t version = 1;          // Version du format preset
    uint8_t pageCount;            // Nombre de pages (1-255)
    uint16_t reserved;            // Padding pour alignement
    uint32_t checksum;            // CRC32 des pages (optionnel mais recommandé)
};  // 12 bytes

// CRC32 permet de:
// - Détecter corruption lors d'import externe (USB, réseau)
// - Valider l'intégrité après transmission
// - Distinguer preset corrompu vs absent (debugging)
```

> **Note**: LittleFS gère le wear-leveling et la cohérence des écritures,
> mais pas de checksum applicatif. Le CRC32 ajoute une couche de validation.

### MacroPageData (existant, inchangé)

```cpp
// Structure d'une page - 64 bytes exactement
// Défini dans midi-studio/core/src/state/macro/MacroPagesState.hpp

struct MacroPageData {
    char name[16];                      // Nom de la page (16 bytes)
    std::array<uint8_t, 8> cc;          // CC numbers (8 bytes)
    std::array<uint8_t, 8> channel;     // MIDI channels (8 bytes)
    std::array<float, 8> values;        // Valeurs normalisées (32 bytes)
};

static_assert(sizeof(MacroPageData) == 64, "MacroPageData must be exactly 64 bytes");
```

### Preset (en mémoire)

```cpp
// Preset complet chargé en RAM

static constexpr uint8_t MAX_PAGES = 32;  // Limite raisonnable

struct Preset {
    PresetHeader header;
    std::vector<MacroPageData> pages;  // Taille variable (1-MAX_PAGES)
    
    // Constructeur avec reserve() pour éviter réallocations
    Preset() {
        pages.reserve(MAX_PAGES);  // Alloue une fois à la construction
    }
    
    // Helpers
    size_t pageCount() const { return pages.size(); }
    MacroPageData& page(size_t i) { return pages[i]; }
    const MacroPageData& page(size_t i) const { return pages[i]; }
    
    // Validation
    bool isValid() const {
        return header.magic == 0x4D535052 
            && header.pageCount > 0 
            && header.pageCount <= MAX_PAGES
            && pages.size() == header.pageCount;
    }
    
    // Calcul CRC32 des pages
    uint32_t computeChecksum() const {
        // CRC32 IEEE 802.3
        uint32_t crc = 0xFFFFFFFF;
        for (const auto& page : pages) {
            const uint8_t* data = reinterpret_cast<const uint8_t*>(&page);
            for (size_t i = 0; i < sizeof(MacroPageData); ++i) {
                crc ^= data[i];
                for (int j = 0; j < 8; ++j) {
                    crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
                }
            }
        }
        return ~crc;
    }
    
    // Création preset par défaut
    static Preset createDefault() {
        Preset p;
        p.header.version = 1;
        p.header.pageCount = 1;
        p.pages.emplace_back();  // 1 page avec valeurs par défaut
        p.header.checksum = p.computeChecksum();
        return p;
    }
};
```

> **Note mémoire**: `std::vector` avec `reserve(32)` alloue 32×64 = 2KB une fois.
> C'est cohérent avec le pattern existant dans le codebase (init-time allocation).
> Alternative: `std::array<MacroPageData, MAX_PAGES>` + compteur (zéro allocation dynamique).

---

## 2. Format fichier

### Preset binaire (Flash / dossier presets)

```
Offset      Size        Content
────────────────────────────────────────────────
0x0000      4           magic (0x4D535052 "MSPR")
0x0004      1           version (1)
0x0005      1           pageCount (N)
0x0006      2           reserved
0x0008      4           checksum (CRC32 des pages)
0x000C      64          Page 0 (MacroPageData)
0x004C      64          Page 1 (si N >= 2)
...
0x000C+64*i 64          Page i
────────────────────────────────────────────────
Total: 12 + (N × 64) bytes

Exemple: 8 pages = 12 + 512 = 524 bytes
         32 pages (max) = 12 + 2048 = 2060 bytes
```

### Nommage fichiers

**Phase 1 (slots numérotés):**
```
presets/
├── 001.bin
├── 002.bin
├── 003.bin
└── ...
```

**Phase 5 (noms libres - futur):**
```
presets/
├── live-set-2024.bin
├── studio-session.bin
└── default.bin
```

### Arborescence stockage

**Teensy:**
```
EEPROM (4KB):
  └── GlobalSettings (16 bytes à 0x0000)

Flash (LittleFS):
  └── /presets/
      ├── 001.bin
      ├── 002.bin
      └── ...
```

**Desktop (Native/WASM via bridge):**
```
~/.config/midi-studio/
├── core/
│   ├── settings.bin      # GlobalSettings
│   └── presets/
│       ├── 001.bin
│       └── ...
└── bitwig/
    ├── settings.bin
    └── presets/
        └── ...
```

---

## 3. Interfaces

### IPresetStorage (nouvelle)

```cpp
// framework/src/oc/hal/IPresetStorage.hpp

namespace oc::hal {

/// Information sur un preset
struct PresetInfo {
    uint8_t slot;
    uint8_t pageCount;
    // Phase 5: char name[32]; uint32_t timestamp;
};

/// Callback pour énumérer les presets
using PresetEnumCallback = std::function<void(const PresetInfo& info)>;

class IPresetStorage {
public:
    virtual ~IPresetStorage() = default;
    
    /// Initialise le storage (crée dossiers si nécessaire)
    virtual bool init() = 0;
    
    /// Énumère les presets existants
    virtual void enumerate(PresetEnumCallback callback) = 0;
    
    /// Vérifie si un slot contient un preset
    virtual bool exists(uint8_t slot) = 0;
    
    /// Charge un preset (valide magic + checksum)
    /// @param slot Numéro du slot (1-255)
    /// @param header [out] En-tête chargé
    /// @param pages [out] Pages chargées (vector redimensionné)
    /// @return true si succès et checksum valide
    virtual bool load(uint8_t slot, PresetHeader& header, 
                      std::vector<MacroPageData>& pages) = 0;
    
    /// Sauvegarde un preset (calcule checksum automatiquement)
    virtual bool save(uint8_t slot, const PresetHeader& header,
                      const std::vector<MacroPageData>& pages) = 0;
    
    /// Supprime un preset
    virtual bool remove(uint8_t slot) = 0;
    
    /// Trouve le prochain slot libre
    /// @return Numéro du slot libre (1-255), ou 0 si plein
    virtual uint8_t findFreeSlot() = 0;
    
    /// Nombre de presets existants
    virtual size_t count() = 0;
};

}  // namespace oc::hal
```

### IStorageBackend (existant, inchangé)

```cpp
// framework/src/oc/hal/IStorageBackend.hpp
// Utilisé pour GlobalSettings (EEPROM / fichier binaire unique)

class IStorageBackend {
public:
    virtual bool available() const = 0;
    virtual size_t read(uint32_t address, uint8_t* buffer, size_t size) = 0;
    virtual size_t write(uint32_t address, const uint8_t* buffer, size_t size) = 0;
    virtual bool commit() = 0;
    virtual bool erase(uint32_t address, size_t size) = 0;
    virtual size_t capacity() const = 0;
};
```

---

## 4. Implémentations

### 4.1 LittleFSPresetStorage (Teensy)

```cpp
// hal-teensy/src/oc/hal/teensy/LittleFSPresetStorage.hpp

namespace oc::hal::teensy {

class LittleFSPresetStorage : public IPresetStorage {
public:
    explicit LittleFSPresetStorage(size_t fsSize = 512 * 1024);
    
    bool init() override;
    void enumerate(PresetEnumCallback callback) override;
    bool exists(uint8_t slot) override;
    bool load(uint8_t slot, PresetHeader& header, 
              std::vector<MacroPageData>& pages) override;
    bool save(uint8_t slot, const PresetHeader& header,
              const std::vector<MacroPageData>& pages) override;
    bool remove(uint8_t slot) override;
    uint8_t findFreeSlot() override;
    size_t count() override;

private:
    LittleFS_Program fs_;
    size_t fsSize_;
    bool initialized_ = false;
    
    // Génère le path: "/presets/001.bin"
    static void slotToPath(uint8_t slot, char* path, size_t size);
};

}  // namespace oc::hal::teensy
```

### 4.2 FilePresetStorage (Native)

```cpp
// hal-sdl/src/oc/hal/sdl/FilePresetStorage.hpp

namespace oc::hal::sdl {

class FilePresetStorage : public IPresetStorage {
public:
    /// @param basePath Dossier des presets (ex: "~/.config/midi-studio/core/presets")
    explicit FilePresetStorage(const std::string& basePath);
    
    bool init() override;
    void enumerate(PresetEnumCallback callback) override;
    bool exists(uint8_t slot) override;
    bool load(uint8_t slot, PresetHeader& header, 
              std::vector<MacroPageData>& pages) override;
    bool save(uint8_t slot, const PresetHeader& header,
              const std::vector<MacroPageData>& pages) override;
    bool remove(uint8_t slot) override;
    uint8_t findFreeSlot() override;
    size_t count() override;

private:
    std::string basePath_;
    
    std::string slotToPath(uint8_t slot) const;
};

}  // namespace oc::hal::sdl
```

### 4.3 HttpPresetStorage (WASM)

```cpp
// hal-sdl/src/oc/hal/sdl/HttpPresetStorage.hpp

namespace oc::hal::sdl {

/**
 * @brief HTTP-based preset storage for WASM builds
 * 
 * Pattern async: Cache local + sync en arrière-plan
 * - Les méthodes load/save opèrent sur le cache local (synchrone)
 * - syncWithServer() synchronise le cache avec le bridge (async)
 * - L'utilisateur voit toujours un état cohérent
 * 
 * Ce pattern évite de bloquer le main loop WASM qui est single-threaded.
 */
class HttpPresetStorage : public IPresetStorage {
public:
    /// @param baseUrl URL de base (ex: "http://localhost:8080/storage/core/presets")
    explicit HttpPresetStorage(const std::string& baseUrl);
    
    bool init() override;
    void enumerate(PresetEnumCallback callback) override;
    bool exists(uint8_t slot) override;
    bool load(uint8_t slot, PresetHeader& header, 
              std::vector<MacroPageData>& pages) override;
    bool save(uint8_t slot, const PresetHeader& header,
              const std::vector<MacroPageData>& pages) override;
    bool remove(uint8_t slot) override;
    uint8_t findFreeSlot() override;
    size_t count() override;
    
    // ═══════════════════════════════════════════════════════════════════
    // Async sync (appeler périodiquement ou sur événement)
    // ═══════════════════════════════════════════════════════════════════
    
    /// Lance une sync async avec le serveur
    void syncWithServer();
    
    /// Vérifie si une sync est en cours
    bool isSyncing() const { return syncing_; }
    
    /// Callback appelé quand sync terminée
    using SyncCallback = std::function<void(bool success)>;
    void setOnSyncComplete(SyncCallback cb) { onSyncComplete_ = std::move(cb); }

private:
    std::string baseUrl_;
    
    // Cache local (toujours disponible, même hors-ligne)
    std::map<uint8_t, Preset> cache_;
    std::set<uint8_t> dirtySlots_;  // Slots modifiés localement
    bool syncing_ = false;
    SyncCallback onSyncComplete_;
    
    // Callbacks statiques pour emscripten_fetch
    static void onFetchSuccess(emscripten_fetch_t* fetch);
    static void onFetchError(emscripten_fetch_t* fetch);
};

}  // namespace oc::hal::sdl
```

> **Pattern async WASM**: Les méthodes IPresetStorage restent synchrones (opèrent sur cache).
> Le code existant (WebSocketTransport) utilise le même pattern: callbacks C statiques
> avec `userData` pointant vers `this`. Voir `hal-net/WebSocketTransport.cpp`.

### 4.4 FileStorageBackend (Native)

```cpp
// hal-sdl/src/oc/hal/sdl/FileStorageBackend.hpp

namespace oc::hal::sdl {

class FileStorageBackend : public IStorageBackend {
public:
    /// @param filePath Chemin du fichier (ex: "~/.config/midi-studio/core/settings.bin")
    explicit FileStorageBackend(const std::string& filePath);
    
    bool available() const override;
    size_t read(uint32_t address, uint8_t* buffer, size_t size) override;
    size_t write(uint32_t address, const uint8_t* buffer, size_t size) override;
    bool commit() override;
    bool erase(uint32_t address, size_t size) override;
    size_t capacity() const override;

private:
    std::string filePath_;
    std::vector<uint8_t> cache_;  // Fichier chargé en mémoire
    bool dirty_ = false;
    
    bool load();  // Charge depuis disque
    bool flush(); // Écrit sur disque
};

}  // namespace oc::hal::sdl
```

### 4.5 HttpStorageBackend (WASM)

```cpp
// hal-sdl/src/oc/hal/sdl/HttpStorageBackend.hpp

namespace oc::hal::sdl {

class HttpStorageBackend : public IStorageBackend {
public:
    /// @param url URL complète (ex: "http://localhost:8080/storage/core/settings")
    explicit HttpStorageBackend(const std::string& url);
    
    bool available() const override;
    size_t read(uint32_t address, uint8_t* buffer, size_t size) override;
    size_t write(uint32_t address, const uint8_t* buffer, size_t size) override;
    bool commit() override;
    bool erase(uint32_t address, size_t size) override;
    size_t capacity() const override;

private:
    std::string url_;
    std::vector<uint8_t> cache_;
    bool dirty_ = false;
    bool loaded_ = false;
    
    bool fetch();  // GET depuis bridge
    bool push();   // PUT vers bridge
};

}  // namespace oc::hal::sdl
```

---

## 5. Code applicatif

### PresetManager

```cpp
// midi-studio/core/src/state/PresetManager.hpp

namespace core::state {

class PresetManager {
public:
    PresetManager(oc::hal::IStorageBackend& settingsBackend,
                  oc::hal::IPresetStorage& presetStorage);
    
    // ═══════════════════════════════════════════════════════════════════
    // Lifecycle
    // ═══════════════════════════════════════════════════════════════════
    
    /// Initialise et charge le preset actif
    /// Appelé au démarrage
    bool init();
    
    /// Met à jour l'auto-save
    /// Appelé dans la main loop
    void update();
    
    // ═══════════════════════════════════════════════════════════════════
    // Accès preset actif
    // ═══════════════════════════════════════════════════════════════════
    
    Preset& active() { return active_; }
    const Preset& active() const { return active_; }
    uint8_t activeSlot() const { return settings_.activePresetSlot; }
    size_t pageCount() const { return active_.pages.size(); }
    
    MacroPageData& page(size_t index) { return active_.pages[index]; }
    const MacroPageData& page(size_t index) const { return active_.pages[index]; }
    
    // ═══════════════════════════════════════════════════════════════════
    // Opérations preset
    // ═══════════════════════════════════════════════════════════════════
    
    /// Crée un nouveau preset (1 page défaut)
    /// @return true si succès
    bool createNew();
    
    /// Charge un preset existant
    /// @param slot Numéro du slot (1-255)
    /// @return true si succès
    bool load(uint8_t slot);
    
    /// Sauvegarde immédiate (bypass auto-save)
    bool save();
    
    /// Supprime un preset
    /// @param slot Numéro du slot
    /// @return true si succès
    bool remove(uint8_t slot);
    
    // ═══════════════════════════════════════════════════════════════════
    // Opérations pages
    // ═══════════════════════════════════════════════════════════════════
    
    /// Ajoute une page au preset actif
    /// @return true si succès
    bool addPage();
    
    /// Supprime une page (si pageCount > 1)
    /// @param index Index de la page à supprimer
    /// @return true si succès
    bool removePage(size_t index);
    
    // ═══════════════════════════════════════════════════════════════════
    // Énumération
    // ═══════════════════════════════════════════════════════════════════
    
    void enumerate(oc::hal::PresetEnumCallback callback) {
        presetStorage_.enumerate(callback);
    }
    
    size_t presetCount() { return presetStorage_.count(); }
    
    // ═══════════════════════════════════════════════════════════════════
    // Dirty tracking
    // ═══════════════════════════════════════════════════════════════════
    
    /// Marque le preset comme modifié (déclenche auto-save)
    void markDirty();
    
    /// Vérifie si des modifications sont en attente
    bool isDirty() const { return dirty_; }
    
    /// Force la sauvegarde si dirty
    void flush();

private:
    // Storage
    oc::hal::IStorageBackend& settingsBackend_;
    oc::hal::IPresetStorage& presetStorage_;
    
    // State
    GlobalSettingsData settings_;
    Preset active_;
    
    // Auto-save
    bool dirty_ = false;
    uint32_t lastModified_ = 0;
    static constexpr uint32_t SAVE_DELAY_MS = 3000;
    
    // Helpers
    bool loadSettings();
    bool saveSettings();
    bool loadActivePreset();
    void createFallbackPreset();
    
    /// Migration depuis l'ancien format CoreSettings (8 pages fixes)
    /// Appelé automatiquement par init() si aucun preset n'existe
    bool migrateLegacyData();
};

}  // namespace core::state
```

### Points d'entrée modifiés

```cpp
// === Teensy: midi-studio/core/main.cpp ===

#include <oc/hal/teensy/EEPROMBackend.hpp>
#include <oc/hal/teensy/LittleFSPresetStorage.hpp>
#include "state/PresetManager.hpp"

static oc::hal::teensy::EEPROMBackend eepromBackend;
static oc::hal::teensy::LittleFSPresetStorage presetStorage;
static std::optional<core::state::PresetManager> presets;

void setup() {
    // ... init display, lvgl, etc.
    
    presetStorage.init();
    presets.emplace(eepromBackend, presetStorage);
    presets->init();
    
    // ... register contexts
}

void loop() {
    // ... app.update()
    presets->update();  // Auto-save
    // ... lvgl.refresh()
}
```

```cpp
// === Native: midi-studio/core/sdl/main-native.cpp ===

#include <oc/hal/sdl/FileStorageBackend.hpp>
#include <oc/hal/sdl/FilePresetStorage.hpp>
#include "state/PresetManager.hpp"

int main(int argc, char** argv) {
    sdl::SdlEnvironment env;
    if (!env.init(argc, argv)) return 1;
    
    // Storage
    oc::hal::sdl::FileStorageBackend settingsBackend(
        "~/.config/midi-studio/core/settings.bin");
    oc::hal::sdl::FilePresetStorage presetStorage(
        "~/.config/midi-studio/core/presets/");
    
    presetStorage.init();
    core::state::PresetManager presets(settingsBackend, presetStorage);
    presets.init();
    
    // App
    oc::app::OpenControlApp app = oc::hal::sdl::AppBuilder()
        .midi(...)
        .controllers(env.inputMapper())
        .inputConfig(Config::Input::CONFIG);
    
    core::app::registerContexts(app, presets);
    app.begin();
    
    while (env.processEvents()) {
        app.update();
        presets.update();  // Auto-save
        env.refresh();
    }
    
    presets.flush();  // Sauvegarde finale
    return 0;
}
```

```cpp
// === WASM: midi-studio/core/sdl/main-wasm.cpp ===

#include <oc/hal/sdl/HttpStorageBackend.hpp>
#include <oc/hal/sdl/HttpPresetStorage.hpp>
#include "state/PresetManager.hpp"

static oc::hal::sdl::HttpStorageBackend* g_settingsBackend = nullptr;
static oc::hal::sdl::HttpPresetStorage* g_presetStorage = nullptr;
static core::state::PresetManager* g_presets = nullptr;

int main(int argc, char** argv) {
    // Static storage pour WASM
    static oc::hal::sdl::HttpStorageBackend settingsBackend(
        "http://localhost:8080/storage/core/settings");
    static oc::hal::sdl::HttpPresetStorage presetStorage(
        "http://localhost:8080/storage/core/presets");
    
    g_settingsBackend = &settingsBackend;
    g_presetStorage = &presetStorage;
    
    presetStorage.init();
    static core::state::PresetManager presets(settingsBackend, presetStorage);
    g_presets = &presets;
    presets.init();
    
    // ... reste identique
}

static void tick(void*) {
    // ...
    g_presets->update();  // Auto-save
    // ...
}
```

---

## 6. Migration données legacy

### Contexte

Le système actuel (`CoreSettings`) stocke 8 pages fixes en EEPROM avec le format :

```
Offset  | Size | Content
0x0000  | 4    | Magic (0x4D435354 "MCST")
0x0004  | 1    | Version
0x0005  | 1    | Active page index
0x0006  | 10   | Reserved
0x0010  | 512  | 8 pages × 64 bytes
```

Il faut migrer ces données vers le nouveau système de presets.

### Stratégie de migration

```cpp
// Dans PresetManager::init()

bool PresetManager::init() {
    // 1. Charger GlobalSettings
    if (!loadSettings()) {
        // Pas de settings → première utilisation ou migration
    }
    
    // 2. Vérifier si un preset existe
    if (!presetStorage_.exists(settings_.activePresetSlot)) {
        // Aucun preset → tenter migration legacy
        if (migrateLegacyData()) {
            OC_LOG_INFO("[PresetManager] Migrated legacy data to preset 1");
        } else {
            // Pas de données legacy → créer preset par défaut
            createFallbackPreset();
        }
    }
    
    // 3. Charger le preset actif
    return loadActivePreset();
}
```

### Implémentation migration

```cpp
bool PresetManager::migrateLegacyData() {
    // Vérifier le magic de l'ancien format
    constexpr uint32_t LEGACY_MAGIC = 0x4D435354;  // "MCST"
    uint32_t magic = 0;
    settingsBackend_.read(0x0000, reinterpret_cast<uint8_t*>(&magic), 4);
    
    if (magic != LEGACY_MAGIC) {
        return false;  // Pas de données legacy
    }
    
    OC_LOG_INFO("[PresetManager] Found legacy CoreSettings, migrating...");
    
    // Lire l'index de page active
    uint8_t legacyActivePage = 0;
    settingsBackend_.read(0x0005, &legacyActivePage, 1);
    
    // Créer un preset avec les 8 pages legacy
    Preset migrated;
    migrated.header.version = 1;
    migrated.header.pageCount = 8;
    migrated.pages.resize(8);
    
    // Lire les 8 pages depuis l'ancien offset (0x0010)
    for (int i = 0; i < 8; i++) {
        settingsBackend_.read(
            0x0010 + i * 64,
            reinterpret_cast<uint8_t*>(&migrated.pages[i]),
            64
        );
    }
    
    // Calculer le checksum
    migrated.header.checksum = migrated.computeChecksum();
    
    // Sauvegarder comme preset 1
    if (!presetStorage_.save(1, migrated.header, migrated.pages)) {
        OC_LOG_ERROR("[PresetManager] Failed to save migrated preset");
        return false;
    }
    
    // Mettre à jour GlobalSettings
    settings_.activePresetSlot = 1;
    saveSettings();
    
    // Optionnel: effacer l'ancien magic pour éviter re-migration
    uint32_t newMagic = 0xFFFFFFFF;
    settingsBackend_.write(0x0000, reinterpret_cast<uint8_t*>(&newMagic), 4);
    settingsBackend_.commit();
    
    OC_LOG_INFO("[PresetManager] Migration complete: 8 pages → preset 1");
    return true;
}
```

### Comportement attendu

| Situation | Action |
|-----------|--------|
| Première utilisation (EEPROM vide) | Créer preset 1 avec 1 page défaut |
| Données legacy présentes | Migrer vers preset 1 avec 8 pages |
| Données legacy + presets existants | Garder presets, ignorer legacy |
| Preset actif corrompu | Fallback vers preset 1 ou défaut |

### Tests de migration

```cpp
// Test: migration depuis CoreSettings legacy
TEST(PresetManager, MigrateLegacyData) {
    MockStorageBackend settingsBackend;
    MockPresetStorage presetStorage;
    
    // Setup: écrire données legacy
    writeLegacyFormat(settingsBackend, 8 /* pages */);
    
    // Act: init devrait migrer
    PresetManager pm(settingsBackend, presetStorage);
    ASSERT_TRUE(pm.init());
    
    // Assert: preset 1 créé avec 8 pages
    ASSERT_TRUE(presetStorage.exists(1));
    ASSERT_EQ(pm.pageCount(), 8);
    ASSERT_EQ(pm.activeSlot(), 1);
}
```

---

## 7. Bridge HTTP API

### Routes

```
# Settings (fichier binaire unique)
GET    /storage/{app}/settings           → Lit settings.bin
PUT    /storage/{app}/settings           ← Écrit settings.bin

# Presets (dossier de fichiers)
GET    /storage/{app}/presets            → Liste [{slot, pageCount}, ...]
GET    /storage/{app}/presets/{slot}     → Lit preset binaire
PUT    /storage/{app}/presets/{slot}     ← Écrit preset binaire
DELETE /storage/{app}/presets/{slot}     → Supprime preset
```

### Implémentation Rust (bridge)

```rust
// bridge/src/storage/mod.rs

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, put, delete},
    Router,
    body::Bytes,
};
use std::path::PathBuf;
use tokio::fs;

pub fn storage_routes() -> Router<AppState> {
    Router::new()
        .route("/storage/:app/settings", get(get_settings).put(put_settings))
        .route("/storage/:app/presets", get(list_presets))
        .route("/storage/:app/presets/:slot", 
               get(get_preset).put(put_preset).delete(delete_preset))
}

fn storage_path(app: &str) -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("midi-studio")
        .join(app)
}

async fn get_settings(Path(app): Path<String>) -> impl IntoResponse {
    let path = storage_path(&app).join("settings.bin");
    match fs::read(&path).await {
        Ok(data) => (StatusCode::OK, data).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn put_settings(Path(app): Path<String>, body: Bytes) -> StatusCode {
    let dir = storage_path(&app);
    fs::create_dir_all(&dir).await.ok();
    let path = dir.join("settings.bin");
    match fs::write(&path, &body).await {
        Ok(_) => StatusCode::OK,
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

async fn list_presets(Path(app): Path<String>) -> impl IntoResponse {
    let dir = storage_path(&app).join("presets");
    let mut presets = Vec::new();
    
    if let Ok(mut entries) = fs::read_dir(&dir).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            if let Some(name) = entry.file_name().to_str() {
                if let Some(slot) = name.strip_suffix(".bin")
                    .and_then(|s| s.parse::<u8>().ok()) 
                {
                    // Lire le pageCount depuis le header
                    if let Ok(data) = fs::read(entry.path()).await {
                        if data.len() >= 2 {
                            presets.push(serde_json::json!({
                                "slot": slot,
                                "pageCount": data[1]
                            }));
                        }
                    }
                }
            }
        }
    }
    
    axum::Json(presets)
}

async fn get_preset(Path((app, slot)): Path<(String, u8)>) -> impl IntoResponse {
    let path = storage_path(&app).join("presets").join(format!("{:03}.bin", slot));
    match fs::read(&path).await {
        Ok(data) => (StatusCode::OK, data).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn put_preset(Path((app, slot)): Path<(String, u8)>, body: Bytes) -> StatusCode {
    let dir = storage_path(&app).join("presets");
    fs::create_dir_all(&dir).await.ok();
    let path = dir.join(format!("{:03}.bin", slot));
    match fs::write(&path, &body).await {
        Ok(_) => StatusCode::OK,
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

async fn delete_preset(Path((app, slot)): Path<(String, u8)>) -> StatusCode {
    let path = storage_path(&app).join("presets").join(format!("{:03}.bin", slot));
    match fs::remove_file(&path).await {
        Ok(_) => StatusCode::OK,
        Err(_) => StatusCode::NOT_FOUND,
    }
}
```

### Cargo.toml (ajouts)

```toml
[dependencies]
axum = "0.7"
dirs = "5"
```

---

## 8. Système d'échange Teensy/Desktop

### Protocole (Phase 4)

Messages pour sync via USB Serial :

```cpp
// Nouveaux MessageID dans le protocole

enum class StorageMessageID : uint8_t {
    // Desktop → Teensy (requêtes)
    PRESET_LIST_REQUEST     = 0x80,  // Demande liste des presets
    PRESET_GET_REQUEST      = 0x81,  // Demande un preset (slot) → JSON
    PRESET_PUT_REQUEST      = 0x82,  // Envoie un preset JSON → Teensy stocke
    PRESET_DELETE_REQUEST   = 0x83,  // Supprime un preset
    
    // Teensy → Desktop (réponses)
    PRESET_LIST_RESPONSE    = 0x90,  // Liste JSON des presets
    PRESET_DATA_RESPONSE    = 0x91,  // Preset en JSON
    PRESET_ACK              = 0x92,  // Confirmation OK
    PRESET_ERROR            = 0x93,  // Erreur
};
```

### Format JSON pour échange

```json
// PRESET_LIST_RESPONSE
{
    "presets": [
        {"slot": 1, "pageCount": 3},
        {"slot": 2, "pageCount": 1},
        {"slot": 5, "pageCount": 8}
    ]
}

// PRESET_DATA_RESPONSE / PRESET_PUT_REQUEST
{
    "slot": 1,
    "pages": [
        {
            "name": "Synth Lead",
            "macros": [
                {"cc": 1, "channel": 1, "value": 0.5},
                {"cc": 2, "channel": 1, "value": 0.75},
                {"cc": 74, "channel": 1, "value": 0.0},
                {"cc": 71, "channel": 1, "value": 1.0},
                {"cc": 73, "channel": 1, "value": 0.5},
                {"cc": 72, "channel": 1, "value": 0.5},
                {"cc": 91, "channel": 1, "value": 0.25},
                {"cc": 93, "channel": 1, "value": 0.0}
            ]
        },
        {
            "name": "Bass Section",
            "macros": [...]
        }
    ]
}
```

### Conversion (Teensy)

```cpp
// midi-studio/core/src/protocol/PresetSerializer.hpp
// Utilise ArduinoJson

namespace core::protocol {

class PresetSerializer {
public:
    /// Convertit un preset binaire en JSON
    /// @param preset Preset à convertir
    /// @param buffer Buffer de sortie
    /// @param bufferSize Taille du buffer
    /// @return Nombre de bytes écrits, 0 si erreur
    static size_t toJson(const Preset& preset, char* buffer, size_t bufferSize);
    
    /// Parse un preset depuis JSON
    /// @param json String JSON
    /// @param preset [out] Preset parsé
    /// @return true si succès
    static bool fromJson(const char* json, Preset& preset);
};

}  // namespace core::protocol
```

---

## 9. Impact sur l'existant

### Fichiers à modifier

| Fichier | Action | Description |
|---------|--------|-------------|
| `framework/src/oc/hal/IPresetStorage.hpp` | **Créer** | Nouvelle interface |
| `hal-teensy/src/oc/hal/teensy/LittleFSPresetStorage.hpp` | **Créer** | Impl Teensy |
| `hal-sdl/src/oc/hal/sdl/FileStorageBackend.hpp` | **Créer** | Settings fichier |
| `hal-sdl/src/oc/hal/sdl/FilePresetStorage.hpp` | **Créer** | Presets fichier |
| `hal-sdl/src/oc/hal/sdl/HttpStorageBackend.hpp` | **Créer** | Settings HTTP |
| `hal-sdl/src/oc/hal/sdl/HttpPresetStorage.hpp` | **Créer** | Presets HTTP |
| `midi-studio/core/src/state/PresetManager.hpp` | **Créer** | Gestionnaire |
| `midi-studio/core/src/state/CoreState.hpp` | **Modifier** | Utiliser PresetManager |
| `midi-studio/core/src/state/CoreSettings.hpp` | **Supprimer** | Remplacé |
| `midi-studio/core/main.cpp` | **Modifier** | Injecter storage |
| `midi-studio/core/sdl/main-native.cpp` | **Modifier** | Injecter storage |
| `midi-studio/core/sdl/main-wasm.cpp` | **Modifier** | Injecter storage |
| `midi-studio/core/sdl/MemoryStorage.hpp` | **Supprimer** | Plus nécessaire |
| `bridge/Cargo.toml` | **Modifier** | Ajouter axum, dirs |
| `bridge/src/main.rs` | **Modifier** | Ajouter routes HTTP |

### Fichiers inchangés

- `MacroPageData` structure (déjà correct)
- `MacroState`, `MacroSlot` (runtime, pas persistence)
- Protocole Bitwig existant
- UI/Views

---

## 10. Dépendances

### Teensy (PlatformIO)

```ini
# platformio.ini - ajouter:
lib_deps =
    ...
    bblanchon/ArduinoJson@^7.0.0
```

LittleFS est inclus dans Teensyduino (pas besoin de lib externe).

### Bridge (Cargo)

```toml
# Cargo.toml - ajouter:
[dependencies]
axum = "0.7"
dirs = "5"
tower-http = { version = "0.5", features = ["cors"] }  # Pour WASM
```

### Desktop C++ (CMake)

Pas de nouvelle dépendance - utilise `<fstream>` standard.

Pour WASM HTTP: utilise `emscripten_fetch` (inclus dans Emscripten).

---

## Annexes

### A. Estimation effort

| Phase | Tâches | Effort |
|-------|--------|--------|
| 1 | Interfaces + FileStorage + PresetManager + **Migration legacy** | 5-7h |
| 2 | Bridge HTTP (axum) + HttpStorage + CORS | 3-4h |
| 3 | LittleFSPresetStorage + intégration Teensy | 3-4h |
| 4 | Protocole échange + ArduinoJson | 4-6h |
| 5 | Nommage avancé + tags | 4-6h |
| **Total** | | **19-27h** |

### B. Risques

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Fragmentation Flash (presets variables) | Faible | Moyen | LittleFS gère le wear-leveling |
| HTTP async en WASM | Moyenne | Moyen | Pattern cache local + sync background |
| Perte données legacy lors migration | Faible | Élevé | Migration automatique dans init() |
| Checksum invalide sur preset importé | Moyenne | Faible | Log warning + fallback défaut |
| CORS bloqué (WASM → bridge HTTP) | Moyenne | Moyen | tower-http avec CORS permissif |

> **Vérifié**: Le pattern async avec cache local est utilisé dans WebSocketTransport.
> Le risque HTTP async est maîtrisable avec le même pattern.

### C. Tests

- [ ] Unit tests PresetManager (load/save/create/delete)
- [ ] Unit tests FilePresetStorage
- [ ] Unit tests Preset (checksum validation, isValid)
- [ ] **Unit tests migration legacy** (CoreSettings → Preset)
- [ ] Integration test Native (persistence survit restart)
- [ ] Integration test WASM (via bridge, cache sync)
- [ ] Integration test Teensy (EEPROM + Flash)
- [ ] Test migration Teensy (données legacy → preset 1)
- [ ] Test échange Teensy ↔ Desktop
