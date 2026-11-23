
import asyncio
import json
import os
import threading
from typing import Any, Dict, List, Optional


class MCPClientManager:
    """Standart Model Context Protocol (MCP) stdio istemci yöneticisi."""

    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = workspace_dir or os.getcwd()

    def discover_servers(self, extra_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Çalışma alanı ve proje kökündeki .mcp.json dosyalarından MCP sunucularını okur."""
        servers: Dict[str, Dict[str, Any]] = {}
        search_dirs = [
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.workspace_dir,
        ]
        if extra_dir and extra_dir not in search_dirs:
            search_dirs.append(extra_dir)

        for d in search_dirs:
            if not d:
                continue
            cfg_path = os.path.join(d, ".mcp.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for name, spec in (data.get("mcpServers") or {}).items():
                        if isinstance(spec, dict) and spec.get("command"):
                            servers[name] = spec
                except Exception:
                    pass
        return servers

    def _run_coro(self, coro, timeout: float = 20.0):
        result: Dict[str, Any] = {}

        def _runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:
                result["error"] = exc

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            raise TimeoutError(f"MCP işlemi zaman aşımına uğradı ({timeout:.0f}s)")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    async def _list_tools_async(self, spec: Dict[str, Any]) -> List[Dict[str, str]]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = os.environ.copy()
        if isinstance(spec.get("env"), dict):
            env.update({str(k): str(v) for k, v in spec["env"].items()})

        params = StdioServerParameters(
            command=spec["command"],
            args=list(spec.get("args") or []),
            env=env,
            cwd=spec.get("cwd") or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
                return [
                    {"name": t.name, "description": (t.description or "")[:200]}
                    for t in (resp.tools or [])
                ]

    async def _call_tool_async(self, spec: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]) -> str:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = os.environ.copy()
        if isinstance(spec.get("env"), dict):
            env.update({str(k): str(v) for k, v in spec["env"].items()})

        params = StdioServerParameters(
            command=spec["command"],
            args=list(spec.get("args") or []),
            env=env,
            cwd=spec.get("cwd") or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.call_tool(tool_name, arguments=arguments or {})
                texts = []
                for item in (resp.content or []):
                    txt = getattr(item, "text", None)
                    texts.append(txt if txt is not None else str(item))
                return "\n".join(texts)

    def list_tools_sync(self, server_name: str, extra_dir: Optional[str] = None, timeout: float = 20.0) -> List[Dict[str, str]]:
        servers = self.discover_servers(extra_dir=extra_dir)
        if server_name not in servers:
            raise ValueError(f"'{server_name}' adlı MCP sunucusu .mcp.json içinde bulunamadı.")
        return self._run_coro(self._list_tools_async(servers[server_name]), timeout=timeout)

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None, extra_dir: Optional[str] = None, timeout: float = 30.0) -> str:
        servers = self.discover_servers(extra_dir=extra_dir)
        if server_name not in servers:
            raise ValueError(f"'{server_name}' adlı MCP sunucusu .mcp.json içinde bulunamadı.")
        return self._run_coro(self._call_tool_async(servers[server_name], tool_name, arguments or {}), timeout=timeout)
