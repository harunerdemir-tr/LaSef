# 🎨 SKILL: Blender 4.x / 5.x Procedural 3D & Headless / Live MCP Scripting (`bpy`)

## 📌 Kesin Mimari Standartlar (Tüm Ajanlar İçin Zorunludur)

### 1. 🚨 BLENDER 4.x / 5.x `bpy` UYUMLULUĞU:
- Blender 4.x ve 5.x'te `Principled BSDF` düğümünde `"Specular"` yerine **`"Specular IOR Level"`**, `"Transmission"` yerine **`"Transmission Weight"`**, `"Coat"` yerine **`"Coat Weight"`** kullan.
- Eski `use_auto_smooth` (Blender 4.1+'da kaldırıldı) kullanma! Bunun yerine `bpy.ops.object.shade_smooth()` veya `mesh.polygons.foreach_set("use_smooth", ...)` kullan.
- `Principled BSDF` girdilerine erişirken anahtar yoksa `bsdf.inputs.get("...")` ile güvenli kontrol yap (`try/except` veya `if sock is not None:`).

### 2. 🏗️ SAHNE TEMİZLİĞİ VE BAĞLAM GÜVENLİĞİ:
- Headless veya canlı sahne sıfırlanacaksa önce aktif mod kontrolü yap (`if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')`).
- Tercihen `bpy.ops` yerine doğrudan veri API'si (`bpy.data.meshes.new`, `bpy.data.objects.new`, `collection.objects.link(obj)`, `bmesh`) veya açık `bpy.context.temp_override(...)` kullan ki background modda `poll()` hataları oluşmasın.
- Sahneye kamera (`Camera`) ve uygun ışık (`SUN` / `AREA` veya world sky) ekle; kamerayı `TRACK_TO` constraint veya vektör yönelimiyle sahneye doğrult.

### 3. 🧪 DOĞRULAMA & ÇIKTI STANDARDI:
- Script sonunda üretilen nesneleri (`len(bpy.data.objects)`), koleksiyonları ve isteğe bağlı `.blend` / önizleme render çıktısını temiz şekilde kaydet (örn. ortam değişkeni veya parametre verilmişse `.blend` / `.png` dışa aktar).
- Eğer LaSef Blender MCP Köprüsü (port `9876`) açıksa canlı sahneye bağlanır; kapalıysa LaSef üretilen scripti Blender CLI (`--background --python`) ile otomatik çalıştırıp doğrulayabilmelidir.
