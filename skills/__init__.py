import os

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

def ilgili_beceriyi_yukle(gorev_metni: str) -> str:
    """Görevin içeriğine göre en uygun uzmanlık becerilerini (Skills) dinamik olarak yükler."""
    kucuk = gorev_metni.lower()
    
    secilen_skilller = []
    
    # 1. Blender & 3D Modelleme / Render (bpy)
    if any(k in kucuk for k in ["blender", "bpy", ".blend", "cycles", "eevee", "geometry nodes", "shader node", "3d modelleme"]):
        secilen_skilller.append("blender_3d")

    # 2. Web & Tarayıcı & Fullstack (Web oyunu gibi isteklerde 'oyun' yüzünden Unity seçilmesini önlemek için önce web kontrol edilir!)
    elif any(k in kucuk for k in ["index.html", "html5", "web", "html", "css", "javascript", "canvas", "tarayıcı", "browser", "sayaç", "dashboard", "site", "react", "fastapi", "api", "security", "audit", "sast", "zafiyet", "owasp", "injection"]) and not any(u in kucuk for u in ["unity", "monobehaviour", "unityengine", "c#"]):
        secilen_skilller.append("web_fullstack")
        secilen_skilller.append("fullstack_react_fastapi")

    # 3. Unity & Oyun Geliştirme
    elif any(k in kucuk for k in ["unity", "c#", "monobehaviour", "unityengine", "oyun", "parkur", "3d", "fps", "karakter"]):
        secilen_skilller.append("unity_game_dev")
        if any(k in kucuk for k in ["level", "dünya", "platform", "harita", "bölüm", "procedural", "üret"]):
            secilen_skilller.append("unity_procedural_worlds")
        if any(k in kucuk for k in ["düşman", "ai", "npc", "kovalama", "devriye", "canavar"]):
            secilen_skilller.append("game_ai_behavior_trees")

    # 3. Gömülü Sistemler & Robotik
    elif any(k in kucuk for k in ["c dili", "c++", "gömülü", "stm32", "sensor", "arduino", "ros", "ros2", "robot"]):
        secilen_skilller.append("embedded_c")
        secilen_skilller.append("ros2_robotics_embedded")

    # 4. Mobil Geliştirme (Flutter & Dart)
    elif any(k in kucuk for k in ["flutter", "dart", "mobil", "android", "ios", "cross-platform"]):
        secilen_skilller.append("mobile_flutter")

    # 5. Unreal Engine & C++
    elif any(k in kucuk for k in ["unreal", "ue5", "ue4", "unreal engine"]):
        secilen_skilller.append("unreal_engine_cpp")

    if not secilen_skilller:
        secilen_skilller = ["unity_game_dev"]  # Varsayılan temel kılavuz

    toplam_metin = []
    for skill in set(secilen_skilller):
        skill_yolu = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        if os.path.exists(skill_yolu):
            try:
                with open(skill_yolu, "r", encoding="utf-8") as f:
                    icerik = f.read()
                print(f"   🧠 [Uzmanlık Becerisi Yüklendi]: {skill}")
                toplam_metin.append(f"\n--- 🌟 UZMANLIK BECERİSİ ({skill}) ---\n{icerik}\n---")
            except Exception:
                pass

    return "\n".join(toplam_metin)
