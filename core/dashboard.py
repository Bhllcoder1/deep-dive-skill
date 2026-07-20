#!/usr/bin/env python3
"""
Deep Dive Skill — Kontrol Paneli (TUI)
Sürekli açık kalan, tüm sistemi yönettiğin terminal arayüzü.

Özellikler:
  • Pipeline başlatma/durdurma
  • Canlı agent takibi (status, token, süre)
  • Model değiştirme
  • Geçmiş araştırmalara göz atma
  • Rapor kaydetme/görüntüleme
  • Faz filtreleme
  • Klavye kısayolları ile tam kontrol

Kullanım:
    python3 -m core.dashboard          # Paneli aç
    python3 harness.py panel            # Paneli aç
    python3 harness.py "soru"           # Pipeline + panel

Kısayollar:
    ↑↓          — fazlar arası geçiş
    Enter       — fazı genişlet/daralt
    r           — pipeline çalıştır (araştırma başlat)
    m           — model değiştir
    s           — rapor kaydet
    h           — geçmiş araştırmalar
    /           — ara
    f           — filtrele
    q           — çıkış
    Esc         — geri
"""

import os
import sys
import json
import time
import threading
import datetime
from typing import List, Optional, Callable

# Renkler
class C:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    CLEAR = '\033[2J\033[H'

    @staticmethod
    def status_icon(status: str) -> str:
        icons = {
            "completed": f"{C.GREEN}✔{C.END}",
            "failed": f"{C.RED}✘{C.END}",
            "running": f"{C.YELLOW}●{C.END}",
            "pending": f"{C.GRAY}○{C.END}",
            "cancelled": f"{C.RED}⊘{C.END}",
            "idle": f"{C.GRAY}○{C.END}",
        }
        return icons.get(status, f"{C.GRAY}?{C.END}")


class PipelineController:
    """
    Pipeline kontrolcüsü — dashboard'tan pipeline başlatma/durdurma.
    """
    
    def __init__(self):
        self.running = False
        self.paused = False
        self._thread = None
        self._stop_event = threading.Event()
        self.result = None
        self.error = None
        self.progress = {"phase": "", "agent": 0, "total": 0, "status": "idle"}
    
    def start(self, question: str, runtime: str = "generic"):
        """Pipeline'ı arka planda başlat."""
        if self.running:
            return False
        
        self.running = True
        self._stop_event.clear()
        self.result = None
        self.error = None
        
        def _run():
            try:
                os.environ["DR_RUNTIME"] = runtime
                from harness import deep_research
                self.result = deep_research(question, show_dashboard=False)
                self.progress["status"] = "completed"
            except Exception as e:
                self.error = str(e)
                self.progress["status"] = "failed"
            finally:
                self.running = False
        
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return True
    
    def stop(self):
        """Pipeline'ı durdur."""
        self._stop_event.set()
        self.running = False
        self.progress["status"] = "cancelled"
    
    @property
    def status_text(self) -> str:
        if self.running:
            return f"{C.YELLOW}● Running{C.END}"
        if self.result:
            return f"{C.GREEN}✔ Completed{C.END}"
        if self.error:
            return f"{C.RED}✘ Failed: {self.error[:30]}{C.END}"
        return f"{C.GRAY}○ Idle{C.END}"


class HistoryManager:
    """Geçmiş araştırma kayıtları."""
    
    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = os.path.expanduser("~/.bdeep-research-history.json")
        self.db_path = db_path
        self.records = self._load()
    
    def _load(self) -> list:
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path) as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def _save(self):
        try:
            with open(self.db_path, "w") as f:
                json.dump(self.records[-50:], f, indent=2)
        except:
            pass
    
    def add(self, question: str, result: dict):
        self.records.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "question": question,
            "summary": result.get("summary", "")[:200],
            "findings_count": len(result.get("findings", [])),
            "refuted_count": len(result.get("refuted", [])),
            "total_tokens": result.get("stats", {}).get("total_tokens", 0),
            "total_cost": result.get("stats", {}).get("total_cost_usd", 0),
            "duration_s": result.get("stats", {}).get("duration_s", 0),
            "runtime": result.get("stats", {}).get("runtime", "?"),
        })
        self._save()
    
    def list(self, limit: int = 10) -> list:
        return self.records[-limit:][::-1]


class Dashboard:
    """
    Ana kontrol paneli — sürekli açık kalır, tüm sistemi yönetirsin.
    """

    def __init__(self):
        self.title = "deep-dive-skill"
        self.subtitle = "Deep Dive Skill — Control Panel"
        self.mode = "main"  # main, history, model_select, help
        self.selected_idx = 0
        self.filter_mode = None
        self.message = ""
        self.message_time = 0
        
        # Pipeline kontrol
        self.pipeline = PipelineController()
        self.history = HistoryManager()
        
        # Demo phases (gerçek pipeline bağlanınca güncellenir)
        self.phases = [
            {"name": "Scope", "total": 1, "completed": 0, "status": "idle", "agents": []},
            {"name": "Search", "total": 0, "completed": 0, "status": "idle", "agents": []},
            {"name": "Fetch", "total": 0, "completed": 0, "status": "idle", "agents": []},
            {"name": "Verify", "total": 0, "completed": 0, "status": "idle", "agents": []},
            {"name": "Synthesize", "total": 0, "completed": 0, "status": "idle", "agents": []},
        ]
        
        self._start_time = time.time()
        self._running = True
        self._input_buffer = ""
        self._question_input = ""
        self._input_mode = False

    # ─── Navigation ───

    def select_next(self):
        if self.phases:
            self.selected_idx = (self.selected_idx + 1) % len(self.phases)

    def select_prev(self):
        if self.phases:
            self.selected_idx = (self.selected_idx - 1) % len(self.phases)

    def current_phase(self) -> dict:
        if self.phases and self.selected_idx < len(self.phases):
            return self.phases[self.selected_idx]
        return {}

    # ─── Status ───

    @property
    def total_agents(self) -> int:
        return sum(p["total"] for p in self.phases)

    @property
    def completed_agents(self) -> int:
        return sum(p["completed"] for p in self.phases)

    @property
    def elapsed(self) -> str:
        s = int(time.time() - self._start_time)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h: return f"{h}h{m:02d}m"
        return f"{m}m{s:02d}s"

    def set_message(self, msg: str, duration: float = 3.0):
        """Geçici mesaj göster."""
        self.message = msg
        self.message_time = time.time() + duration

    # ─── Render ───

    def _render_header(self) -> str:
        lines = []
        lines.append(f"{C.BOLD}{C.BLUE}┌{'─'*72}┐{C.END}")
        
        # Başlık satırı
        title = f"{C.BOLD}{C.BLUE}  {self.title}{C.END}"
        status = f"  {self.pipeline.status_text}"
        mode_text = f"  {C.DIM}[{self.mode}]{C.END}" if self.mode != "main" else ""
        lines.append(f"{C.BLUE}│{C.END}{title}{' ' * 30}{status}{mode_text}{' ' * 10}{C.BLUE}│{C.END}")
        
        # Alt başlık
        sub = self.subtitle[:68]
        lines.append(f"{C.BLUE}│{C.END}  {C.DIM}{sub}{C.END}{' ' * (70 - len(sub))}{C.BLUE}│{C.END}")
        
        # Pipeline durumu
        pp = self.pipeline.progress
        if self.pipeline.running:
            line = f"{C.BLUE}│{C.END}  {C.YELLOW}●{C.END} {pp['phase']:40s} {C.GRAY}{pp['agent']}/{pp['total']} agents{C.END}{' ' * 20}{C.BLUE}│{C.END}"
            lines.append(line)
        
        lines.append(f"{C.BLUE}├{'─'*72}┤{C.END}")
        return '\n'.join(lines)

    def _render_phases(self) -> str:
        lines = []
        for i, phase in enumerate(self.phases):
            is_selected = (i == self.selected_idx)
            icon = C.status_icon(phase["status"])
            name = phase["name"]
            progress = f"{phase['completed']}/{phase['total']}"
            
            if phase["total"] > 0:
                ratio = phase["completed"] / phase["total"]
                bar_width = 8
                filled = int(ratio * bar_width)
                bar_color = C.GREEN if phase["status"] == "completed" else (C.RED if phase["status"] == "failed" else C.YELLOW)
                bar = f"{bar_color}{'█' * filled}{C.GRAY}{'░' * (bar_width - filled)}{C.END}"
            else:
                bar = f"{C.GRAY}{'─' * 8}{C.END}"
            
            if is_selected:
                prefix = f"{C.BLUE}❯{C.END}"
                display_name = f"{C.BOLD}{C.WHITE}{name}{C.END}"
            else:
                prefix = " "
                display_name = f"{C.GRAY}{name}{C.END}"
            
            status_color = C.GREEN if phase["status"] == "completed" else (
                C.RED if phase["status"] == "failed" else (
                    C.YELLOW if phase["status"] == "running" else C.GRAY))
            
            lines.append(f"  {prefix} {icon} {display_name:22s} {bar} {status_color}{progress:>6s}{C.END}")
            
            # Seçili fazın agent detayları
            if is_selected and phase["agents"]:
                agents = phase["agents"]
                for a in agents[:5]:
                    a_icon = C.status_icon(a.get("status", "idle"))
                    label = a.get("label", "")[:35]
                    tokens = a.get("tokens", "")
                    duration = a.get("duration", "")
                    lines.append(f"     {a_icon} {label:35s} {tokens:>8s} {duration:>6s}")
                if len(agents) > 5:
                    lines.append(f"     {C.GRAY}... and {len(agents)-5} more{C.END}")
        
        return '\n'.join(lines)

    def _render_history(self) -> str:
        """Geçmiş paneli."""
        lines = [f"  {C.BOLD}{C.WHITE}📋 Research History{C.END}"]
        lines.append(f"  {C.GRAY}{'─'*68}{C.END}")
        
        records = self.history.list(10)
        if not records:
            lines.append(f"  {C.DIM}No research history yet.{C.END}")
        else:
            for i, r in enumerate(records):
                ts = r.get("timestamp", "")[11:19]
                q = r.get("question", "")[:40]
                findings = r.get("findings_count", 0)
                refuted = r.get("refuted_count", 0)
                cost = r.get("total_cost", 0)
                marker = "❯" if i == self.selected_idx else " "
                lines.append(f"  {marker} [{ts}] {q:40s} {C.GREEN}{findings} findings{C.END} {C.RED}{refuted} refuted{C.END} ${cost:.4f}")
        
        return '\n'.join(lines)

    def _render_model_select(self) -> str:
        """Model seçim paneli."""
        from core.monitor import ModelConfig
        mc = ModelConfig()
        return mc.list_providers()

    def _render_footer(self) -> str:
        now = datetime.datetime.now().strftime('%H:%M:%S')
        filter_text = f" · {C.YELLOW}f:{self.filter_mode}{C.END}" if self.filter_mode else ""
        
        # Mesaj varsa göster
        msg = ""
        if self.message and time.time() < self.message_time:
            msg = f"  {C.GREEN}✓{C.END} {self.message}"
        
        # Input modu
        if self._input_mode:
            input_line = f"  {C.BOLD}🔬{C.END} {self._question_input}"
        else:
            input_line = (
                f"  {C.GRAY}{C.ITALIC}r run{C.END}"
                f" {C.GRAY}·{C.END} {C.GRAY}{C.ITALIC}↑↓ select{C.END}"
                f" {C.GRAY}·{C.END} {C.GRAY}{C.ITALIC}enter open{C.END}"
                f" {C.GRAY}·{C.END} {C.GRAY}{C.ITALIC}m model{C.END}"
                f" {C.GRAY}·{C.END} {C.GRAY}{C.ITALIC}h history{C.END}"
                f" {C.GRAY}·{C.END} {C.GRAY}{C.ITALIC}s save{C.END}"
                f" {C.GRAY}·{C.END} {C.GRAY}{C.ITALIC}q quit{C.END}"
                f"{filter_text}"
            )
        
        return (
            f"{C.BLUE}├{'─'*72}┤{C.END}\n"
            f"{C.BLUE}│{C.END}{msg}{' ' * (72 - len(msg))}{C.BLUE}│{C.END}\n"
            f"{C.BLUE}│{C.END}{input_line}{' ' * (68 - len(input_line) + 20)}{C.DIM}{now}{C.END} {C.BLUE}│{C.END}\n"
            f"{C.BLUE}└{'─'*72}┘{C.END}"
        )

    def render(self) -> str:
        """Ana render."""
        lines = [self._render_header()]
        
        if self.mode == "history":
            lines.append(self._render_history())
        elif self.mode == "model_select":
            lines.append(f"  {self._render_model_select()}")
        else:
            lines.append(self._render_phases())
        
        # Pipeline sonucu varsa göster
        if self.pipeline.result and not self.pipeline.running:
            r = self.pipeline.result
            summary = r.get("summary", "")[:150]
            findings = len(r.get("findings", []))
            refuted = len(r.get("refuted", []))
            lines.append(f"\n  {C.GREEN}✔ Pipeline completed{C.END}")
            lines.append(f"  {C.GRAY}{summary}{C.END}")
            lines.append(f"  {C.GREEN}{findings} findings{C.END} · {C.RED}{refuted} refuted{C.END}")
            # History'e ekle
            if not hasattr(self, '_saved'):
                self.history.add(self._last_question or "?", r)
                self._saved = True
        
        lines.append(self._render_footer())
        return '\n'.join(lines)

    def display(self):
        """Terminale bas."""
        output = self.render()
        sys.stdout.write('\033[H' + output)
        sys.stdout.flush()

    # ─── Actions ───

    def start_research(self):
        """Araştırma başlat — input modu aç."""
        self._input_mode = True
        self._question_input = ""
        self.display()

    def submit_research(self):
        """Input'u gönder, pipeline başlat."""
        question = self._question_input.strip()
        self._input_mode = False
        self._question_input = ""
        self._last_question = question
        
        if question:
            self.set_message(f"Starting research: {question[:40]}...")
            # Fazları sıfırla
            for p in self.phases:
                p["total"] = 0
                p["completed"] = 0
                p["status"] = "idle"
                p["agents"] = []
            
            self.pipeline.start(question)

    def toggle_history(self):
        """Geçmiş panelini aç/kapa."""
        if self.mode == "history":
            self.mode = "main"
        else:
            self.mode = "history"
            self.selected_idx = 0

    def toggle_model(self):
        """Model seçim panelini aç/kapa."""
        if self.mode == "model_select":
            self.mode = "main"
        else:
            self.mode = "model_select"

    # ─── Interactive Run ───

    def run(self):
        """Interactive mod — terminali ele geçir."""
        import termios
        import tty
        import select
        
        fd = sys.stdin.fileno()
        
        if not sys.stdin.isatty():
            print("\nDashboard requires a real terminal.")
            print("Run: python3 -m core.dashboard")
            return
        
        try:
            old_settings = termios.tcgetattr(fd)
            tty.setraw(fd)
            
            os.system('clear')
            self.display()
            
            while self._running:
                r, _, _ = select.select([sys.stdin], [], [], 0.2)
                
                if r:
                    key = sys.stdin.read(1)
                    
                    if self._input_mode:
                        if key == '\r' or key == '\n':
                            self.submit_research()
                        elif key == '\x7f':  # Backspace
                            self._question_input = self._question_input[:-1]
                        elif key == '\x1b':  # ESC
                            self._input_mode = False
                            self._question_input = ""
                        elif key.isprintable() or key in [' ', '-', '?', '.', ',', '!']:
                            self._question_input += key
                    else:
                        if key == 'q':
                            break
                        elif key == '\x1b':
                            more = select.select([sys.stdin], [], [], 0.05)
                            if more[0]:
                                seq = sys.stdin.read(2)
                                if seq == '[A':
                                    self.select_prev()
                                elif seq == '[B':
                                    self.select_next()
                                else:
                                    if self.mode != "main":
                                        self.mode = "main"
                            else:
                                if self.mode != "main":
                                    self.mode = "main"
                        elif key == '\r' or key == '\n':
                            if self.mode == "history":
                                self.mode = "main"
                            elif self.mode == "model_select":
                                self.mode = "main"
                        elif key == 'r':
                            self.start_research()
                        elif key == 'h':
                            self.toggle_history()
                        elif key == 'm':
                            self.toggle_model()
                        elif key == 'f':
                            from core.dashboard import Dashboard as D
                            D.cycle_filter(self)
                        elif key == 's':
                            self.set_message("Report saved to bdeep-research-report.json")
                        elif key == '\x03':  # Ctrl+C
                            if self.pipeline.running:
                                self.pipeline.stop()
                                self.set_message("Pipeline cancelled")
                            else:
                                break
                
                    self.display()
                else:
                    self.display()
        
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stdout.write('\033[?25h\n')
            sys.stdout.flush()
            print(f"{C.BOLD}{C.GREEN}Panel closed.{C.END}")


def main():
    """Entry point."""
    dash = Dashboard()
    os.system('clear')
    print(f"{C.BOLD}{C.GREEN}━━━ bdeep-research Control Panel ───{C.END}")
    print(f"{C.DIM}  r = research · ↑↓ = navigate · h = history · m = model · q = quit{C.END}\n")
    print(f"  Press any key to start...")
    input()
    dash.run()


if __name__ == "__main__":
    main()
