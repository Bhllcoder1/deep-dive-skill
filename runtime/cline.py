"""
Cline / Roo Code Runtime.
MCP tabanlı CLI. Web search için MCP server gerekli.
Eğer MCP web search server varsa onu kullanır, yoksa generic fallback.
"""

import os
from .generic import GenericRuntime


class ClineRuntime(GenericRuntime):
    @property
    def name(self) -> str:
        return "cline"

    def setup(self) -> bool:
        result = super().setup()
        if result:
            # MCP web search server var mı kontrol et (ileride)
            mcp_search = os.environ.get("MCP_WEB_SEARCH_URL", "")
            if mcp_search:
                print(f"[cline] ✅ MCP web search server: {mcp_search}")
            else:
                print("[cline] ⚠ MCP web search server bulunamadı, DDG scraping kullanılacak")
        return result
