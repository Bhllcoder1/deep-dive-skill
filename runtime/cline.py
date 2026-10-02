"""
Cline / Roo Code Runtime.
MCP tabanlı CLI. Web search için MCP server gerekli.
Eğer MCP web search server varsa onu kullanır, yoksa generic fallback.
"""

import os
from core.logs import get_logger

from .generic import GenericRuntime


_LOG = get_logger("runtime.cline")


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
                _LOG.info(f"[cline] ✅ MCP web search server: {mcp_search}")
            else:
                _LOG.warning("[cline] ⚠ MCP web search server bulunamadı, DDG scraping kullanılacak")
        return result
