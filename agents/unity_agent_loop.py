import os
import sys
import re
import json
import time
from typing import Dict, Any, Optional, List
from infrastructure.gemini_client import gemini_service
from infrastructure.nim_client import nim_service
from tools import execute_tool_call, extract_tool_call, resolve_tool_paths
from tools.unity_bridge_client import unity_client

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UNITY_AGENT_SYSTEM_PROMPT = """Sen Unity Oyun Motoru konusunda dünya çapında uzmanlaşmış OTONOM BİR OYUN GELİŞTİRİCİSİ ve TEKNİK DİREKTÖRSÜN (Unity Technical Director).

GÖREVİN:
Sana verilen oyun geliştirme görevini Unity Editor ile CANLI VE ETKİLEŞİMLİ olarak tamamlamak.
Sadece metin veya kod yazıp bırakmayacaksın! Dosyaları yazacak, Unity Editor'deki objeleri oluşturacak, bileşenleri bağlayacak, derleme ve konsol hatalarını canlı denetleyeceksin.

SANA SAĞLANAN ARAÇLAR (TOOLS):

📁 1. DOSYA VE KOD SİSTEMİ:
- `write_file`: {"file_path": "Assets/Scripts/PlayerController.cs", "content": "..."} -> C# scripti yazar.
- `read_file`: {"file_path": "..."} -> Dosyayı inceler.
- `grep_search`: {"directory_path": "Assets", "pattern": "..."} -> Proje dosyalarında sınıf/hata metni/metot arar.
- `inspect_image`: {"file_path": "Assets/...png", "detailed": false} -> Asset envanterindeki bir ikonu veya görseli gerektiğinde Gemini Vision ile inceler.
- `search_assets`: {"directory_path": ".", "query": "icon"} -> Proje klasöründeki görsel/ikon envanterini arar.
- `replace_in_file`: {"file_path": "...", "target_content": "...", "replacement_content": "..."} -> Koddaki hatayı düzeltir.

🎮 2. CANLI UNITY EDITOR ARAÇLARI:
- `unity_status`: {} -> Unity açık mı, derleniyor mu kontrol eder.
- `unity_wait_compile`: {"timeout": 30} -> C# kodu yazdıktan sonra Unity derlemesini bekler ve CS hata raporunu döner.
- `unity_get_hierarchy`: {} -> Sahnedeki tüm objeleri ve bileşenleri ağaç yapısında inceler.
- `unity_inspect_object`: {"target": "Player"} -> Bir objenin tüm alanlarını ve Inspector değişkenlerini döner.
- `unity_create_object`: {"name": "Player", "primitive_type": "Capsule", "px": 0, "py": 1, "pz": 0} -> Sahneye obje/primitif koyar.
- `unity_add_component`: {"target": "Player", "component": "PlayerController"} -> Scripti veya Unity bileşenini objeye takar.
- `unity_set_property`: {"target": "Player", "component": "PlayerController", "property": "moveSpeed", "value": "7.5", "is_reference": false} -> Inspector alanını ayarlar veya referans bağlar.
- `unity_create_prefab`: {"target": "Player", "asset_path": "Assets/Prefabs/Player.prefab"} -> Objeyi temiz bir Prefab olarak kaydeder.
- `unity_instantiate_prefab`: {"asset_path": "Assets/Prefabs/Player.prefab"} -> Prefab'ı sahneye çağırır.
- `unity_execute_csharp`: {"code": "Debug.Log('Test');"} -> Unity Editor içinde anında C# Editor kodu çalıştırır (REPL).
- `unity_delete_object`: {"target": "Player"} -> Sahneden obje siler.
- `unity_get_logs`: {} -> Unity konsolundaki kırmızı hataları veya uyarıları okur.
- `unity_clear_logs`: {} -> Unity konsolundaki geçmiş logları ve hataları temizler.
- `unity_set_play_mode`: {"play": true} -> Oyunu başlatır (PlayMode ON) veya durdurur (PlayMode OFF).
- `unity_capture_screenshot`: {"prefer_game_view": true} -> Canlı oyunun veya sahnenin ekran görüntüsünü alır.
- `unity_save_scene`: {} -> Sahneyi kaydeder.

KESİN ÇALIŞMA KURALLARI (RE-ACT PROTOKOLÜ):
1. **Derleme Garantisi:** Bir `.cs` dosyası yazdıktan sonra MUTLAKA `unity_wait_compile` çağır veya derleme sonucuna bak. Eğer CS derleme hatası alırsan, başka hiçbir işlem yapmadan ÖNCE kodu düzelt!
2. **Kör Çalışma Yasağı:** Sahneye bir obje eklemeden önce `unity_get_hierarchy` ile sahneyi gör.
3. **Prefab-First Disiplini:** Kritik oyun nesnelerini oluşturduktan sonra `unity_create_prefab` ile `Assets/Prefabs/` klasörüne kaydet.
4. **Format Kuralı:** Bir araç çalıştırmak istediğinde YALNIZCA şu formatta tek bir JSON bloğu ver:
```tool
{
  "tool": "araç_adı",
  "args": { ... }
}
```
5. İşin tamamen bittiğinde ve konsolda hiçbir kırmızı hata kalmadığında, hiçbir tool bloğu yazmadan kullanıcıya detaylı bir Başarı Özeti ver.
"""

class UnityAgentLoop:
    """
    Unity Odaklı Kapalı-Döngü (Closed-Loop / ReAct) Otonom Ajan Yürütücüsü.
    """
    def __init__(self, project_path: str = "", max_steps: int = 15):
        self.project_path = project_path
        self.max_steps = max_steps

    def execute_task(
        self,
        instruction: str,
        target_file: str = "",
        prefer_nim: bool = False,
        read_only: bool = False
    ) -> str:
        print(f"\n🎮 [Unity ReAct Ajanı] Görev Başlatıldı: {instruction[:70]}...")

        if self.project_path and os.path.exists(self.project_path) and not read_only:
            unity_client.install_bridge_to_project(self.project_path)

        connected = unity_client.is_connected()
        status_info = "Unity Çevrimiçi ve Bağlı" if connected else "Unity Çevrimdışı (Köprü dinlemede değil, sadece dosya işlemleri yürütülebilir)"
        print(f"   📡 Bağlantı Durumu: {status_info}")

        ro_note = (
            "\n⚠️ SALT-OKUNUR DENETİM MODU: Sahneyi veya dosyaları değiştiren araçlar (write_file, replace_in_file, "
            "unity_create_object, unity_delete_object, unity_add_component, unity_set_property, unity_execute_csharp) "
            "KULLANILAMAZ. Yalnızca okuma/inceleme araçlarını kullan!\n"
            if read_only else ""
        )

        sym_context = ""
        if self.project_path and os.path.isdir(os.path.join(self.project_path, "Assets")):
            try:
                from tools.unity_tools import format_unity_project_symbol_index
                sym_context = format_unity_project_symbol_index(self.project_path, max_chars=4500)
            except Exception:
                sym_context = ""

        conversation_history = (
            f"KULLANICI GÖREVİ:\n{instruction}\n\n"
            f"ÇALIŞMA DİZİNİ: {self.project_path}\n"
            f"HEDEF DOSYA/BİLEŞEN: {target_file}\n"
            f"UNITY KÖPRÜ DURUMU: {status_info}\n"
            f"{ro_note}"
            + (f"\n{sym_context}\n" if sym_context else "")
        )

        mutating_tools = {
            "write_file", "replace_in_file", "run_terminal",
            "unity_create_object", "unity_delete_object", "unity_add_component",
            "unity_set_property", "unity_create_prefab", "unity_instantiate_prefab",
            "unity_execute_csharp", "unity_set_play_mode", "unity_clear_logs"
        }
        effective_mutating_tools = mutating_tools - {"unity_clear_logs", "unity_set_play_mode"}
        mutating_actions_count = 0
        nudged_without_mutation = False

        for step in range(1, self.max_steps + 1):
            print(f"\n   🔄 [Döngü Adımı {step}/{self.max_steps}] Düşünülüyor...")

            response = ""
            if prefer_nim and nim_service.client:
                try:
                    nim_model = nim_service.get_best_model_for_capability("reason")
                    messages = [
                        {"role": "system", "content": UNITY_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": conversation_history}
                    ]
                    response = nim_service.complete_with_retry(
                        model_id=nim_model,
                        messages=messages,
                        temperature=0.15,
                        timeout=90.0
                    )
                except Exception as nim_ex:
                    print(f"      ⚠️ NIM hatası ({nim_ex}), Gemini devrede...")
                    response = gemini_service.generate_with_retry(
                        prompt=conversation_history,
                        system_instruction=UNITY_AGENT_SYSTEM_PROMPT,
                        temperature=0.2
                    )
            else:
                try:
                    response = gemini_service.generate_with_retry(
                        prompt=conversation_history,
                        system_instruction=UNITY_AGENT_SYSTEM_PROMPT,
                        temperature=0.2
                    )
                except Exception as ex:
                    print(f"      ⚠️ Gemini hatası: {ex}, NIM devrede...")
                    messages = [
                        {"role": "system", "content": UNITY_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": conversation_history}
                    ]
                    nim_model = nim_service.get_best_model_for_capability("reason")
                    response = nim_service.complete_with_retry(
                        model_id=nim_model,
                        messages=messages,
                        temperature=0.15,
                        timeout=90.0
                    )

            if not response:
                return "❌ Ajan yanıt üretemedi."

            parsed_tool = extract_tool_call(response)
            if parsed_tool:
                tool_name, tool_args = parsed_tool
                try:
                    if read_only and tool_name in mutating_tools:
                        tool_result = f"Hata: Salt-okunur modda '{tool_name}' aracı çalıştırılamaz. Yalnızca okuma/inceleme araçlarını kullanın."
                    else:
                        if self.project_path:
                            tool_args = resolve_tool_paths(tool_args, self.project_path)

                        print(f"      ⚡ [Tool Çağrısı]: {tool_name}({list(tool_args.keys())})")
                        tool_result = execute_tool_call(tool_name, tool_args)
                        print(f"         └ Çıktı: {str(tool_result)[:120]}...")

                        if not read_only and tool_name in effective_mutating_tools and not str(tool_result).startswith("Hata:"):
                            mutating_actions_count += 1

                    extra_observation = ""
                    edited_path = str(tool_args.get("file_path") or tool_args.get("path") or tool_args.get("file") or "")
                    if not read_only and tool_name in ["write_file", "replace_in_file"] and edited_path.endswith(".cs"):
                        if unity_client.is_connected():
                            print("         ⏳ Unity C# derlemesi bekleniyor...")
                            compile_res = unity_client.wait_for_compilation(timeout=15.0, project_path=self.project_path)
                            if compile_res.get("has_errors"):
                                err_list = "\n".join(compile_res.get("errors", []))
                                extra_observation = f"\n\n🚨 DİKKAT: Az önce yazdığın C# scripti Unity'de derleme hatası verdi:\n{err_list}\nLütfen bir sonraki adımda bu hatayı derhal düzelt!"
                            else:
                                extra_observation = "\n\n✅ Unity C# derlemesi başarıyla tamamlandı (Sıfır hata)."

                    conversation_history += (
                        f"\n\n--- ADIM {step} MODEL YANITI ---\n{response}\n"
                        f"--- ADIM {step} TOOL SONUCU ({tool_name}) ---\n{tool_result}{extra_observation}\n"
                    )

                except Exception as e:
                    print(f"      ❌ Tool ayrıştırma/çalıştırma hatası: {e}")
                    conversation_history += f"\n\n--- ADIM {step} MODEL YANITI ---\n{response}\n--- HATA ---\nTool çalıştırma hatası: {e}\n"
            else:
                if not read_only and mutating_actions_count == 0 and step < self.max_steps and not nudged_without_mutation:
                    nudged_without_mutation = True
                    print("      ⚠️ [Unity ReAct Ajanı]: Henüz dosya/sahne değişikliği yapılmadı; düzeltme yapması için yönlendiriliyor...")
                    conversation_history += (
                        f"\n\n--- ADIM {step} MODEL YANITI ---\n{response}\n"
                        "--- SİSTEM UYARISI ---\n"
                        "🚨 Henüz HİÇBİR dosya düzenleme (`read_file` + `replace_in_file` / `write_file`) veya sahne değiştirme "
                        "(`unity_add_component` / `unity_set_property` / `unity_execute_csharp`) aracı çağırmadın! "
                        "Sadece inceleyip açıklama yazmak hatayı çözmez. Şimdi `grep_search` / `read_file` ile ilgili .cs dosyasını bulup "
                        "doğrudan `replace_in_file` veya `unity_*` aracıyla GERÇEKTEN düzelt ve `unity_save_scene` ile kaydet!"
                    )
                    continue
                if not read_only and mutating_actions_count == 0:
                    print(f"   ⚠️ [Unity ReAct Ajanı]: Görev tamamlanamadı; hiçbir somut dosya veya sahne değişikliği yapılmadı (Müdahale: 0).")
                    return (
                        f"⚠️ [Unity ReAct Ajanı]: Görev tamamlanamadı (0 müdahale yapıldı). "
                        f"Somut bir değişiklik (dosya/bileşen) uygulanmadı.\n{response}"
                    )

                print(f"   🎉 [Unity ReAct Ajanı] Görevi Başarıyla Tamamladı! (Müdahale: {mutating_actions_count})")
                return response

        return "⚠️ Ajan maksimum adım sayısına ulaştı. Mevcut durum kaydedildi."

unity_agent = UnityAgentLoop()
