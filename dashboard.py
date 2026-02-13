from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Label, ProgressBar, RichLog, Static
from textual.reactive import reactive
from textual.worker import Worker, WorkerState
import asyncio
import websockets
import json
import logging
import subprocess
import os

# Configuration
SENTINEL_LOG_PATH = "/tmp/sentinel.log" # Monitoring the main sentinel log
URI = "ws://127.0.0.1:18789"
TOKEN = "98a78e62552017edb19a9302e7eee104d51902e215381f66" # Dev token

class ContextMonitor(Static):
    """Widget to display context usage."""
    usage_percent = reactive(0.0)
    total_tokens = reactive(0)
    limit_tokens = reactive(0)

    def compose(self) -> ComposeResult:
        yield Label("Context Window Usage", classes="header-label")
        yield ProgressBar(total=100, show_eta=False, id="context-bar")
        yield Label("0 / 0 tokens (0%)", id="context-label")

    def watch_usage_percent(self, value: float) -> None:
        try:
            bar = self.query_one("#context-bar", ProgressBar)
            bar.update(progress=value)
            
            label = self.query_one("#context-label", Label)
            label.update(f"{self.total_tokens:,} / {self.limit_tokens:,} tokens ({value:.1f}%)")
            
            if value > 90:
                bar.styles.color = "red"
            elif value > 75:
                bar.styles.color = "yellow"
            else:
                bar.styles.color = "green"
        except Exception:
            pass

class LogViewer(ScrollableContainer):
    """Widget to display logs."""
    
    def compose(self) -> ComposeResult:
        yield Label("Sentinel Logs", classes="header-label")
        yield RichLog(id="log-view", markup=True, highlight=True, wrap=True)

    def write_log(self, content: str):
        log_view = self.query_one("#log-view", RichLog)
        log_view.write(content)

class SentinelDashboard(App):
    """A Textual app to monitor and control Sentinel."""

    CSS = """
    Screen {
        layout: vertical;
    }

    .header-label {
        text-align: center;
        text-style: bold;
        background: $primary;
        color: $text;
        width: 100%;
        padding: 1;
        margin-bottom: 1;
    }

    #sidebar {
        width: 30;
        dock: left;
        background: $surface;
        padding: 1;
        border-right: solid $primary;
    }

    #content {
        width: 1fr;
        padding: 1;
    }

    Button {
        width: 100%;
        margin-bottom: 1;
    }

    #context-bar {
        width: 100%;
        margin-bottom: 1;
    }
    
    #log-view {
        height: 1fr;
        border: solid $accent;
        background: $surface-darken-1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main"):
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Label("Quick Actions", classes="header-label")
                    yield Button("Trigger Daily Briefing", id="btn-briefing", variant="primary")
                    yield Button("Restart Sentinel", id="btn-restart", variant="error")
                    yield Static("\nSystem Status:\nUNKNOWN", id="status-text")
                
                with Vertical(id="content"):
                    yield ContextMonitor(id="context-monitor")
                    yield LogViewer(id="logs")
                    
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Sentinel Dashboard"
        self.run_worker(self.monitor_context_usage, exclusive=True, group="monitor")
        self.run_worker(self.tail_logs, exclusive=True, group="logs")

    async def monitor_context_usage(self):
        """Polls OpenClaw for context usage."""
        monitor_widget = self.query_one("#context-monitor", ContextMonitor)
        status_widget = self.query_one("#status-text", Static)
        
        while True:
            try:
                async with websockets.connect(URI) as websocket:
                    status_widget.update("\nSystem Status:\nCONNECTED (Gateway)")
                    
                    # Auth
                    connect_req = {
                        "id": "init", "type": "req", "method": "connect",
                        "params": {
                            "auth": { "token": TOKEN },
                            "client": { "mode": "probe", "platform": "darwin", "version": "2026.2.9", "id": "openclaw-probe" },
                            "minProtocol": 3, "maxProtocol": 3
                        }
                    }
                    await websocket.send(json.dumps(connect_req))
                    # Consume auth response (simplistic)
                    await websocket.recv() 

                    while True:
                        req = { "id": "poll", "type": "req", "method": "sessions.list", "params": { "limit": 1 } }
                        await websocket.send(json.dumps(req))
                        resp = await websocket.recv()
                        data = json.loads(resp)
                        
                        if data.get("id") == "poll" and data.get("ok"):
                            sessions = data.get("payload", {}).get("sessions", [])
                            defaults = data.get("payload", {}).get("defaults", {})
                            if sessions:
                                session = sessions[0]
                                total = session.get("totalTokens", 0)
                                limit = session.get("contextTokens") or defaults.get("contextTokens") or 1048576
                                
                                if limit > 0:
                                    percent = (total / limit) * 100
                                    monitor_widget.total_tokens = total
                                    monitor_widget.limit_tokens = limit
                                    monitor_widget.usage_percent = percent
                        
                        await asyncio.sleep(2)

            except Exception as e:
                status_widget.update(f"\nSystem Status:\nDISCONNECTED\n({str(e)})")
                await asyncio.sleep(5)

    async def tail_logs(self):
        """Tails the sentinel log file."""
        log_viewer = self.query_one("#logs", LogViewer)
        
        if not os.path.exists(SENTINEL_LOG_PATH):
             log_viewer.write_log(f"Waiting for log file: {SENTINEL_LOG_PATH}...")
        
        # Simple polling tail implementation
        file_pos = 0
        while True:
            if os.path.exists(SENTINEL_LOG_PATH):
                with open(SENTINEL_LOG_PATH, "r") as f:
                    f.seek(file_pos)
                    lines = f.readlines()
                    if lines:
                         for line in lines:
                             log_viewer.write_log(line.strip())
                         file_pos = f.tell()
            await asyncio.sleep(1)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-briefing":
            self.notify("Triggering Daily Briefing...")
            # Run the python script directly as a subprocess
            subprocess.Popen(["./daily_briefing.sh"], shell=True)
            
        elif event.button.id == "btn-restart":
            self.notify("Restart functionality not yet implemented via UI (Use Ctrl+C in terminal)", severity="warning")

if __name__ == "__main__":
    app = SentinelDashboard()
    app.run()
