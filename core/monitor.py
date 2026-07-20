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
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


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
    CANCELLED = "cancelled"


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
    input_cost_per_m: float = 0.50    # Modelin $/M prompt token maliyeti
    output_cost_per_m: float = 2.00   # Modelin $/M completion token maliyeti

    @property
    def cost_usd(self) -> float:
        """Bu agent'ın modele göre tahmini maliyeti ($)."""
        input_cost = (self.prompt_tokens / 1_000_000) * self.input_cost_per_m
        output_cost = (self.completion_tokens / 1_000_000) * self.output_cost_per_m
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
    skipped_agents: int = 0
    cancelled_agents: int = 0

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
            return time.monotonic() - self.start_time
        return 0.0

    @property
    def finished_agents(self) -> int:
        """Terminal durumdaki agent sayısı."""
        return (
            self.completed_agents
            + self.failed_agents
            + self.skipped_agents
            + self.cancelled_agents
        )

    def progress_bar(self, width: int = 20) -> str:
        """Faz için progress bar."""
        if self.total_agents == 0:
            return "[" + "░" * width + "]"
        done = self.finished_agents
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
        self._lock = threading.RLock()
        requested_provider = os.environ.get("LLM_PROVIDER", "deepseek").strip()
        self.provider = requested_provider if requested_provider in self.PROVIDERS else "deepseek"
        self.model = os.environ.get("LLM_MODEL", "").strip() or self._default_model()
        self.api_base = os.environ.get("LLM_API_BASE", "").strip() or self._default_base()
        self._explicit_api_key = os.environ.get("LLM_API_KEY", "")
        self.api_key = ""
        self._load_api_key()

    def _default_model(self) -> str:
        info = self.PROVIDERS.get(self.provider, {})
        return info.get("default_model", "deepseek-chat")

    def _default_base(self) -> str:
        info = self.PROVIDERS.get(self.provider, {})
        return info.get("base_url", "https://api.deepseek.com/v1")

    def _load_api_key(self):
        """API key'i aktif sağlayıcının environment değişkeninden yükle."""
        if self._explicit_api_key:
            self.api_key = self._explicit_api_key
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
        if not isinstance(provider, str):
            raise TypeError("provider must be a string")
        provider = provider.strip()
        if provider not in self.PROVIDERS:
            return False
        if not isinstance(model, str):
            raise TypeError("model must be a string")

        with self._lock:
            self.provider = provider
            self.model = model.strip() or self._default_model()
            self.api_base = self._default_base()
            self._load_api_key()
            os.environ["LLM_PROVIDER"] = provider
            os.environ["LLM_MODEL"] = self.model
            os.environ["LLM_API_BASE"] = self.api_base
        return True

    def list_providers(self) -> str:
        """Tüm sağlayıcıları listele."""
        with self._lock:
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
        with self._lock:
            info = self.PROVIDERS[self.provider]
            inp = info["cost_per_m_input"]
            out = info["cost_per_m_output"]
            return f"{self.provider}/{self.model} — ${inp:.2f}/M in, ${out:.2f}/M out"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        input_tokens = _token_count(input_tokens, "input_tokens")
        output_tokens = _token_count(output_tokens, "output_tokens")
        with self._lock:
            info = self.PROVIDERS[self.provider]
            inp_cost = (input_tokens / 1_000_000) * info["cost_per_m_input"]
            out_cost = (output_tokens / 1_000_000) * info["cost_per_m_output"]
            return round(inp_cost + out_cost, 6)

    def _monitor_values(self) -> Tuple[str, float, float]:
        """Atomik olarak monitor için model ve fiyat bilgisini döndür."""
        with self._lock:
            info = self.PROVIDERS[self.provider]
            return self.model, info["cost_per_m_input"], info["cost_per_m_output"]

    def _report_values(self) -> Tuple[str, str, str, str]:
        """Atomik bir rapor için aktif model yapılandırmasını döndür."""
        with self._lock:
            info = self.PROVIDERS[self.provider]
            cost_info = (
                f"{self.provider}/{self.model} — "
                f"${info['cost_per_m_input']:.2f}/M in, "
                f"${info['cost_per_m_output']:.2f}/M out"
            )
            return self.provider, self.model, self.api_base, cost_info


def _text(value: str, name: str) -> str:
    """Boş olmayan, başı/sonu kırpılmış metin doğrulaması."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _token_count(value: int, name: str) -> int:
    """Token sayaçlarının negatif veya bool değer almasını engeller."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


class PipelineMonitor:
    """
    Pipeline canlı takip sistemi.
    Claude Code'un /workflows ekranının Hermes/Generic versiyonu.
    
    Kullanım:
        monitor = PipelineMonitor("Araştırma sorusu")
        monitor.start_phase("Scope")
        agent_id = monitor.start_agent("search:pricing", "Scope")
        monitor.complete_agent(agent_id, prompt_tokens=300, completion_tokens=200)
        monitor.fail_agent(agent_id, "API hatası")
        monitor.end_phase("Scope")
        print(monitor.phase_report())
    """

    def __init__(self, question: str, model_config: Optional[ModelConfig] = None):
        self.question = _text(question, "question")
        if model_config is not None and not isinstance(model_config, ModelConfig):
            raise TypeError("model_config must be a ModelConfig or None")
        self.model = model_config or ModelConfig()
        self.phases: List[PhaseRecord] = []
        self._current_phase: Optional[PhaseRecord] = None
        self._agent_counter = 0
        self._agents: Dict[str, Tuple[PhaseRecord, AgentRecord]] = {}
        self._phases: Dict[str, PhaseRecord] = {}
        self._lock = threading.RLock()
        self._cancelled = False
        self._paused = False
        self.start_time = time.monotonic()
        self.end_time = 0.0

    # ─── Phase Management ───

    def start_phase(self, name: str) -> PhaseRecord:
        """Yeni faz başlat."""
        name = _text(name, "name")
        with self._lock:
            if self._cancelled:
                raise RuntimeError("cannot start a phase after cancellation")
            if name in self._phases:
                raise ValueError(f"phase already exists: {name}")
            phase = PhaseRecord(name=name, status=PhaseStatus.ACTIVE, start_time=time.monotonic())
            self.phases.append(phase)
            self._phases[name] = phase
            self._current_phase = phase
        return phase

    def end_phase(self, name: str, status: PhaseStatus = PhaseStatus.COMPLETED):
        """Fazı bitir."""
        name = _text(name, "name")
        if not isinstance(status, PhaseStatus):
            raise TypeError("status must be a PhaseStatus")
        with self._lock:
            phase = self._phases.get(name)
            if phase is None:
                raise KeyError(f"unknown phase: {name}")
            if phase.status != PhaseStatus.ACTIVE:
                return
            phase.status = status
            phase.end_time = time.monotonic()
            if phase is self._current_phase:
                self._current_phase = None

    def skip_phase(self, name: str):
        """Fazı atla."""
        self.end_phase(name, PhaseStatus.SKIPPED)

    # ─── Agent Management ───

    def _next_agent_id_locked(self) -> str:
        self._agent_counter += 1
        return f"agent_{self._agent_counter:04d}"

    def start_agent(self, label: str, phase: str, model: str = "") -> str:
        """Yeni agent başlat. Returns: agent_id"""
        label = _text(label, "label")
        phase_name = _text(phase, "phase")
        if not isinstance(model, str):
            raise TypeError("model must be a string")
        configured_model, input_cost, output_cost = self.model._monitor_values()

        with self._lock:
            if self._cancelled:
                raise RuntimeError("cannot start an agent after cancellation")
            phase_record = self._phases.get(phase_name)
            if phase_record is None:
                raise KeyError(f"unknown phase: {phase_name}")
            if phase_record.status != PhaseStatus.ACTIVE:
                raise RuntimeError(f"cannot start an agent in {phase_record.status.value} phase: {phase_name}")

            agent = AgentRecord(
                id=self._next_agent_id_locked(),
                label=label,
                phase=phase_name,
                status=AgentStatus.RUNNING,
                model=model.strip() or configured_model,
                start_time=time.monotonic(),
                input_cost_per_m=input_cost,
                output_cost_per_m=output_cost,
            )
            phase_record.agents.append(agent)
            phase_record.total_agents += 1
            self._agents[agent.id] = (phase_record, agent)
        return agent.id

    def complete_agent(self, agent_id: str, prompt_tokens: int = 0,
                       completion_tokens: int = 0, result_preview: str = ""):
        """Agent'ı tamamlandı olarak işaretle."""
        agent_id = _text(agent_id, "agent_id")
        prompt_tokens = _token_count(prompt_tokens, "prompt_tokens")
        completion_tokens = _token_count(completion_tokens, "completion_tokens")
        if not isinstance(result_preview, str):
            raise TypeError("result_preview must be a string")
        with self._lock:
            phase, agent = self._agent(agent_id)
            if not self._finish_agent(phase, agent, AgentStatus.COMPLETED):
                return
            agent.prompt_tokens = prompt_tokens
            agent.completion_tokens = completion_tokens
            agent.total_tokens = prompt_tokens + completion_tokens
            agent.result_preview = result_preview[:100]

    def fail_agent(self, agent_id: str, error: str = ""):
        """Agent'ı hatalı olarak işaretle."""
        agent_id = _text(agent_id, "agent_id")
        if not isinstance(error, str):
            error = str(error)
        with self._lock:
            phase, agent = self._agent(agent_id)
            if self._finish_agent(phase, agent, AgentStatus.FAILED):
                agent.error = error[:1_000]

    def skip_agent(self, agent_id: str):
        """Agent'ı atla."""
        agent_id = _text(agent_id, "agent_id")
        with self._lock:
            phase, agent = self._agent(agent_id)
            self._finish_agent(phase, agent, AgentStatus.SKIPPED)

    def _agent(self, agent_id: str) -> Tuple[PhaseRecord, AgentRecord]:
        """Kayıtlı agent'ı bulun; çağıran monitor kilidini tutmalıdır."""
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {agent_id}") from exc

    def _finish_agent(self, phase: PhaseRecord, agent: AgentRecord,
                      status: AgentStatus) -> bool:
        """Bir çalışan agent'ı yalnızca bir kez terminal duruma geçirir."""
        if agent.status != AgentStatus.RUNNING:
            return False

        agent.status = status
        agent.end_time = time.monotonic()
        agent.duration = max(0.0, agent.end_time - agent.start_time)
        if status == AgentStatus.COMPLETED:
            phase.completed_agents += 1
        elif status == AgentStatus.FAILED:
            phase.failed_agents += 1
        elif status == AgentStatus.SKIPPED:
            phase.skipped_agents += 1
        elif status == AgentStatus.CANCELLED:
            phase.cancelled_agents += 1
        return True

    # ─── Control ───

    def cancel(self):
        """Tüm pipeline'ı iptal et."""
        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            self._paused = False
            self.end_time = time.monotonic()
            for phase in self.phases:
                if phase.status == PhaseStatus.ACTIVE:
                    phase.status = PhaseStatus.CANCELLED
                    phase.end_time = self.end_time
                for a in phase.agents:
                    self._finish_agent(phase, a, AgentStatus.CANCELLED)
            self._current_phase = None

    def pause(self):
        """Pipeline'ı duraklat."""
        with self._lock:
            if not self._cancelled:
                self._paused = True

    def resume(self):
        """Pipeline'ı devam ettir."""
        with self._lock:
            if not self._cancelled:
                self._paused = False

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    # ─── Stuck Detection ───

    def check_stuck(self, timeout: int = 120) -> List[Tuple[str, str, float]]:
        """Timeout olan agent'ları tespit et.
        Returns: [(agent_id, label, elapsed_s), ...]"""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a number")
        if timeout < 0:
            raise ValueError("timeout must not be negative")
        with self._lock:
            return self._stuck_agents(timeout, time.monotonic())

    def _stuck_agents(self, timeout: float, now: float) -> List[Tuple[str, str, float]]:
        """Kilit altındaki çalışan agent'lar için timeout kontrolü."""
        stuck = []
        for phase in self.phases:
            for agent in phase.agents:
                if agent.status == AgentStatus.RUNNING:
                    elapsed = max(0.0, now - agent.start_time)
                    if elapsed > timeout:
                        stuck.append((agent.id, agent.label, elapsed))
        return stuck

    # ─── Stats ───

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return sum(p.total_tokens for p in self.phases)

    @property
    def total_cost(self) -> float:
        with self._lock:
            return round(sum(p.total_cost for p in self.phases), 6)

    @property
    def total_duration(self) -> float:
        with self._lock:
            end_time = self.end_time or time.monotonic()
            return max(0.0, end_time - self.start_time)

    @property
    def total_agents(self) -> int:
        with self._lock:
            return sum(p.total_agents for p in self.phases)

    @property
    def completed_agents(self) -> int:
        with self._lock:
            return sum(p.completed_agents for p in self.phases)

    @property
    def failed_agents(self) -> int:
        with self._lock:
            return sum(p.failed_agents for p in self.phases)

    @property
    def active_agents(self) -> int:
        with self._lock:
            return sum(
                agent.status == AgentStatus.RUNNING
                for phase in self.phases
                for agent in phase.agents
            )

    # ─── Reports ───

    def summary_line(self) -> str:
        """Tek satır özet — Claude Code progress bar benzeri."""
        with self._lock:
            total = sum(phase.total_agents for phase in self.phases)
            done = sum(phase.finished_agents for phase in self.phases)
            bar_width = 15
            ratio = done / total if total > 0 else 0
            filled = int(ratio * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            status = "⛔" if self._cancelled else ("⏸" if self._paused else "🔄")
            duration = (self.end_time or time.monotonic()) - self.start_time
            tokens = sum(phase.total_tokens for phase in self.phases)
            cost = sum(phase.total_cost for phase in self.phases)
            return (
                f"{status} [{bar}] {done}/{total} agents · "
                f"{max(0.0, duration):.0f}s · "
                f"{tokens:,} tok · "
                f"${cost:.4f}"
            )

    def phase_report(self) -> str:
        """Faz bazında detaylı rapor."""
        with self._lock:
            _, _, _, cost_info = self.model._report_values()
            now = time.monotonic()
            total_agents = sum(phase.total_agents for phase in self.phases)
            total_tokens = sum(phase.total_tokens for phase in self.phases)
            total_cost = sum(phase.total_cost for phase in self.phases)
            duration = max(0.0, (self.end_time or now) - self.start_time)
            stuck = self._stuck_agents(120, now)
            stuck_ids = {agent_id for agent_id, _, _ in stuck}

            lines = [f"\n{'='*60}"]
            lines.append("🔬 PIPELINE MONITOR")
            lines.append(f"{'='*60}")
            lines.append(f"  Soru: {self.question[:80]}")
            lines.append(f"  Model: {cost_info}")
            lines.append(f"  Süre: {duration:.0f}s")
            lines.append(f"  Toplam: {total_agents} agents · {total_tokens:,} tok · ${total_cost:.4f}")
            lines.append("")

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
                    PhaseStatus.CANCELLED: "⛔",
                }.get(phase.status, "❓")

                lines.append(f"  {icon} PHASE: {phase.name}")
                lines.append(
                    f"     {phase.progress_bar()} · {phase.duration:.0f}s · "
                    f"{phase.total_tokens:,} tok · ${phase.total_cost:.4f}"
                )

                failed = [agent for agent in phase.agents if agent.status == AgentStatus.FAILED]
                running = [agent for agent in phase.agents if agent.status == AgentStatus.RUNNING]
                if running:
                    for agent in running[:5]:
                        elapsed = max(0.0, now - agent.start_time)
                        warn = " ⚠TIMEOUT!" if agent.id in stuck_ids else ""
                        lines.append(f"     🔄 {agent.label:40s} {elapsed:.0f}s{warn}")

                if failed:
                    lines.append("     ❌ Hatalı agent'lar:")
                    for agent in failed[:3]:
                        lines.append(f"        • {agent.label} — {agent.error[:80]}")

            if stuck:
                lines.append(f"\n  ⚠ TIMEOUT UYARISI: {len(stuck)} agent 120s+'yi aştı:")
                for _, label, elapsed in stuck[:3]:
                    lines.append(f"    • {label} ({elapsed:.0f}s)")

            lines.append(f"{'='*60}")
            return "\n".join(lines)

    def json_report(self) -> dict:
        """JSON formatında rapor — makine okuması için."""
        with self._lock:
            provider, model, api_base, cost_info = self.model._report_values()
            now = time.monotonic()
            duration = max(0.0, (self.end_time or now) - self.start_time)
            total_agents = sum(phase.total_agents for phase in self.phases)
            completed_agents = sum(phase.completed_agents for phase in self.phases)
            failed_agents = sum(phase.failed_agents for phase in self.phases)
            skipped_agents = sum(phase.skipped_agents for phase in self.phases)
            cancelled_agents = sum(phase.cancelled_agents for phase in self.phases)
            active_agents = sum(
                agent.status == AgentStatus.RUNNING
                for phase in self.phases
                for agent in phase.agents
            )
            total_tokens = sum(phase.total_tokens for phase in self.phases)
            total_cost = round(sum(phase.total_cost for phase in self.phases), 6)
            stuck = self._stuck_agents(120, now)

            return {
                "question": self.question,
                "model": {
                    "provider": provider,
                    "model": model,
                    "api_base": api_base,
                    "cost_info": cost_info,
                },
                "stats": {
                    "duration_s": duration,
                    "total_agents": total_agents,
                    "completed_agents": completed_agents,
                    "failed_agents": failed_agents,
                    "skipped_agents": skipped_agents,
                    "cancelled_agents": cancelled_agents,
                    "active_agents": active_agents,
                    "total_tokens": total_tokens,
                    "total_cost_usd": total_cost,
                },
                "phases": [
                    {
                        "name": phase.name,
                        "status": phase.status.value,
                        "duration_s": phase.duration,
                        "total_agents": phase.total_agents,
                        "completed": phase.completed_agents,
                        "failed": phase.failed_agents,
                        "skipped": phase.skipped_agents,
                        "cancelled": phase.cancelled_agents,
                        "tokens": phase.total_tokens,
                        "cost_usd": phase.total_cost,
                    }
                    for phase in self.phases
                ],
                "stuck_agents": [
                    {"id": agent_id, "label": label, "elapsed_s": elapsed}
                    for agent_id, label, elapsed in stuck
                ],
            }
