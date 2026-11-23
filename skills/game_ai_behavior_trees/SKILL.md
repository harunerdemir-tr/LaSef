# 🧠 SKILL: Game AI & Behavior Trees / State Machines

## 📌 Mimari Kurallar
1. **Finit State Machine (FSM):**
   - Düşman ve NPC yapay zekaları için `IdleState`, `PatrolState`, `ChaseState`, `AttackState` sınıflarını interface tabanlı (`IState`) kurgula.
2. **Görüş ve Duyma Alanı (Field of View / Raycasting):**
   - Karakter algılamayı `Physics.Raycast`, `Physics.OverlapSphere` ve `Vector3.Angle` ile matematiksel yap; NavMesh yoksa bile yön vektörüyle hareket et.
3. **Dinamik Zorluk ve Hedef Takibi:**
   - Oyuncuyu akıcı şekilde takip etmek için `Vector3.MoveTowards` veya `Rigidbody.velocity` yönlendirmesi kullan.
