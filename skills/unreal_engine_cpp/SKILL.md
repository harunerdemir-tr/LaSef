# 🎮 SKILL: Unreal Engine 5 C++ & Gameplay Architecture

## 📌 Kesin Mimari Standartlar (Tüm Ajanlar İçin Zorunludur)

### 1. ⚙️ UNREAL ENGINE TİP SİSTEMİ & MAKROLAR (UCLASS / UPROPERTY / UFUNCTION):
- Unreal Engine Reflection sistemini eksiksiz kullan:
  - Sınıflar için `UCLASS()`, değişkenler için `UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "...")`, fonksiyonlar için `UFUNCTION(BlueprintCallable, Category = "...")` makrolarını kurallara uygun ekle.
- Garbage Collector'ın nesneleri toplaması için `TObjectPtr<T>` veya `UPROPERTY()` işaretçilerini doğru bağla; sahipsiz `new` veya standart C++ işaretçileri yerine `NewObject<T>()` / `SpawnActor<T>()` kullan.

### 2. 🎮 OYUN DÖNGÜSÜ & KARAKTER MEKANİKLERİ:
- Karakterler için `ACharacter` ve `UCharacterMovementComponent`, kameralar için `USpringArmComponent` ve `UCameraComponent` hiyerarşisini `CreateDefaultSubobject` ile Constructor içinde kur.
- Girdileri Enhanced Input System (`UInputAction`, `UInputMappingContext`) ile bağla.
- Fizik ve çarpışmalar için `UCapsuleComponent` veya `UStaticMeshComponent` kök bileşenlerini (RootComponent) net şekilde yapılandır.

### 3. 🛡️ DERLEME GÜVENLİĞİ & GENERATED HEADERS:
- Header dosyalarında `#include "DosyaAdi.generated.h"` kuralı ZORUNLU olarak en son `#include` satırında yer almalıdır.
- Sınıf isimlerinde Unreal adlandırma kurallarına tam uy: `A` (Actors), `U` (UObjects/Components), `F` (Structs), `E` (Enums), `I` (Interfaces).
- Fonksiyon gövdelerini eksiksiz doldur; boş bırakma.
