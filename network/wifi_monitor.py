import platform
import subprocess
import threading
import time

import customtkinter as ctk


class WiFiMonitor:
    def __init__(self, parent_frame):
        self.parent_frame = parent_frame
        self.wifi_status_label = None
        self.wifi_monitor_running = False
        self.current_status = None
        self.setup_ui()
        self.start_monitor()

    def setup_ui(self):
        """Create the WiFi status label (initially hidden)"""
        self.wifi_status_label = ctk.CTkLabel(
            self.parent_frame,
            text="",
            text_color="red"
        )
        self.wifi_status_label.grid(
            row=7, column=0, columnspan=3,
            padx=10, pady=5, sticky="w"
        )
        self.wifi_status_label.grid_remove()  # Start hidden

    def check_wifi_status(self):
        """Ping Google's DNS multiple times and return average latency."""
        try:
            param = "-n" if platform.system().lower() == "windows" else "-c"
            latencies = []

            for _ in range(3):
                result = subprocess.run(
                    ["ping", param, "1", "8.8.8.8"],  # 1 ping per run
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5,
                    text=True
                )

                if result.returncode == 0:
                    output = result.stdout
                    if "time=" in output:
                        try:
                            time_str = output.split("time=")[-1].split("ms")[0].strip()
                            latency = float(time_str)
                            latencies.append(latency)
                        except ValueError:
                            pass
                else:
                    # If a ping fails, append a high value to reflect bad latency
                    latencies.append(9999)

            if not latencies:
                return ("disconnected", "No internet connection")

            avg_latency = sum(latencies) / len(latencies)
            if avg_latency < 150:
                return ("good", f"Average latency: {avg_latency:.1f}ms")
            else:
                return ("slow", f"High latency ({avg_latency:.1f}ms)")

        except Exception:
            return ("error", "Network test failed")

    def update_display(self):
        """Show/hide the status label based on connection quality"""
        status, message = self.current_status
        if status in ("slow", "disconnected", "error"):
            self.wifi_status_label.configure(
                text=f"⚠️ Slow Wifi: {message}",
                text_color="orange" if status == "slow" else "red"
            )
            self.wifi_status_label.grid()
        else:
            self.wifi_status_label.grid_remove()

    def monitor_wifi_status(self):
        """Background thread to check connection regularly"""
        while self.wifi_monitor_running:
            self.current_status = self.check_wifi_status()
            while True:
                try:
                    self.update_display()
                    break
                except RuntimeError:
                    pass
            time.sleep(5)  # Check every 20 seconds

    def start_monitor(self):
        """Start the monitoring thread"""
        if not self.wifi_monitor_running:
            self.wifi_monitor_running = True
            wifi_thread = threading.Thread(
                target=self.monitor_wifi_status,
                daemon=True
            )
            wifi_thread.start()

    def stop_monitor(self):
        """Stop the monitoring thread"""
        self.wifi_monitor_running = False