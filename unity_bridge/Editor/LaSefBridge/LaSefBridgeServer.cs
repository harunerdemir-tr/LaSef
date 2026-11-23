#if UNITY_EDITOR
using System;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.InteropServices;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace LaSef.UnityBridge
{
    /// <summary>
    /// 👑 LaSef Unity Editor Bridge
    /// Yapay Zeka Ajanları için İki Yönlü, Thread-Safe Unity Editor HTTP Köprüsü.
    /// - Ana Thread Görev Dağıtıcısı (EditorApplication.update + Win32 PostMessage Wakeup)
    /// - SerializedObject & SerializedProperty Dinamik Bağlama
    /// - Derleme & Domain Reload Yaşam Döngüsü Senkronizasyonu
    /// - Konsol Log ve Hata Yakalama Tamponu
    /// - Prefab & Asset Yönetimi
    /// - Dinamik C# Editor REPL / Kod Yürütme
    /// </summary>
    [InitializeOnLoad]
    public static class LaSefBridgeServer
    {
        private const int DEFAULT_PORT = 8088;
        private static HttpListener _listener;
        private static Thread _listenerThread;
        private static bool _isRunning = false;
        private static readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();
        private static IntPtr _mainWindowHandle = IntPtr.Zero;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
        private const uint WM_NULL = 0x0000;
        private const uint WM_TIMER = 0x0113;
        
        // Konsol Log Tamponu (Thread-safe)
        private static readonly List<LogEntry> _recentLogs = new List<LogEntry>();
        private static readonly object _logLock = new object();
        private const int MAX_LOGS = 100;

        // Derleme Durumu
        private static bool _isCompiling = false;
        private static readonly List<string> _compileErrors = new List<string>();
        private static bool _legacyRunnersCleaned = false;

        // Thread-safe Önbellek (Main thread dışından güvenle okunabilir)
        private static volatile string _cachedUnityVersion = "";
        private static volatile string _cachedProjectPath = "";
        private static volatile string _cachedActiveScene = "";
        private static volatile bool _cachedIsCompiling = false;
        private static volatile bool _cachedIsPlaying = false;
        private static volatile bool _cachedScriptCompilationFailed = false;

        [Serializable]
        public class LogEntry
        {
            public string type;
            public string message;
            public string stackTrace;
            public string timestamp;
        }

        static LaSefBridgeServer()
        {
            Application.runInBackground = true;
            try
            {
                _mainWindowHandle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;
            }
            catch { }
            EditorApplication.update += OnEditorUpdate;
            Application.logMessageReceivedThreaded += OnLogReceived;
            CompilationPipeline.compilationStarted += OnCompilationStarted;
            CompilationPipeline.compilationFinished += OnCompilationFinished;
            CompilationPipeline.assemblyCompilationFinished += OnAssemblyCompilationFinished;
            AssemblyReloadEvents.beforeAssemblyReload += StopServer;
            EditorApplication.quitting += StopServer;

            // Editör açıldığında veya derleme sonrası otomatik başlat
            StartServer(DEFAULT_PORT);
        }

        private static void WakeMainThread()
        {
            try
            {
                if (_mainWindowHandle == IntPtr.Zero)
                {
                    _mainWindowHandle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;
                }
                if (_mainWindowHandle != IntPtr.Zero)
                {
                    PostMessage(_mainWindowHandle, WM_NULL, IntPtr.Zero, IntPtr.Zero);
                    PostMessage(_mainWindowHandle, WM_TIMER, IntPtr.Zero, IntPtr.Zero);
                }
            }
            catch { }
        }

        [MenuItem("LaSef/🚀 Köprü Sunucusu (Bridge)/Yeniden Başlat (Restart)", false, 10)]
        public static void RestartMenu()
        {
            StopServer();
            StartServer(DEFAULT_PORT);
        }

        [MenuItem("LaSef/🚀 Köprü Sunucusu (Bridge)/Durdur (Stop)", false, 11)]
        public static void StopMenu()
        {
            StopServer();
        }

        public static void StartServer(int port)
        {
            if (_isRunning) return;

            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add($"http://127.0.0.1:{port}/");
                _listener.Prefixes.Add($"http://localhost:{port}/");
                _listener.Start();
                _isRunning = true;

                _listenerThread = new Thread(ListenLoop)
                {
                    IsBackground = true,
                    Name = "LaSefBridge_Listener"
                };
                _listenerThread.Start();

                Debug.Log($"<color=#00FFAA><b>[LaSef Köprüsü]</b></color> Canlı ve Dinlemede: http://127.0.0.1:{port}/");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[LaSef Köprüsü] Başlatılamadı (Port {port} dolu olabilir): {ex.Message}");
                _isRunning = false;
            }
        }

        public static void StopServer()
        {
            if (!_isRunning) return;
            _isRunning = false;

            try
            {
                _listener?.Stop();
                _listener?.Close();
            }
            catch { }
            Debug.Log("[LaSef Köprüsü] Durduruldu.");
        }

        private static void OnEditorUpdate()
        {
            try
            {
                if (string.IsNullOrEmpty(_cachedUnityVersion)) _cachedUnityVersion = Application.unityVersion;
                if (string.IsNullOrEmpty(_cachedProjectPath)) _cachedProjectPath = Application.dataPath;
                var sc = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
                _cachedActiveScene = sc.name;
                _cachedIsCompiling = EditorApplication.isCompiling;
                _cachedIsPlaying = EditorApplication.isPlaying;
                _cachedScriptCompilationFailed = EditorUtility.scriptCompilationFailed;

                if (!_legacyRunnersCleaned && !EditorApplication.isCompiling)
                {
                    _legacyRunnersCleaned = true;
                    CleanupLegacyDynamicRunners();
                }
            }
            catch { }

            // Ana thread üzerinde bekleyen istekleri tüket
            int processed = 0;
            while (_mainThreadQueue.TryDequeue(out var action) && processed < 20)
            {
                try
                {
                    action?.Invoke();
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[LaSef Köprüsü] Ana Thread Görev Hatası: {ex}");
                }
                processed++;
            }
        }

        private static void CleanupLegacyDynamicRunners()
        {
            try
            {
                string bridgeDir = Path.Combine(Application.dataPath, "Editor", "LaSefBridge");
                if (!Directory.Exists(bridgeDir)) return;

                bool deletedAny = false;
                foreach (var file in Directory.GetFiles(bridgeDir, "LaSefDynamicRunner_*"))
                {
                    try
                    {
                        if (file.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
                        {
                            string relPath = "Assets/Editor/LaSefBridge/" + Path.GetFileName(file);
                            if (!AssetDatabase.DeleteAsset(relPath))
                            {
                                File.Delete(file);
                            }
                            deletedAny = true;
                        }
                        else if (file.EndsWith(".meta", StringComparison.OrdinalIgnoreCase))
                        {
                            File.Delete(file);
                            deletedAny = true;
                        }
                    }
                    catch { }
                }

                if (deletedAny)
                {
                    AssetDatabase.Refresh();
                }
            }
            catch { }
        }

        private static void OnLogReceived(string condition, string stackTrace, LogType type)
        {
            if (string.IsNullOrEmpty(condition)) return;

            // Köprü iç mesajlarını ve eski dinamik çalıştırıcı gürültüsünü filtrele
            if (condition.Contains("LaSefDynamicRunner_") || condition.Contains("[LaSef Köprüsü]"))
                return;

            // Konsola düşen C# derleme hatalarını (Assembly-CSharp ve Assembly-CSharp-Editor dahil) yakala
            if (condition.Contains("error CS"))
            {
                lock (_compileErrors)
                {
                    if (!_compileErrors.Contains(condition))
                    {
                        _compileErrors.Add(condition);
                    }
                }
            }

            lock (_logLock)
            {
                _recentLogs.Add(new LogEntry
                {
                    type = type.ToString(),
                    message = condition,
                    stackTrace = stackTrace,
                    timestamp = DateTime.Now.ToString("HH:mm:ss.fff")
                });

                if (_recentLogs.Count > MAX_LOGS)
                {
                    _recentLogs.RemoveAt(0);
                }
            }
        }

        private static void OnCompilationStarted(object context)
        {
            _isCompiling = true;
            _cachedIsCompiling = true;
            lock (_compileErrors)
            {
                _compileErrors.Clear();
            }
        }

        private static void OnCompilationFinished(object context)
        {
            _isCompiling = false;
            _cachedIsCompiling = EditorApplication.isCompiling;
            lock (_compileErrors)
            {
                if (_compileErrors.Count > 0)
                {
                    _cachedScriptCompilationFailed = true;
                }
            }
            WakeMainThread();
        }

        private static void OnAssemblyCompilationFinished(string assemblyName, CompilerMessage[] messages)
        {
            _isCompiling = EditorApplication.isCompiling;
            lock (_compileErrors)
            {
                foreach (var msg in messages)
                {
                    if (msg.type == CompilerMessageType.Error)
                    {
                        if (msg.file != null && msg.file.Contains("LaSefDynamicRunner_"))
                            continue;

                        _cachedScriptCompilationFailed = true;
                        string formatted = $"[{assemblyName}] {msg.file}({msg.line},{msg.column}): {msg.message}";
                        if (!_compileErrors.Contains(formatted))
                        {
                            _compileErrors.Add(formatted);
                        }
                    }
                }
            }
        }

        private static void ListenLoop()
        {
            while (_isRunning && _listener != null && _listener.IsListening)
            {
                try
                {
                    var context = _listener.GetContext();
                    ThreadPool.QueueUserWorkItem(_ => HandleRequest(context));
                }
                catch (HttpListenerException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    if (_isRunning)
                        Debug.LogWarning($"[LaSef Köprüsü] Dinleme Hatası: {ex.Message}");
                }
            }
        }

        private static void HandleRequest(HttpListenerContext context)
        {
            var request = context.Request;
            var response = context.Response;

            // CORS İzinleri
            response.Headers.Add("Access-Control-Allow-Origin", "*");
            response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            response.Headers.Add("Access-Control-Allow-Headers", "Content-Type");

            if (request.HttpMethod == "OPTIONS")
            {
                response.StatusCode = 200;
                response.Close();
                return;
            }

            string path = request.Url.AbsolutePath.TrimEnd('/').ToLowerInvariant();
            string body = "";

            if (request.HasEntityBody)
            {
                using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                {
                    body = reader.ReadToEnd();
                }
            }

            // Durum kontrolü hemen arka planda cevaplanabilir
            if (path == "/status" || path == "")
            {
                var statusJson = GetStatusJson();
                SendJsonResponse(response, 200, statusJson);
                return;
            }

            if (path == "/console/logs")
            {
                var logsJson = GetLogsJson();
                SendJsonResponse(response, 200, logsJson);
                return;
            }

            if (path == "/console/clear")
            {
                var clearJson = HandleClearLogs();
                SendJsonResponse(response, 200, clearJson);
                return;
            }

            // Ana thread gerektiren işlemler
            using (var waitHandle = new ManualResetEvent(false))
            {
                string resultJson = "";
                int statusCode = 200;

                _mainThreadQueue.Enqueue(() =>
                {
                    try
                    {
                        resultJson = RouteMainThreadRequest(path, request.HttpMethod, body, out statusCode);
                    }
                    catch (Exception ex)
                    {
                        statusCode = 500;
                        resultJson = $"{{\"success\":false,\"error\":\"{EscapeJson(ex.Message)}\"}}";
                    }
                    finally
                    {
                        try { waitHandle.Set(); } catch { }
                    }
                });

                // Ana thread'i uyandır (Unity arka planda/odak dışındayken bile anında çalışmasını sağlar)
                WakeMainThread();

                // 15 saniye zaman aşımı ile ana thread'i bekle (her 200ms'de bir Win32 mesaj döngüsünü dürt)
                bool completed = false;
                for (int w = 0; w < 75; w++)
                {
                    if (waitHandle.WaitOne(200))
                    {
                        completed = true;
                        break;
                    }
                    WakeMainThread();
                }

                if (completed)
                {
                    SendJsonResponse(response, statusCode, resultJson);
                }
                else
                {
                    SendJsonResponse(response, 504, "{\"success\":false,\"error\":\"Main thread timeout (15s)\"}");
                }
            }
        }

        private static string RouteMainThreadRequest(string path, string method, string body, out int statusCode)
        {
            statusCode = 200;

            if (_isCompiling || EditorApplication.isCompiling)
            {
                return "{\"success\":false,\"compiling\":true,\"message\":\"Unity su anda kod derliyor (domain reload). Lutfen bekleyin.\"}";
            }

            // PlayMode geçişi sırasında sahne yükleme/boşaltma yarım kalabileceğinden geçici bekleme bildir
            if (EditorApplication.isPlaying != EditorApplication.isPlayingOrWillChangePlaymode && path != "/playmode/set")
            {
                return "{\"success\":false,\"transitioning\":true,\"message\":\"Unity PlayMode gecisi tamamlaniyor. Lutfen kisa sure bekleyin.\"}";
            }

            switch (path)
            {
                case "/hierarchy":
                    return HandleGetHierarchy();

                case "/gameobject/create":
                    return HandleCreateGameObject(body);

                case "/gameobject/inspect":
                    return HandleInspectGameObject(body);

                case "/gameobject/delete":
                    return HandleDeleteGameObject(body);

                case "/component/add":
                    return HandleAddComponent(body);

                case "/property/set":
                    return HandleSetProperty(body);

                case "/prefab/create":
                    return HandleCreatePrefab(body);

                case "/prefab/instantiate":
                    return HandleInstantiatePrefab(body);

                case "/execute_csharp":
                    return HandleExecuteCSharp(body);

                case "/scene/save":
                    return HandleSaveScene();

                case "/playmode/set":
                    return HandleSetPlayMode(body);

                case "/camera/capture":
                    return HandleCaptureScreenshot(body);

                case "/asset/refresh":
                    AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                    return "{\"success\":true,\"message\":\"AssetDatabase refreshed.\"}";

                case "/console/clear":
                    return HandleClearLogs();

                default:
                    statusCode = 404;
                    return $"{{\"success\":false,\"error\":\"Bilinmeyen endpoint: {path}\"}}";
            }
        }

        // ==========================================
        // ENDPOINT HANDLERS
        // ==========================================

        private static string HandleGetHierarchy()
        {
            var activeScene = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
            var roots = (activeScene.IsValid() && activeScene.isLoaded) ? activeScene.GetRootGameObjects() : new GameObject[0];
            
            if (roots == null || roots.Length == 0)
            {
                var allRoots = new List<GameObject>();
                for (int s = 0; s < UnityEngine.SceneManagement.SceneManager.sceneCount; s++)
                {
                    var sc = UnityEngine.SceneManagement.SceneManager.GetSceneAt(s);
                    if (sc.isLoaded)
                    {
                        allRoots.AddRange(sc.GetRootGameObjects());
                    }
                }
                if (allRoots.Count > 0)
                {
                    roots = allRoots.ToArray();
                }
                else
                {
                    var allGos = UnityEngine.Object.FindObjectsByType<GameObject>(FindObjectsInactive.Include, FindObjectsSortMode.None);
                    var orphanRoots = new List<GameObject>();
                    foreach (var go in allGos)
                    {
                        if (go != null && go.transform.parent == null)
                            orphanRoots.Add(go);
                    }
                    roots = orphanRoots.ToArray();
                }
            }

            var sb = new StringBuilder();
            sb.Append("{\"success\":true,\"scene\":\"").Append(EscapeJson(activeScene.name)).Append("\",\"root_count\":").Append(roots.Length).Append(",\"nodes\":[");

            for (int i = 0; i < roots.Length; i++)
            {
                if (i > 0) sb.Append(",");
                SerializeGameObjectNode(roots[i], sb, depth: 0, maxDepth: 4);
            }
            sb.Append("]}");
            return sb.ToString();
        }

        private static void SerializeGameObjectNode(GameObject go, StringBuilder sb, int depth, int maxDepth)
        {
            sb.Append("{");
            sb.Append("\"id\":").Append(go.GetInstanceID()).Append(",");
            sb.Append("\"name\":\"").Append(EscapeJson(go.name)).Append("\",");
            sb.Append("\"active\":").Append(go.activeSelf.ToString().ToLower()).Append(",");
            sb.Append("\"tag\":\"").Append(EscapeJson(go.tag)).Append("\",");
            sb.Append("\"layer\":\"").Append(EscapeJson(LayerMask.LayerToName(go.layer))).Append("\",");
            
            var pos = go.transform.position;
            var inv = System.Globalization.CultureInfo.InvariantCulture;
            sb.Append("\"pos\":{\"x\":").Append(pos.x.ToString("F2", inv))
              .Append(",\"y\":").Append(pos.y.ToString("F2", inv))
              .Append(",\"z\":").Append(pos.z.ToString("F2", inv)).Append("},");

            // Bileşenler
            var comps = go.GetComponents<Component>();
            sb.Append("\"components\":[");
            int compCount = 0;
            foreach (var c in comps)
            {
                if (c == null) continue;
                if (compCount > 0) sb.Append(",");
                sb.Append("\"").Append(EscapeJson(c.GetType().Name)).Append("\"");
                compCount++;
            }
            sb.Append("],");

            // Çocuklar
            sb.Append("\"child_count\":").Append(go.transform.childCount);
            if (depth < maxDepth && go.transform.childCount > 0)
            {
                sb.Append(",\"children\":[");
                for (int i = 0; i < go.transform.childCount; i++)
                {
                    if (i > 0) sb.Append(",");
                    SerializeGameObjectNode(go.transform.GetChild(i).gameObject, sb, depth + 1, maxDepth);
                }
                sb.Append("]");
            }
            sb.Append("}");
        }

        private static string HandleCreateGameObject(string body)
        {
            string name = ExtractStringField(body, "name") ?? "GameObject_Ajan";
            string primitive = ExtractStringField(body, "primitive_type");
            string parentPath = ExtractStringField(body, "parent");

            GameObject go;
            if (!string.IsNullOrEmpty(primitive))
            {
                if (Enum.TryParse<PrimitiveType>(primitive, true, out var pType))
                    go = GameObject.CreatePrimitive(pType);
                else
                    go = new GameObject(name);
            }
            else
            {
                go = new GameObject(name);
            }

            go.name = name;

            if (!string.IsNullOrEmpty(parentPath))
            {
                var parentGo = GameObject.Find(parentPath);
                if (parentGo != null)
                {
                    go.transform.SetParent(parentGo.transform, false);
                }
            }

            // Pozisyon, Rotasyon, Boyut varsa ayarla
            float px = ExtractFloatField(body, "px", 0f);
            float py = ExtractFloatField(body, "py", 0f);
            float pz = ExtractFloatField(body, "pz", 0f);
            go.transform.position = new Vector3(px, py, pz);

            float sx = ExtractFloatField(body, "sx", 1f);
            float sy = ExtractFloatField(body, "sy", 1f);
            float sz = ExtractFloatField(body, "sz", 1f);
            go.transform.localScale = new Vector3(sx, sy, sz);

            Undo.RegisterCreatedObjectUndo(go, "LaSef Ajan Olusturdu");
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());

            return $"{{\"success\":true,\"id\":{go.GetInstanceID()},\"name\":\"{EscapeJson(go.name)}\",\"message\":\"GameObject basariyla olusturuldu.\"}}";
        }

        private static string HandleInspectGameObject(string body)
        {
            string target = ExtractStringField(body, "target");
            GameObject go = FindTargetGameObject(target);

            if (go == null)
            {
                return $"{{\"success\":false,\"error\":\"Hedef bulunamadi: '{EscapeJson(target)}'\"}}";
            }

            var sb = new StringBuilder();
            sb.Append("{\"success\":true,\"id\":").Append(go.GetInstanceID());
            sb.Append(",\"name\":\"").Append(EscapeJson(go.name)).Append("\"");
            sb.Append(",\"tag\":\"").Append(EscapeJson(go.tag)).Append("\"");
            sb.Append(",\"layer\":\"").Append(EscapeJson(LayerMask.LayerToName(go.layer))).Append("\"");
            
            var comps = go.GetComponents<Component>();
            sb.Append(",\"components\":[");
            for (int i = 0; i < comps.Length; i++)
            {
                var c = comps[i];
                if (c == null) continue;
                if (i > 0) sb.Append(",");
                sb.Append("{\"type\":\"").Append(EscapeJson(c.GetType().FullName)).Append("\",\"properties\":{");

                var so = new SerializedObject(c);
                var prop = so.GetIterator();
                int propCount = 0;
                if (prop.NextVisible(true))
                {
                    do
                    {
                        if (prop.name == "m_Script") continue;
                        if (propCount > 0) sb.Append(",");
                        sb.Append("\"").Append(EscapeJson(prop.name)).Append("\":\"");
                        sb.Append(EscapeJson(GetPropertyValueString(prop)));
                        sb.Append("\"");
                        propCount++;
                        if (propCount > 25) break; // Token korumasi
                    } while (prop.NextVisible(false));
                }
                sb.Append("}}");
            }
            sb.Append("]}");
            return sb.ToString();
        }

        private static string HandleDeleteGameObject(string body)
        {
            string target = ExtractStringField(body, "target");
            GameObject go = FindTargetGameObject(target);
            if (go == null) return $"{{\"success\":false,\"error\":\"Silinecek obje bulunamadi: '{target}'\"}}";

            Undo.DestroyObjectImmediate(go);
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            return $"{{\"success\":true,\"message\":\"'{EscapeJson(target)}' silindi.\"}}";
        }

        private static string HandleAddComponent(string body)
        {
            string target = ExtractStringField(body, "target");
            string compName = ExtractStringField(body, "component");

            GameObject go = FindTargetGameObject(target);
            if (go == null) return $"{{\"success\":false,\"error\":\"Hedef obje bulunamadi: '{target}'\"}}";

            Type compType = FindType(compName);
            if (compType == null)
            {
                return $"{{\"success\":false,\"error\":\"Bilesen turu bulunamadi: '{compName}'. Script henuz derlenmemis olabilir.\"}}";
            }

            Undo.RecordObject(go, "LaSef Bilesen Ekle");
            Component added = go.AddComponent(compType);
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());

            return $"{{\"success\":true,\"message\":\"'{compName}' bileseni '{go.name}' nesnesine basariyla eklendi.\"}}";
        }

        private static string HandleSetProperty(string body)
        {
            string target = ExtractStringField(body, "target");
            string compName = ExtractStringField(body, "component");
            string propName = ExtractStringField(body, "property");
            string valStr = ExtractStringField(body, "value");
            bool isRef = ExtractBoolField(body, "is_reference", false);

            GameObject go = FindTargetGameObject(target);
            if (go == null) return $"{{\"success\":false,\"error\":\"Hedef obje bulunamadi: '{target}'\"}}";

            Component comp = null;
            if (!string.IsNullOrEmpty(compName))
            {
                Type compType = FindType(compName);
                if (compType != null) comp = go.GetComponent(compType);
            }
            else
            {
                comp = go.transform;
            }

            if (comp == null) return $"{{\"success\":false,\"error\":\"'{compName}' bileseni '{target}' uzerinde bulunamadi.\"}}";

            var so = new SerializedObject(comp);
            var prop = so.FindProperty(propName);
            if (prop == null) return $"{{\"success\":false,\"error\":\"Property '{propName}' bilesende bulunamadi.\"}}";

            Undo.RecordObject(comp, $"Set Property {propName}");

            if (isRef)
            {
                // Obje referansı bağlama (GameObject, Component, Asset)
                GameObject refGo = FindTargetGameObject(valStr);
                if (refGo != null)
                {
                    if (prop.propertyType == SerializedPropertyType.ObjectReference)
                    {
                        if (prop.type.Contains("GameObject"))
                            prop.objectReferenceValue = refGo;
                        else if (prop.type.Contains("Transform"))
                            prop.objectReferenceValue = refGo.transform;
                        else
                        {
                            var subComp = refGo.GetComponent(prop.type.Replace("PPtr<", "").Replace(">", "").Trim('$'));
                            prop.objectReferenceValue = subComp != null ? subComp : (UnityEngine.Object)refGo;
                        }
                    }
                }
                else
                {
                    // Asset Database üzerinden ara
                    var asset = AssetDatabase.LoadMainAssetAtPath(valStr);
                    if (asset != null) prop.objectReferenceValue = asset;
                    else return $"{{\"success\":false,\"error\":\"Referans nesne bulunamadi: '{valStr}'\"}}";
                }
            }
            else
            {
                // Primitif Değer Atamaları
                switch (prop.propertyType)
                {
                    case SerializedPropertyType.Integer:
                        if (int.TryParse(valStr, out int iVal)) prop.intValue = iVal;
                        break;
                    case SerializedPropertyType.Boolean:
                        if (bool.TryParse(valStr, out bool bVal)) prop.boolValue = bVal;
                        break;
                    case SerializedPropertyType.Float:
                        if (float.TryParse(valStr, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float fVal)) prop.floatValue = fVal;
                        break;
                    case SerializedPropertyType.String:
                        prop.stringValue = valStr;
                        break;
                    case SerializedPropertyType.Vector2:
                        var v2 = ParseVector2(valStr);
                        prop.vector2Value = v2;
                        break;
                    case SerializedPropertyType.Vector3:
                        var v3 = ParseVector3(valStr);
                        prop.vector3Value = v3;
                        break;
                    default:
                        return $"{{\"success\":false,\"error\":\"Desteklenmeyen Property Type: {prop.propertyType}\"}}";
                }
            }

            so.ApplyModifiedProperties();
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());

            return $"{{\"success\":true,\"message\":\"'{propName}' degeri basariyla guncellendi.\"}}";
        }

        private static string HandleCreatePrefab(string body)
        {
            string target = ExtractStringField(body, "target");
            string assetPath = ExtractStringField(body, "asset_path") ?? $"Assets/Prefabs/{target}.prefab";

            GameObject go = FindTargetGameObject(target);
            if (go == null) return $"{{\"success\":false,\"error\":\"Hedef obje bulunamadi: '{target}'\"}}";

            string dir = Path.GetDirectoryName(assetPath);
            if (!Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
                AssetDatabase.Refresh();
            }

            GameObject prefab = PrefabUtility.SaveAsPrefabAssetAndConnect(go, assetPath, InteractionMode.UserAction);
            if (prefab != null)
            {
                AssetDatabase.SaveAssets();
                return $"{{\"success\":true,\"asset_path\":\"{assetPath}\",\"message\":\"Prefab basariyla olusturuldu.\"}}";
            }
            return $"{{\"success\":false,\"error\":\"Prefab kaydedilemedi.\"}}";
        }

        private static string HandleInstantiatePrefab(string body)
        {
            string assetPath = ExtractStringField(body, "asset_path");
            string parent = ExtractStringField(body, "parent");

            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (prefab == null) return $"{{\"success\":false,\"error\":\"Prefab asset bulunamadi: '{assetPath}'\"}}";

            GameObject instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            if (!string.IsNullOrEmpty(parent))
            {
                var pGo = FindTargetGameObject(parent);
                if (pGo != null) instance.transform.SetParent(pGo.transform, false);
            }

            Undo.RegisterCreatedObjectUndo(instance, "Instantiate Prefab");
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());

            return $"{{\"success\":true,\"id\":{instance.GetInstanceID()},\"name\":\"{instance.name}\"}}";
        }

        private static string HandleExecuteCSharp(string body)
        {
            string code = ExtractStringField(body, "code")?.Trim();
            if (string.IsNullOrEmpty(code)) return "{\"success\":false,\"error\":\"Kod bos olamaz.\"}";

            if (EditorUtility.scriptCompilationFailed)
            {
                return "{\"success\":false,\"error\":\"Unity projesinde derleme hatasi (scriptCompilationFailed) mevcut. Once C# derleme hatalarini giderin.\"}";
            }

            // 1. Doğrudan Reflection ile Metot Çağrısını Dene (Örn: FPSArenaSceneBuilder.BuildScene(); veya LaSef.Editor.NeonArenaSceneBuilder.BuildScene();)
            string cleanCode = code.TrimEnd(';', ' ', '\n', '\r');
            int lastParen = cleanCode.IndexOf('(');
            string methodTarget = lastParen > 0 ? cleanCode.Substring(0, lastParen).Trim() : cleanCode;
            int lastDot = methodTarget.LastIndexOf('.');
            if (lastDot > 0)
            {
                string typeName = methodTarget.Substring(0, lastDot).Trim();
                string methodName = methodTarget.Substring(lastDot + 1).Trim();

                Type targetType = FindType(typeName);
                if (targetType != null)
                {
                    var method = targetType.GetMethod(methodName, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
                    if (method != null)
                    {
                        try
                        {
                            object res = method.Invoke(null, null);
                            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
                            string outStr = res != null ? res.ToString() : "OK";
                            return $"{{\"success\":true,\"output\":\"{EscapeJson(outStr)}\"}}";
                        }
                        catch (Exception ex)
                        {
                            var inner = ex.InnerException ?? ex;
                            string stack = inner.StackTrace ?? "";
                            if (stack.Length > 450) stack = stack.Substring(0, 450);
                            return $"{{\"success\":false,\"error\":\"Metot yurutme hatasi: {EscapeJson(inner.GetType().Name + ": " + inner.Message + " | " + stack)}\"}}";
                        }
                    }
                    return $"{{\"success\":false,\"error\":\"'{EscapeJson(typeName)}' sinifinda static '{EscapeJson(methodName)}' metodu bulunamadi.\"}}";
                }
            }

            // 2. EditorApplication.ExecuteMenuItem kontrolü
            if (code.Contains("ExecuteMenuItem"))
            {
                int startQuote = code.IndexOf('"');
                int endQuote = code.LastIndexOf('"');
                if (startQuote >= 0 && endQuote > startQuote)
                {
                    string menuItem = code.Substring(startQuote + 1, endQuote - startQuote - 1);
                    bool menuRes = EditorApplication.ExecuteMenuItem(menuItem);
                    return $"{{\"success\":{menuRes.ToString().ToLower()},\"output\":\"ExecuteMenuItem({EscapeJson(menuItem)}) = {menuRes}\"}}";
                }
            }

            // Not: Geçici LaSefDynamicRunner_*.cs dosyası oluşturma yöntemi CS2001 ve yetim .meta
            // hatalarına yol açtığı için kaldırılmıştır. Tüm çağrılar Reflection veya MenuItem üzerinden yürütülür.
            return $"{{\"success\":false,\"error\":\"Hedef sinif veya metot derlenmis assembly icinde bulunamadi: '{EscapeJson(cleanCode)}'. Editor scriptinin hatasiz derlendiginden emin olun.\"}}";
        }

        private static void CleanMissingScriptsInScene()
        {
            try
            {
                if (EditorApplication.isPlaying) return;
                bool anyRemoved = false;
                foreach (var go in UnityEngine.Object.FindObjectsByType<GameObject>(FindObjectsSortMode.None))
                {
                    if (go != null && GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(go) > 0)
                    {
                        GameObjectUtility.RemoveMonoBehavioursWithMissingScript(go);
                        anyRemoved = true;
                    }
                }
                if (anyRemoved)
                {
                    EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
                }
            }
            catch { }
        }

        private static string HandleSaveScene()
        {
            CleanMissingScriptsInScene();
            var scene = EditorSceneManager.GetActiveScene();
            if (string.IsNullOrEmpty(scene.path))
            {
                string scenesDir = "Assets/Scenes";
                if (!AssetDatabase.IsValidFolder(scenesDir))
                {
                    AssetDatabase.CreateFolder("Assets", "Scenes");
                }
                string fallbackPath = $"{scenesDir}/LaSefAutoScene.unity";
                bool savedNew = EditorSceneManager.SaveScene(scene, fallbackPath);
                AssetDatabase.SaveAssets();
                return $"{{\"success\":{savedNew.ToString().ToLower()},\"scene\":\"{EscapeJson(scene.name)}\",\"path\":\"{EscapeJson(fallbackPath)}\"}}";
            }
            bool saved = EditorSceneManager.SaveScene(scene);
            AssetDatabase.SaveAssets();
            return $"{{\"success\":{saved.ToString().ToLower()},\"scene\":\"{EscapeJson(scene.name)}\",\"path\":\"{EscapeJson(scene.path)}\"}}";
        }

        private static string HandleSetPlayMode(string body)
        {
            bool play = ExtractBoolField(body, "play", true);
            if (play)
            {
                CleanMissingScriptsInScene();
                // PlayMode'a geçerken kirli (kaydedilmemiş) sahnenin objelerinin kaybolmaması için otomatik kaydet
                var activeScene = EditorSceneManager.GetActiveScene();
                if (activeScene.isDirty)
                {
                    HandleSaveScene();
                }
            }
            EditorApplication.isPlaying = play;
            return $"{{\"success\":true,\"is_playing\":{play.ToString().ToLower()},\"transitioning\":{(EditorApplication.isPlaying != EditorApplication.isPlayingOrWillChangePlaymode).ToString().ToLower()}}}";
        }

        private static string HandleCaptureScreenshot(string body = "")
        {
            Camera cam = null;
            string camName = "SceneView";

            // Eğer oyun oynatılıyorsa veya özellikle istenmişse Game kamerası (Camera.main) önceliklidir
            bool preferGame = ExtractBoolField(body, "game_view", EditorApplication.isPlaying);
            if (preferGame && Camera.main != null)
            {
                cam = Camera.main;
                camName = "Camera.main";
            }
            else if (preferGame && Camera.allCamerasCount > 0)
            {
                cam = Camera.allCameras[0];
                camName = cam.name;
            }
            else if (preferGame)
            {
                cam = UnityEngine.Object.FindFirstObjectByType<Camera>();
                if (cam != null) camName = cam.name;
            }

            // Game kamerası yoksa SceneView kamerasına dön
            if (cam == null)
            {
                var sceneView = SceneView.lastActiveSceneView;
                if (sceneView == null && SceneView.sceneViews.Count > 0)
                    sceneView = (SceneView)SceneView.sceneViews[0];

                if (sceneView != null && sceneView.camera != null)
                {
                    cam = sceneView.camera;
                    camName = "SceneView";
                }
            }

            if (cam != null)
            {
                int width = 640;
                int height = 360;
                var rt = new RenderTexture(width, height, 24);
                var prevTarget = cam.targetTexture;

                // ScreenSpaceOverlay Canvas'ları geçici olarak ScreenSpaceCamera moduna al ki cam.Render() UI'ı da yakalasın
                var overlayCanvases = new List<Canvas>();
                foreach (var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsSortMode.None))
                {
                    if (c != null && c.isActiveAndEnabled && c.renderMode == RenderMode.ScreenSpaceOverlay)
                    {
                        overlayCanvases.Add(c);
                        c.renderMode = RenderMode.ScreenSpaceCamera;
                        c.worldCamera = cam;
                        c.planeDistance = Mathf.Max(cam.nearClipPlane + 0.05f, 0.25f);
                    }
                }
                if (overlayCanvases.Count > 0)
                {
                    Canvas.ForceUpdateCanvases();
                }

                cam.targetTexture = rt;
                cam.Render();

                foreach (var c in overlayCanvases)
                {
                    if (c != null)
                    {
                        c.renderMode = RenderMode.ScreenSpaceOverlay;
                        c.worldCamera = null;
                    }
                }

                RenderTexture.active = rt;
                var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();

                cam.targetTexture = prevTarget;
                RenderTexture.active = null;
                UnityEngine.Object.DestroyImmediate(rt);

                byte[] bytes = tex.EncodeToJPG(75);
                UnityEngine.Object.DestroyImmediate(tex);
                string b64 = Convert.ToBase64String(bytes);

                return $"{{\"success\":true,\"format\":\"image/jpeg\",\"camera\":\"{camName}\",\"is_playing\":{EditorApplication.isPlaying.ToString().ToLower()},\"data\":\"{b64}\"}}";
            }

            return "{\"success\":false,\"error\":\"Aktif SceneView veya Camera bulunamadi.\"}";
        }

        // ==========================================
        // YARDIMCI VE JSON FONKSİYONLARI
        // ==========================================

        private static string GetStatusJson()
        {
            bool compilingNow = _isCompiling || _cachedIsCompiling;
            int pendingQueue = _mainThreadQueue.Count;
            if (pendingQueue > 0)
            {
                WakeMainThread();
            }

            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append("\"online\":true,");
            sb.Append("\"unity_version\":\"").Append(EscapeJson(_cachedUnityVersion)).Append("\",");
            sb.Append("\"project_path\":\"").Append(EscapeJson(_cachedProjectPath)).Append("\",");
            sb.Append("\"active_scene\":\"").Append(EscapeJson(_cachedActiveScene)).Append("\",");
            sb.Append("\"is_compiling\":").Append(compilingNow.ToString().ToLower()).Append(",");
            sb.Append("\"pending_queue\":").Append(pendingQueue).Append(",");
            sb.Append("\"is_playing\":").Append(_cachedIsPlaying.ToString().ToLower()).Append(",");
            sb.Append("\"script_compilation_failed\":").Append(_cachedScriptCompilationFailed.ToString().ToLower()).Append(",");

            var allErrors = new List<string>();
            lock (_compileErrors)
            {
                allErrors.AddRange(_compileErrors);
            }
            lock (_logLock)
            {
                foreach (var l in _recentLogs)
                {
                    if (!string.IsNullOrEmpty(l.message) && l.message.Contains("error CS") && !l.message.Contains("LaSefDynamicRunner_"))
                    {
                        if (!allErrors.Contains(l.message))
                            allErrors.Add(l.message);
                    }
                }
            }
            if (_cachedScriptCompilationFailed && allErrors.Count == 0)
            {
                allErrors.Add("[Compiler] Unity Editor script compilation failed (EditorUtility.scriptCompilationFailed = true).");
            }

            sb.Append("\"compile_errors\":[");
            for (int i = 0; i < allErrors.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append("\"").Append(EscapeJson(allErrors[i])).Append("\"");
            }
            sb.Append("]");
            sb.Append("}");
            return sb.ToString();
        }

        private static string GetLogsJson()
        {
            var sb = new StringBuilder();
            sb.Append("{\"success\":true,\"logs\":[");
            lock (_logLock)
            {
                for (int i = 0; i < _recentLogs.Count; i++)
                {
                    if (i > 0) sb.Append(",");
                    var l = _recentLogs[i];
                    sb.Append("{\"type\":\"").Append(l.type)
                      .Append("\",\"message\":\"").Append(EscapeJson(l.message))
                      .Append("\",\"stackTrace\":\"").Append(EscapeJson(l.stackTrace))
                      .Append("\",\"time\":\"").Append(l.timestamp).Append("\"}");
                }
            }
            sb.Append("]}");
            return sb.ToString();
        }

        private static string HandleClearLogs()
        {
            lock (_logLock)
            {
                _recentLogs.Clear();
            }
            lock (_compileErrors)
            {
                _compileErrors.Clear();
            }
            return "{\"success\":true,\"message\":\"Loglar ve derleme hatalari temizlendi.\"}";
        }

        private static void SendJsonResponse(HttpListenerResponse response, int statusCode, string json)
        {
            try
            {
                byte[] bytes = Encoding.UTF8.GetBytes(json);
                response.ContentType = "application/json; charset=utf-8";
                response.StatusCode = statusCode;
                response.ContentLength64 = bytes.Length;
                response.OutputStream.Write(bytes, 0, bytes.Length);
                response.OutputStream.Flush();
            }
            catch { }
            finally
            {
                try { response.Close(); } catch { }
            }
        }

        private static GameObject FindTargetGameObject(string target)
        {
            if (string.IsNullOrEmpty(target)) return null;

            if (int.TryParse(target, out int instanceId))
            {
                var obj = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
                if (obj != null) return obj;
            }

            return GameObject.Find(target);
        }

        private static Type FindType(string typeName)
        {
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                var type = assembly.GetType(typeName);
                if (type != null) return type;
            }
            // Namespace'siz arama
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                foreach (var type in assembly.GetTypes())
                {
                    if (type.Name.Equals(typeName, StringComparison.OrdinalIgnoreCase))
                        return type;
                }
            }
            return null;
        }

        private static string GetPropertyValueString(SerializedProperty prop)
        {
            var inv = System.Globalization.CultureInfo.InvariantCulture;
            switch (prop.propertyType)
            {
                case SerializedPropertyType.Integer: return prop.intValue.ToString(inv);
                case SerializedPropertyType.Boolean: return prop.boolValue.ToString();
                case SerializedPropertyType.Float: return prop.floatValue.ToString("F3", inv);
                case SerializedPropertyType.String: return prop.stringValue;
                case SerializedPropertyType.ObjectReference: return prop.objectReferenceValue != null ? prop.objectReferenceValue.name : "null";
                case SerializedPropertyType.Enum: return prop.enumDisplayNames.Length > prop.enumValueIndex && prop.enumValueIndex >= 0 ? prop.enumDisplayNames[prop.enumValueIndex] : prop.enumValueIndex.ToString(inv);
                case SerializedPropertyType.Vector2: return $"{prop.vector2Value.x.ToString("F2", inv)},{prop.vector2Value.y.ToString("F2", inv)}";
                case SerializedPropertyType.Vector3: return $"{prop.vector3Value.x.ToString("F2", inv)},{prop.vector3Value.y.ToString("F2", inv)},{prop.vector3Value.z.ToString("F2", inv)}";
                default: return $"[{prop.propertyType}]";
            }
        }

        private static Vector2 ParseVector2(string s)
        {
            var p = s.Split(',');
            if (p.Length >= 2 && 
                float.TryParse(p[0], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float x) && 
                float.TryParse(p[1], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float y))
                return new Vector2(x, y);
            return Vector2.zero;
        }

        private static Vector3 ParseVector3(string s)
        {
            var p = s.Split(',');
            if (p.Length >= 3 && 
                float.TryParse(p[0], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float x) && 
                float.TryParse(p[1], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float y) && 
                float.TryParse(p[2], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float z))
                return new Vector3(x, y, z);
            return Vector3.zero;
        }

        private static string ExtractStringField(string json, string field)
        {
            if (string.IsNullOrEmpty(json)) return null;
            var pattern = $"\"{System.Text.RegularExpressions.Regex.Escape(field)}\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"";
            var match = System.Text.RegularExpressions.Regex.Match(json, pattern);
            if (!match.Success) return null;
            string raw = match.Groups[1].Value;
            if (!raw.Contains("\\")) return raw;

            var sb = new StringBuilder(raw.Length);
            for (int i = 0; i < raw.Length; i++)
            {
                char ch = raw[i];
                if (ch == '\\' && i + 1 < raw.Length)
                {
                    char next = raw[++i];
                    switch (next)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        default: sb.Append(next); break;
                    }
                }
                else
                {
                    sb.Append(ch);
                }
            }
            return sb.ToString();
        }

        private static float ExtractFloatField(string json, string field, float defVal = 0f)
        {
            if (string.IsNullOrEmpty(json)) return defVal;
            var pattern = $"\"{field}\"\\s*:\\s*(-?[0-9\\.]+)";
            var match = System.Text.RegularExpressions.Regex.Match(json, pattern);
            if (match.Success && float.TryParse(match.Groups[1].Value, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float val))
                return val;
            return defVal;
        }

        private static bool ExtractBoolField(string json, string field, bool defVal = false)
        {
            if (string.IsNullOrEmpty(json)) return defVal;
            var pattern = $"\"{field}\"\\s*:\\s*(true|false)";
            var match = System.Text.RegularExpressions.Regex.Match(json, pattern, System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (match.Success) return match.Groups[1].Value.ToLower() == "true";
            return defVal;
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("\\", "\\\\")
                    .Replace("\"", "\\\"")
                    .Replace("\r", "\\r")
                    .Replace("\n", "\\n")
                    .Replace("\t", "\\t");
        }
    }
}
#endif
