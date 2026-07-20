"""
Pipeline Monitor — Canlı durum takip, token sayacı, model yönetimi, hata takibi, kontrol mekanizmaları.

Claude Code'un /workflows ekranındaki özelliklerin Hermes/Generic versiyonu:
  • parallel() durumu — kaç ajan çalışıyor, biten, bekleyen, hatalı
  • Model seçimi — hangi model, değiştirme, API sağlayıcı
  • Token takibi — toplam token, faz başına token, tahmini maliyet
  • Hata takibi — hangi agent nerede takıldı, sebebi
  • Kontrol — durdur, devam et, agent'ı yeniden başlat, faz atla
"""

import os
import json
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class AgentStatus(str, Enum):
    """Agent durumu."""
    PENDING = "pending"          # Bekliyor
    RUNNING = "running"          # Çalışıyor
    COMPLETED = "completed"      # Tamamlandı
    FAILED = "failed"            # Hata
    SKIPPED = "skipped"          # Atlandı
    CANCELLED = "cancelled"      # İptal edildi


class PhaseStatus(str, Enum):
    """Faz durumu."""
    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentRecord:
    """Bir agent'ın kaydı."""
    id: str                          # Agent ID (unique)
    label: str                       # Agent etiketi (ör: "search:pricing")
    phase: str                       # Hangi fazda (Scope, Search, Fetch, Verify, Synthesize)
    status: AgentStatus = AgentStatus.PENDING
    model: str = ""                  # Kullanılan model
    prompt_tokens: int = 0           # Prompt token
    completion_tokens: int = 0       # Completion token
    total_tokens: int = 0            # Toplam token
    start_time: float = 0.0          # Başlangıç zamanı
    end_time: float = 0.0            # Bitiş zamanı
    duration: float = 0.0            # Geçen süre (sn)
    error: str = ""                  # Hata mesajı
    result_preview: str = ""         # Sonuç önizlemesi

    @property
    def cost_usd(self) -> float:
        """Tahmini maliyet ($). DeepSeek: $0.50/M input, $2.00/M output."""
        input_cost = (self.prompt_tokens / 1_000_000) * 0.50
        output_cost = (self.completion_tokens / 1_000_000) * 2.00
        return round(input_cost + output_cost, 6)

    def summary(self) -> str:
        """Agent özeti — tek satır."""
        status_icon = {
            AgentStatus.PENDING: "⏳",
            AgentStatus.RUNNING: "🔄",
            AgentStatus.COMPLETED: "✅",
            AgentStatus.FAILED: "❌",
            AgentStatus.SKIPPED: "⏭",
            AgentStatus.CANCELLED: "🚫",
        }.get(self.status, "❓")

        duration_str = f"{self.duration:.1f}s" if self.duration > 0 else "..."
        token_str = f"{self.total_tokens:,}tok" if self.total_tokens > 0 else ""
        error_str = f" ⚠{self.error[:50]}" if self.error else ""

        return f"  {status_icon} {self.label:40s} {duration_str:8s} {token_str:15s}{error_str}"


@dataclass
class PhaseRecord:
    """Bir fazın kaydı."""
    name: str                        # Faz adı
    status: PhaseStatus = PhaseStatus.WAITING
    agents: List[AgentRecord] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0

    @property
    def total_tokens(self) -> int:
        return sum(a.total_tokens for a in self.agents)

    @property
    def total_cost(self) -> float:
        return round(sum(a.cost_usd for a in self.agents), 6)

    @property
    def duration(self) -> float:
        if self.end_time > 0:
            return self.end_time - self.start_time
        if self.start_time > 0:
            return time.time() - self.start_time
        return 0.0

    def progress_bar(self, width: int = 20) -> str:
        """Faz için progress bar."""
        if self.total_agents == 0:
            return "[" + "░" * width + "]"
        done = self.completed_agents + self.failed_agents
        ratio = done / self.total_agents
        filled = int(ratio * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {done}/{self.total_agents}"


class ModelConfig:
    """Model yapılandırması — hangi model, hangi API, değiştirme."""
    
    # Kayıtlı model sağlayıcıları
    PROVIDERS = {
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "cost_per_m_input": 0.50,    # $/M token
            "cost_per_m_output": 2.00,
            "env_key": "DEEPSEEK_API_KEY",
            "default_model": "deepseek-chat",
        },
        "chatgpt": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "cost_per_m_input": 2.50,
            "cost_per_m_output": 10.00,
            "env_key": "OPENAI_API_KEY",
            "default_model": "gpt-4o-mini",
        },
        "claude": {
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-sonnet-4", "claude-haiku-3"],
            "cost_per_m_input": 3.00,
            "cost_per_m_output": 15.00,
            "env_key": "ANTHROPIC_API_KEY",
            "default_model": "claude-sonnet-4",
        },
        "kimi": {
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["kimi-k2", "moonshot-v1-8k"],
            "cost_per_m_input": 0.60,
            "cost_per_m_output": 2.00,
            "env_key": "KIMI_API_KEY",
            "default_model": "kimi-k2",
        },
        "qwen": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
            "cost_per_m_input": 0.40,
            "cost_per_m_output": 1.20,
            "env_key": "QWEN_API_KEY",
            "default_model": "qwen-plus",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "models": ["gemini-2.0-flash", "gemini-2.0-pro"],
            "cost_per_m_input": 0.10,
            "cost_per_m_output": 0.40,
            "env_key": "GEMINI_API_KEY",
            "default_model": "gemini-2.0-flash",
        },
        "minimax": {
            "base_url": "https://api.minimax.chat/v1",
            "models": ["minimax-text-01"],
            "cost_per_m_input": 0.50,
            "cost_per_m_output": 1.50,
            "env_key": "MINIMAX_API_KEY",
            "default_model": "minimax-text-01",
        },
        "zhipu": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-4-plus", "glm-4v"],
            "cost_per_m_input": 0.50,
            "cost_per_m_output": 2.00,
            "env_key": "ZHIPU_API_KEY",
            "default_model": "glm-4-plus",
        },
    }

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "deepseek")
        self.model = os.environ.get("LLM_MODEL", self._default_model())
        self.api_base = os.environ.get("LLM_API_BASE", self._default_base())
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self._load_api_key()

    def _default_model(self) -> str:
        info = self.PROVIDERS.get(self.provider, {})
        return info.get("default_model", "deepseek-chat")

    def _default_base(self) -> str:
        info = self.PROVIDERS.get(self.provider, {})
        return info.get("base_url", "https://api.deepseek.com/v1")

    def _load_api_key(self):
        """API key'i environment'dan veya .env'den yükle."""
        if self.api_key:
            return
        info = self.PROVIDERS.get(self.provider, {})
        env_key_name = info.get("env_key", "")
        if env_key_name:
            self.api_key = os.environ.get(env_key_name, "")
        # DeepSeek fallback
        if not self.api_key:
            self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    def switch(self, provider: str, model: str = "") -> bool:
        """Model sağlayıcısını değiştir."""
        if provider not in self.PROVIDERS:
            return False
        self.provider = provider
        self.model = model or self._default_model()
        self.api_base = self._default_base()
        self._load_api_key()
        os.environ["LLM_PROVIDER"] = provider
        os.environ["LLM_MODEL"] = self.model
        os.environ["LLM_API_BASE"] = self.api_base
        return True

    def list_providers(self) -> str:
        """Tüm sağlayıcıları listele."""
        lines = []
        lines.append(f"{'Provider':15s} {'Model':25s} {'Cost Input':12s} {'Cost Out':12s} {'Status':10s}")
        lines.append("-" * 75)
        for name, info in self.PROVIDERS.items():
            marker = "← aktif" if name == self.provider else ""
            default = info["default_model"]
            inp = f"${info['cost_per_m_input']:.2f}/M"
            out = f"${info['cost_per_m_output']:.2f}/M"
            key_set = "✅" if (info["env_key"] and os.environ.get(info["env_key"])) or name == self.provider else "❌"
            lines.append(f"  {name:15s} {default:25s} {inp:12s} {out:12s} {key_set:5s} {marker}")
        return "\n".join(lines)

    @property
    def cost_info(self) -> str:
        info = self.PROVIDERS.get(self.provider, {})
        inp = info.get("cost_per_m_input", 0)
        out = info.get("cost_per_m_output", 0)
        return f"{self.provider}/{self.model} — ${inp:.2f}/M in, ${out:.2f}/M out"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        info = self.PROVIDERS.get(self.provider, {})
        inp_cost = (input_tokens / 1_000_000) * info.get("cost_per_m_input", 0.50)
        out_cost = (output_tokens / 1_000_000) * info.get("cost_per_m_output", 2.00)
        return round(inp_cost + out_cost, 6)


class PipelineMonitor:
    """
    Pipeline canlı takip sistemi.
    Claude Code'un /workflows ekranının Hermes/Generic versiyonu.
    
    Kullanım:
        monitor = PipelineMonitor("Araştırma sorusu")
        monitor.start_phase("Scope")
        agent_id = monitor.start_agent("search:pricing", "Scope")
        monitor.complete_agent(agent_id, tokens=500)
        monitor.fail_agent(agent_id, "API hatası")
        monitor.end_phase("Scope")
        print(monitor.report())
    """

    def __init__(self, question: str, model_config: Optional[ModelConfig] = None):
        self.question = question
        self.model = model_config or ModelConfig()
        self.phases: List[PhaseRecord] = []
        self._current_phase: Optional[PhaseRecord] = None
        self._agent_counter = 0
        self._lock = threading.Lock()
        self._cancelled = False
        self._paused = False
        self.start_time = time.time()
        self.end_time = 0.0

    # ─── Phase Management ───

    def start_phase(self, name: str) -> PhaseRecord:
        """Yeni faz başlat."""
        phase = PhaseRecord(name=name, status=PhaseStatus.ACTIVE, start_time=time.time())
        with self._lock:
            self.phases.append(phase)
            self._current_phase = phase
        return phase

    def end_phase(self, name: str, status: PhaseStatus = PhaseStatus.COMPLETED):
        """Fazı bitir."""
        with self._lock:
            for p in self.phases:
                if p.name == name:
                    p.status = status
                    p.end_time = time.time()
                    if p is self._current_phase:
                        self._current_phase = None
                    break

    def skip_phase(self, name: str):
        """Fazı atla."""
        self.end_phase(name, PhaseStatus.SKIPPED)

    # ─── Agent Management ───

    def _next_agent_id(self) -> str:
        self._agent_counter += 1
        return f"agent_{self._agent_counter:04d}"

    def start_agent(self, label: str, phase: str, model: str = "") -> str:
        """Yeni agent başlat. Returns: agent_id"""
        agent = AgentRecord(
            id=self._next_agent_id(),
            label=label,
            phase=phase,
            status=AgentStatus.RUNNING,
            model=model or self.model.model,
            start_time=time.time(),
        )
        with self._lock:
            for p in self.phases:
                if p.name == phase:
                    p.agents.append(agent)
                    p.total_agents += 1
                    p.completed_agents  # don't increment
                    break
        return agent.id

    def complete_agent(self, agent_id: str, prompt_tokens: int = 0,
                       completion_tokens: int = 0, result_preview: str = ""):
        """Agent'ı tamamlandı olarak işaretle."""
        with self._lock:
            for phase in self.phases:
                for a in phase.agents:
                    if a.id == agent_id:
                        a.status = AgentStatus.COMPLETED
                        a.end_time = time.time()
                        a.duration = a.end_time - a.start_time
                        a.prompt_tokens = prompt_tokens
                        a.completion_tokens = completion_tokens
                        a.total_tokens = prompt_tokens + completion_tokens
                        a.result_preview = result_preview[:100]
                        phase.completed_agents += 1
                        return

    def fail_agent(self, agent_id: str, error: str = ""):
        """Agent'ı hatalı olarak işaretle."""
        with self._lock:
            for phase in self.phases:
                for a in phase.agents:
                    if a.id == agent_id:
                        a.status = AgentStatus.FAILED
                        a.end_time = time.time()
                        a.duration = a.end_time - a.start_time
                        a.error = error
                        phase.failed_agents += 1
                        return

    def skip_agent(self, agent_id: str):
        """Agent'ı atla."""
        with self._lock:
            for phase in self.phases:
                for a in phase.agents:
                    if a.id == agent_id:
                        a.status = AgentStatus.SKIPPED
                        return

    # ─── Control ───

    def cancel(self):
        """Tüm pipeline'ı iptal et."""
        self._cancelled = True
        self.end_time = time.time()
        with self._lock:
            for phase in self.phases:
                if phase.status == PhaseStatus.ACTIVE:
                    phase.status = PhaseStatus.FAILED
                    phase.end_time = time.time()
                for a in phase.agents:
                    if a.status == AgentStatus.RUNNING:
                        a.status = AgentStatus.CANCELLED
                        a.end_time = time.time()
                        a.duration = a.end_time - a.start_time

    def pause(self):
        """Pipeline'ı duraklat."""
        self._paused = True

    def resume(self):
        """Pipeline'ı devam ettir."""
        self._paused = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ─── Stuck Detection ───

    def check_stuck(self, timeout: int = 120) -> List[Tuple[str, str, float]]:
        """Timeout olan agent'ları tespit et.
        Returns: [(agent_id, label, elapsed_s), ...]"""
        stuck = []
        now = time.time()
        with self._lock:
            for phase in self.phases:
                for a in phase.agents:
                    if a.status == AgentStatus.RUNNING:
                        elapsed = now - a.start_time
                        if elapsed > timeout:
                            stuck.append((a.id, a.label, elapsed))
        return stuck

    # ─── Stats ───

    @property
    def total_tokens(self) -> int:
        return sum(p.total_tokens for p in self.phases)

    @property
    def total_cost(self) -> float:
        return round(sum(p.total_cost for p in self.phases), 6)

    @property
    def total_duration(self) -> float:
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def total_agents(self) -> int:
        return sum(p.total_agents for p in self.phases)

    @property
    def completed_agents(self) -> int:
        return sum(p.completed_agents for p in self.phases)

    @property
    def failed_agents(self) -> int:
        return sum(p.failed_agents for p in self.phases)

    @property
    def active_agents(self) -> int:
        count = 0
        with self._lock:
            for phase in self.phases:
                for a in phase.agents:
                    if a.status == AgentStatus.RUNNING:
                        count += 1
        return count

    # ─── Reports ───

    def summary_line(self) -> str:
        """Tek satır özet — Claude Code progress bar benzeri."""
        total = self.total_agents
        done = self.completed_agents + self.failed_agents
        bar_width = 15
        ratio = done / total if total > 0 else 0
        filled = int(ratio * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        status = "⏸" if self._paused else ("⛔" if self._cancelled else "🔄")

        return (
            f"{status} [{bar}] {done}/{total} agents · "
            f"{self.total_duration:.0f}s · "
            f"{self.total_tokens:,} tok · "
            f"${self.total_cost:.4f}"
        )

    def phase_report(self) -> str:
        """Faz bazında detaylı rapor."""
        lines = [f"\n{'='*60}"]
        lines.append(f"🔬 PIPELINE MONITOR")
        lines.append(f"{'='*60}")
        lines.append(f"  Soru: {self.question[:80]}")
        lines.append(f"  Model: {self.model.cost_info}")
        lines.append(f"  Süre: {self.total_duration:.0f}s")
        lines.append(f"  Toplam: {self.total_agents} agents · {self.total_tokens:,} tok · ${self.total_cost:.4f}")
        lines.append(f"")

        if not self.phases:
            lines.append("  (Henüz faz başlamadı)")
            return "\n".join(lines)

        for phase in self.phases:
            icon = {
                PhaseStatus.WAITING: "⏳",
                PhaseStatus.ACTIVE: "🔄",
                PhaseStatus.COMPLETED: "✅",
                PhaseStatus.FAILED: "❌",
                PhaseStatus.SKIPPED: "⏭",
            }.get(phase.status, "❓")

            lines.append(f"  {icon} PHASE: {phase.name}")
            lines.append(f"     {phase.progress_bar()} · {phase.duration:.0f}s · {phase.total_tokens:,} tok · ${phase.total_cost:.4f}")

            if phase.agents:
                # Hatalı agent'ları göster
                failed = [a for a in phase.agents if a.status == AgentStatus.FAILED]
                running = [a for a in phase.agents if a.status == AgentStatus.RUNNING]
                stuck = self.check_stuck(120)

                if running:
                    for a in running[:5]:  # İlk 5 çalışan
                        elapsed = time.time() - a.start_time
                        is_stuck = any(s[0] == a.id for s in stuck)
                        warn = " ⚠TIMEOUT!" if is_stuck else ""
                        lines.append(f"     🔄 {a.label:40s} {elapsed:.0f}s{warn}")

                if failed:
                    lines.append(f"     ❌ Hatalı agent'lar:")
                    for a in failed[:3]:
                        lines.append(f"        • {a.label} — {a.error[:80]}")

        # Stuck uyarısı
        stuck = self.check_stuck()
        if stuck:
            lines.append(f"\n  ⚠ TIMEOUT UYARISI: {len(stuck)} agent {120}s+'yi aştı:")
            for sid, slab, selapsed in stuck[:3]:
                lines.append(f"    • {slab} ({selapsed:.0f}s)")

        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def json_report(self) -> dict:
        """JSON formatında rapor — makine okuması için."""
        return {
            "question": self.question,
            "model": {
                "provider": self.model.provider,
                "model": self.model.model,
                "api_base": self.model.api_base,
                "cost_info": self.model.cost_info,
            },
            "stats": {
                "duration_s": self.total_duration,
                "total_agents": self.total_agents,
                "completed_agents": self.completed_agents,
                "failed_agents": self.failed_agents,
                "active_agents": self.active_agents,
                "total_tokens": self.total_tokens,
                "total_cost_usd": self.total_cost,
            },
            "phases": [
                {
                    "name": p.name,
                    "status": p.status.value,
                    "duration_s": p.duration,
                    "total_agents": p.total_agents,
                    "completed": p.completed_agents,
                    "failed": p.failed_agents,
                    "tokens": p.total_tokens,
                    "cost_usd": p.total_cost,
                }
                for p in self.phases
            ],
            "stuck_agents": [
                {"id": sid, "label": slab, "elapsed_s": selapsed}
                for sid, slab, selapsed in self.check_stuck()
            ],
        }
