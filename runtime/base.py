"""
Base Runtime Interface.
Her platform adaptörü bu interface'i uygulamak ZORUNDADIR.
Her platform kendi doğal API'sini ve gücünü kullanır.

Omnigent mimarisinden esinlenen capability modeli:
  IntegrationMode: SDK_IN_PROCESS, CLI_SUBPROCESS, NATIVE_TUI, NATIVE_SERVER
  Elicitation: NONE, HOOK, APPROVAL_MIRROR
  ModelFamily: CLAUDE, GPT, GEMINI, MULTI, DEEPSEEK, KIMI, QWEN
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class IntegrationMode(str, Enum):
    """Platformun vendor agent'ı nasıl çalıştırdığı."""
    CLI_SUBPROCESS = "cli-subprocess"
    SDK_IN_PROCESS = "sdk-in-process"
    NATIVE_TUI = "native-tui"
    NATIVE_SERVER = "native-server"


class Elicitation(str, Enum):
    """Policy/tool onay mekanizması."""
    NONE = "none"
    HOOK = "hook"
    APPROVAL_MIRROR = "approval-mirror"


class ModelFamily(str, Enum):
    """Desteklenen model aileleri."""
    CLAUDE = "claude"
    GPT = "gpt"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    MULTI = "multi"
    KIMI = "kimi"
    QWEN = "qwen"


class AuthMethod(str, Enum):
    """Kimlik doğrulama yöntemi."""
    API_KEY = "api-key"
    SUBSCRIPTION = "subscription"
    OAUTH = "oauth"
    GATEWAY = "gateway"


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Her platformun capability tanımı (Omnigent HarnessCapabilities'ten esinlenmiştir)."""
    name: str
    integration_mode: IntegrationMode = IntegrationMode.CLI_SUBPROCESS
    elicitation: Elicitation = Elicitation.NONE
    model_families: List[ModelFamily] = field(default_factory=lambda: [ModelFamily.MULTI])
    auth_methods: List[AuthMethod] = field(default_factory=lambda: [AuthMethod.API_KEY])

    # Özellik flags
    has_builtin_agent: bool = False
    has_builtin_parallel: bool = False
    has_builtin_web_search: bool = False
    has_builtin_web_fetch: bool = False
    has_mcp_support: bool = False
    has_policy_hooks: bool = False
    has_collaboration: bool = False
    has_cloud_sandbox: bool = False
    has_web_ui: bool = False
    has_mobile: bool = False

    # Performans
    max_parallel_agents: int = 1
    max_context_window: int = 128000
    setup_time_seconds: int = 0
    cost_per_research_usd: float = 0.13

    def describe(self) -> str:
        """Platformun capability özeti."""
        features = []
        if self.has_builtin_agent: features.append("agent()")
        if self.has_builtin_parallel: features.append("parallel()")
        if self.has_builtin_web_search: features.append("WebSearch")
        if self.has_builtin_web_fetch: features.append("WebFetch")
        if self.has_mcp_support: features.append("MCP")
        if self.has_policy_hooks: features.append("Policies")
        if self.has_collaboration: features.append("Collab")

        return (
            f"{self.name:15s} | "
            f"{self.integration_mode.value:20s} | "
            f"Par: {'✅' if self.has_builtin_parallel or self.max_parallel_agents > 1 else '❌'} | "
            f"Web: {'✅' if self.has_builtin_web_search else '❌'} | "
            f"Mod: {', '.join(m.value for m in self.model_families):30s} | "
            f"${self.cost_per_research_usd:.2f}/rsrch"
        )


class BaseRuntime(ABC):
    """Her platform için temel runtime arayüzü."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Platformun capability tanımı."""
        return RuntimeCapabilities(name=self.name)

    @abstractmethod
    def setup(self) -> bool:
        """Platformu başlatır, gerekli kontrolleri yapar.
        Returns: True = hazır, False = eksik var"""
        ...

    @abstractmethod
    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """
        LLM çağrısı yapar.
        - Claude Code: built-in agent()
        - Hermes: terminal + curl DeepSeek API
        - Generic: requests ile herhangi bir OpenAI-uyumlu API
        """
        ...

    @abstractmethod
    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """Web araması yapar.
        Returns: [{"url": str, "title": str, "snippet": str, "relevance": str}]"""
        ...

    @abstractmethod
    def web_fetch(self, url: str) -> Optional[str]:
        """URL içeriğini getirir. Returns: HTML'den arındırılmış metin veya None"""
        ...

    @abstractmethod
    def run_parallel(self, fn_list: List[Callable[[], Any]],
                     max_workers: int = 3) -> List[Any]:
        """Fonksiyonları paralel çalıştırır. Returns: Sonuçlar listesi"""
        ...

    def phase(self, name: str, detail: str = "") -> None:
        """Faz değişikliğini bildirir."""
        print(f"\n=== Phase: {name} ===" + (f" {detail}" if detail else ""))
        # Dashboard: seçili fazı güncelle
        if hasattr(self, '_dashboard') and self._dashboard:
            phase_name = name.split('/')[-1].split(' —')[0].strip()
            self._dashboard.select_phase(phase_name)

    def log(self, message: str) -> None:
        """Log mesajı basar."""
        print(f"  [{self.name}] {message}")
