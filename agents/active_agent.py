import os
from typing import Optional
from infrastructure.llm_client import cagir_gemini_sef
from infrastructure.nim_client import nim_service
from tools import execute_tool_call, extract_tool_call, resolve_tool_paths

READ_ONLY_AGENT_TOOLS = {
    "list_directory", "read_file", "grep_search", "check_syntax",
    "inspect_image", "search_assets",
    "unity_status", "unity_ping", "unity_get_hierarchy",
    "unity_inspect_object", "unity_get_logs",
    "blender_ping", "blender_status", "mcp_blender_ping",
    "blender_get_scene", "mcp_blender_get_scene",
}


def otonom_ajan_gorevi_yurut(
    gorev: str,
    hedef_klasor: str = "",
    max_adim: int = 6,
    prefer_nim: bool = False,
    read_only: bool = False,
    kaynak_baglami: str = "",
) -> str:
    """
    Ajan sadece pasif metin üretmez;
    Dosyaları ve Unity sahnesini okur, oluşturur, düzenler ve doğrular! (Tool-Calling ReAct Agent Loop)
    Hem Google Gemini hem NVIDIA NIM modelleriyle çalışabilir.
    """
    mod_etiketi = "Salt-Okunur İnceleme" if read_only else "Tam Yetkili Müdahale"
    print(f"\n🤖 [Aktif Otonom Ajan · {mod_etiketi}] Göreve Başladı: '{gorev[:70]}'")

    calisma_dizini = os.path.abspath(hedef_klasor) if hedef_klasor else os.getcwd()

    if read_only:
        arac_listesi = """SANA VERİLEN SALT-OKUNUR ARAÇLAR (TOOLS):
1. `list_directory`: `{"directory_path": "."}` -> Projedeki dosyaları listeler.
2. `read_file`: `{"file_path": "Assets/Scripts/..."}` -> Dosya içeriğini okur.
3. `grep_search`: `{"directory_path": ".", "pattern": "..."}` -> Kod içinde metin/sembol arar.
4. `inspect_image`: `{"file_path": "...", "detailed": false}` -> Görsel veya ikonu Gemini Vision ile inceler.
5. `search_assets`: `{"directory_path": ".", "query": "..."}` -> Proje görsel/ikon envanterinde arama yapar.
6. `unity_status`: `{}` -> Unity Editor (Port 8088) bağlantı, sahne ve derleme durumunu sorgular.
7. `unity_get_hierarchy`: `{}` -> Sahnedeki tüm kök GameObject'leri ve bileşenlerini listeler.
8. `unity_inspect_object`: `{"target": "Player"}` -> Sahnedeki bir objenin Transform ve bileşen detaylarını inceler.
9. `unity_get_logs`: `{}` -> Unity konsol loglarını okur."""
        mod_kurali = "- Bu görev SALT-OKUNUR (Read-Only) moddadır: Hiçbir dosyayı değiştirme veya silme; yalnızca incele ve net Türkçe yanıt ver."
    else:
        arac_listesi = """SANA VERİLEN ARAÇLAR (TOOLS):
1. `list_directory`: `{"directory_path": "."}` -> Projedeki dosyaları listeler.
2. `read_file`: `{"file_path": "Assets/Scripts/..."}` -> Dosya içeriğini okur.
   - Görsel/İkon gerektiğinde: `inspect_image` (`{"file_path": "...", "detailed": false}`) ve `search_assets` (`{"directory_path": ".", "query": "..."}`).
3. `write_file`: `{"file_path": "Assets/Scripts/...", "content": "..."}` -> Dosyayı doğrudan projeye yazar.
4. `replace_in_file`: `{"file_path": "...", "target_content": "...", "replacement_content": "..."}` -> Mevcut koddaki hedef bloğu günceller.
5. `run_terminal`: `{"command": "..."}` -> Terminal komutu çalıştırır.
6. `unity_status`: `{}` -> Unity Editor bağlantı ve derleme durumunu kontrol eder.
7. `unity_get_hierarchy`: `{}` -> Sahnedeki tüm GameObject'leri listeler.
8. `unity_inspect_object`: `{"target": "Player"}` -> Objenin bileşenlerini ve konumunu inceler.
9. `unity_create_object`: `{"name": "...", "primitive_type": "Cube", "px": 0, "py": 1, "pz": 0}` -> Sahneye yeni obje ekler.
10. `unity_add_component`: `{"target": "Player", "component": "Rigidbody"}` -> Objeye bileşen veya C# scripti ekler.
11. `unity_set_property`: `{"target": "Player", "component": "PlayerController", "property": "moveSpeed", "value": "8"}` -> Inspector özelliğini değiştirir.
12. `unity_execute_csharp`: `{"code": "..."}` -> Unity Editor içinde C# kodu çalıştırır.
13. `unity_wait_compile`: `{}` -> C# derlemesinin bitmesini bekler.
14. `unity_save_scene`: `{}` -> Aktif sahneyi diske kaydeder."""
        mod_kurali = "- İşi pasifçe anlatma; gerekli dosya veya Unity sahne değişikliklerini araçlarla bizzat uygula, ardından sonucu özetle."

    sistem_talimati = f"""Sen dünya çapında otonom bir Yazılım ve Oyun Motoru Mühendisi Ajanısın (ReAct Agent).
Hedef Çalışma Dizini: '{calisma_dizini}'

{arac_listesi}

KURALLAR:
{mod_kurali}
- Araç çağırmak istediğinde yanıtında YALNIZCA aşağıdaki blok formatını kullan:
```tool
{{"tool": "arac_adi", "args": {{}}}}
```
- Yeterli bilgiyi topladığında veya işlemi tamamladığında ```tool bloğu KULLANMA; doğrudan kullanıcıya net Türkçe nihai yanıtını yaz.
"""
    gecmis = f"Kullanıcı Görevi: {gorev}\nHedef Dizin: {calisma_dizini}"
    if kaynak_baglami:
        gecmis += f"\n\nMEVCUT PROJE VE SAHNE BAĞLAMI:\n{kaynak_baglami[:30000]}"

    son_yanit = ""
    for adim in range(1, max_adim + 1):
        try:
            yanit = ""
            if prefer_nim:
                try:
                    nim_model = nim_service.get_best_model_for_capability("reason")
                    yanit = nim_service.complete_with_retry(
                        model_id=nim_model,
                        messages=[
                            {"role": "system", "content": sistem_talimati},
                            {"role": "user", "content": gecmis},
                        ],
                        temperature=0.1,
                        max_tokens=4000,
                    )
                except Exception:
                    yanit = ""

            if not yanit or yanit.startswith("[HATA"):
                yanit = cagir_gemini_sef(sistem_talimati, gecmis, temperature=0.1)

            son_yanit = yanit
            parsed_tool = extract_tool_call(yanit)
            if parsed_tool:
                t_name, t_args = parsed_tool
                if read_only and t_name not in READ_ONLY_AGENT_TOOLS:
                    gecmis += (
                        f"\n\nSenin Yanıtın:\n{yanit}\n\n"
                        f"Tool Sonucu ({t_name}): HATA — Salt-okunur modda '{t_name}' aracına izin verilmez. "
                        f"Yalnızca okuma/inceleme araçlarını kullan veya doğrudan nihai cevabı yaz."
                    )
                    continue
                try:
                    t_args = resolve_tool_paths(t_args, calisma_dizini)
                    print(f"   ⚡ [Ajan Aracı Çağırdı ({adim}/{max_adim})] {t_name}({list(t_args.keys())})")
                    sonuc = execute_tool_call(t_name, t_args)
                    print(f"      └ 🟢 Gözlem: {str(sonuc)[:100]}")

                    gecmis += (
                        f"\n\nSenin Yanıtın:\n{yanit}\n\n"
                        f"Tool Sonucu ({t_name}):\n{str(sonuc)[:4000]}\n"
                        "Başka bir araca ihtiyacın yoksa doğrudan Türkçe nihai yanıtını yaz."
                    )
                    continue
                except Exception as e:
                    gecmis += f"\n\nTool çalıştırma hatası ({t_name}): {e}"
            else:
                return yanit
        except Exception as e:
            print(f"[HATA] Ajan döngüsü hatası: {e}")
            break

    if son_yanit and extract_tool_call(son_yanit):
        try:
            ozet_istegi = gecmis + "\n\nTüm araç adımları tamamlandı. Şimdi araç çağırmadan doğrudan kullanıcıya Türkçe nihai cevabı/raporu yaz."
            return cagir_gemini_sef(sistem_talimati, ozet_istegi, temperature=0.1)
        except Exception:
            pass
    return son_yanit or "Ajan görev döngüsünü tamamladı."
