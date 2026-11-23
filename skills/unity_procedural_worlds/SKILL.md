# 🌍 SKILL: Unity Procedural Worlds & Zero-Asset Generation

## 📌 Mimari Kurallar
1. **Sıfır Asset / Sıfır Prefab İlkesi:**
   - Dışarıdan 3D model veya prefab beklemeden, `Mesh`, `MeshFilter`, `GameObject.CreatePrimitive()` kullanarak arazileri (Terrain), labirentleri, parkur bloklarını ve zindanları tamamen matematiksel (Perlin Noise, Grid) üret.
2. **Procedural Materyal ve Renkler:**
   - Standart Shader kullanarak `new Material(Shader.Find("Standard"))` ile çalışma zamanında dinamik renk, emission ve parlaklık ata.
3. **Optimizasyon ve Chunking:**
   - Büyük dünyalarda objeleri tek bir root `WorldContainer` altında grupla, görünmeyen objeleri dinamik yok et veya deaktive et.
