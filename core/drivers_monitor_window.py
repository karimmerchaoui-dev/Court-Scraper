import threading
import time
from io import BytesIO
from queue import Queue

import customtkinter as ctk
from PIL import Image


class DriverMonitorWindow:
    """Window to monitor all drivers in the pool with screenshots and logs"""

    def __init__(self, parent, driver_pool):
        self.parent = parent
        self.driver_pool = driver_pool
        self.window = None
        self.is_monitoring = False
        self.monitor_thread = None
        self.driver_frames = {}
        self.screenshot_labels = {}
        self.log_texts = {}
        self.update_interval = 0.2  # seconds between screenshot updates
        self.screenshot_queue = Queue()
        self.current_driver_index = 0  # Track which driver to update next
        self.fullscreen_windows = {}  # Track fullscreen windows per driver
        self.current_images = {}  # Store current images for each driver
        self.zoom_levels = {}  # Track zoom level per driver
        self.pan_positions = {}  # Track pan position per driver

    def cleanup_driver_data(self, driver_id):
        """Clean up all data for a driver"""
        if driver_id in self.driver_frames:
            try:
                self.driver_frames[driver_id]["frame"].destroy()
            except:
                pass
            del self.driver_frames[driver_id]

        if driver_id in self.screenshot_labels:
            del self.screenshot_labels[driver_id]

        if driver_id in self.log_texts:
            del self.log_texts[driver_id]

        if driver_id in self.current_images:
            del self.current_images[driver_id]

        if driver_id in self.zoom_levels:
            del self.zoom_levels[driver_id]

        if driver_id in self.pan_positions:
            del self.pan_positions[driver_id]

        self.close_fullscreen(driver_id)

    def open_monitor_window(self):
        """Open the driver monitoring window"""
        if self.window is not None and self.window.winfo_exists():
            self.window.focus()
            return

        # Clean up any stale data from previous window
        self.driver_frames.clear()
        self.screenshot_labels.clear()
        self.current_images.clear()
        self.zoom_levels.clear()
        self.pan_positions.clear()
        self.fullscreen_windows.clear()

        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Driver Pool Monitor")
        self.window.geometry("1400x900")

        # Configure grid
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(1, weight=1)

        # Header frame
        header_frame = ctk.CTkFrame(self.window)
        header_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(header_frame, text="Driver Pool Monitor",
                     font=("Arial", 20, "bold")).pack(side="left", padx=10)

        # Status label
        self.status_label = ctk.CTkLabel(header_frame, text="Active Drivers: 0",
                                         font=("Arial", 12))
        self.status_label.pack(side="left", padx=20)


        # Scrollable frame for drivers
        self.scroll_frame = ctk.CTkScrollableFrame(self.window)
        self.scroll_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # Start monitoring
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        # Start screenshot queue processing
        self.window.after(200, self.process_screenshot_queue)

    def open_fullscreen(self, driver_id):
        """Open fullscreen window for a specific driver with zoom capability"""
        # Close existing fullscreen for this driver if open
        if driver_id in self.fullscreen_windows and self.fullscreen_windows[driver_id].winfo_exists():
            self.fullscreen_windows[driver_id].focus()
            return

        # Initialize zoom and pan for this driver
        self.zoom_levels[driver_id] = 1.0
        self.pan_positions[driver_id] = [0, 0]

        # Create fullscreen window
        fs_window = ctk.CTkToplevel(self.window)
        fs_window.title(f"Driver {driver_id} - Fullscreen")
        fs_window.attributes('-fullscreen', True)
        fs_window.configure(fg_color="black")
        fs_window.lift()
        fs_window.attributes("-topmost", True)

        # Control panel at top
        control_frame = ctk.CTkFrame(fs_window, fg_color="gray20")
        control_frame.place(relx=0.5, rely=0.05, anchor="center")

        # Close button
        close_btn = ctk.CTkButton(
            control_frame,
            text="✕ Exit (ESC)",
            command=lambda: self.close_fullscreen(driver_id),
            width=120,
            height=35,
            fg_color="red",
            hover_color="darkred"
        )
        close_btn.pack(side="left", padx=5, pady=5)

        # Zoom controls
        ctk.CTkLabel(control_frame, text="Zoom:", font=("Arial", 12)).pack(side="left", padx=(10, 5))

        zoom_out_btn = ctk.CTkButton(
            control_frame,
            text="−",
            width=35,
            height=35,
            command=lambda: self.zoom_image(driver_id, -0.2),
            font=("Arial", 16, "bold")
        )
        zoom_out_btn.pack(side="left", padx=2)

        zoom_label = ctk.CTkLabel(control_frame, text="100%", font=("Arial", 12), width=60)
        zoom_label.pack(side="left", padx=5)

        zoom_in_btn = ctk.CTkButton(
            control_frame,
            text="+",
            width=35,
            height=35,
            command=lambda: self.zoom_image(driver_id, 0.2),
            font=("Arial", 16, "bold")
        )
        zoom_in_btn.pack(side="left", padx=2)

        reset_btn = ctk.CTkButton(
            control_frame,
            text="Reset",
            width=70,
            height=35,
            command=lambda: self.reset_zoom(driver_id)
        )
        reset_btn.pack(side="left", padx=5)

        # Canvas for image with scrolling capability
        canvas = ctk.CTkCanvas(fs_window, bg="black", highlightthickness=0)
        canvas.place(relx=0.5, rely=0.55, anchor="center", relwidth=0.95, relheight=0.85)

        # Create image label on canvas
        img_label = ctk.CTkLabel(canvas, text="Loading...", fg_color="black")
        canvas_window = canvas.create_window(0, 0, anchor="nw", window=img_label)

        # Mouse drag for panning
        drag_data = {"x": 0, "y": 0, "dragging": False}

        def on_mouse_press(event):
            drag_data["x"] = event.x
            drag_data["y"] = event.y
            drag_data["dragging"] = True
            canvas.config(cursor="fleur")

        def on_mouse_release(event):
            drag_data["dragging"] = False
            canvas.config(cursor="")

        def on_mouse_drag(event):
            if drag_data["dragging"]:
                dx = event.x - drag_data["x"]
                dy = event.y - drag_data["y"]
                self.pan_positions[driver_id][0] += dx
                self.pan_positions[driver_id][1] += dy
                drag_data["x"] = event.x
                drag_data["y"] = event.y
                self.update_fullscreen_image(driver_id, self.current_images.get(driver_id))

        canvas.bind("<ButtonPress-1>", on_mouse_press)
        canvas.bind("<ButtonRelease-1>", on_mouse_release)
        canvas.bind("<B1-Motion>", on_mouse_drag)

        # Mouse wheel for zooming
        def on_mousewheel(event):
            if event.delta > 0:
                self.zoom_image(driver_id, 0.1)
            else:
                self.zoom_image(driver_id, -0.1)

        canvas.bind("<MouseWheel>", on_mousewheel)  # Windows/MacOS
        canvas.bind("<Button-4>", lambda e: self.zoom_image(driver_id, 0.1))  # Linux scroll up
        canvas.bind("<Button-5>", lambda e: self.zoom_image(driver_id, -0.1))  # Linux scroll down

        # Bind ESC key to close
        fs_window.bind('<Escape>', lambda e: self.close_fullscreen(driver_id))

        # Store references
        self.fullscreen_windows[driver_id] = fs_window
        self.driver_frames[driver_id]["fullscreen_label"] = img_label
        self.driver_frames[driver_id]["fullscreen_canvas"] = canvas
        self.driver_frames[driver_id]["fullscreen_zoom_label"] = zoom_label

        # Update with current image if available
        if driver_id in self.current_images:
            self.update_fullscreen_image(driver_id, self.current_images[driver_id])

    def zoom_image(self, driver_id, delta):
        """Zoom in or out on fullscreen image"""
        if driver_id not in self.zoom_levels:
            return

        # Update zoom level (clamp between 0.5x and 5x)
        self.zoom_levels[driver_id] = max(0.5, min(5.0, self.zoom_levels[driver_id] + delta))

        # Update zoom label
        if driver_id in self.driver_frames and "fullscreen_zoom_label" in self.driver_frames[driver_id]:
            zoom_pct = int(self.zoom_levels[driver_id] * 100)
            self.driver_frames[driver_id]["fullscreen_zoom_label"].configure(text=f"{zoom_pct}%")

        # Redraw image
        if driver_id in self.current_images:
            self.update_fullscreen_image(driver_id, self.current_images[driver_id])

    def reset_zoom(self, driver_id):
        """Reset zoom and pan to default"""
        self.zoom_levels[driver_id] = 1.0
        self.pan_positions[driver_id] = [0, 0]

        if driver_id in self.driver_frames and "fullscreen_zoom_label" in self.driver_frames[driver_id]:
            self.driver_frames[driver_id]["fullscreen_zoom_label"].configure(text="100%")

        if driver_id in self.current_images:
            self.update_fullscreen_image(driver_id, self.current_images[driver_id])

    def close_fullscreen(self, driver_id):
        """Close fullscreen window for a specific driver"""
        if driver_id in self.fullscreen_windows:
            fs = self.fullscreen_windows[driver_id]
            try:
                self.fullscreen_windows[driver_id].destroy()
                fs.attributes("-topmost", False)
                fs.destroy()
            except:
                pass
            del self.fullscreen_windows[driver_id]

            # Clean up fullscreen references
            if driver_id in self.driver_frames:
                self.driver_frames[driver_id].pop("fullscreen_label", None)
                self.driver_frames[driver_id].pop("fullscreen_canvas", None)
                self.driver_frames[driver_id].pop("fullscreen_zoom_label", None)

    def update_fullscreen_image(self, driver_id, image):
        """Update fullscreen image if window is open"""
        if not image or driver_id not in self.fullscreen_windows:
            return

        if not self.fullscreen_windows[driver_id].winfo_exists():
            return

        try:
            fs_window = self.fullscreen_windows[driver_id]
            canvas = self.driver_frames[driver_id].get("fullscreen_canvas")
            img_label = self.driver_frames[driver_id].get("fullscreen_label")

            if not canvas or not img_label:
                return

            # Get canvas size
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()

            if canvas_width < 10 or canvas_height < 10:  # Canvas not ready yet
                fs_window.after(100, lambda: self.update_fullscreen_image(driver_id, image))
                return

            # Calculate size with zoom
            img_width, img_height = image.size
            zoom = self.zoom_levels.get(driver_id, 1.0)

            # Base scale to fit canvas at 100% zoom
            base_scale = min(canvas_width / img_width, canvas_height / img_height) * 0.95
            final_scale = base_scale * zoom

            new_width = int(img_width * final_scale)
            new_height = int(img_height * final_scale)

            # Apply pan offset
            pan_x, pan_y = self.pan_positions.get(driver_id, [0, 0])

            # Center image plus pan offset
            x_pos = (canvas_width - new_width) // 2 + pan_x
            y_pos = (canvas_height - new_height) // 2 + pan_y

            # Create CTkImage
            photo = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=(new_width, new_height)
            )
            img_label.configure(image=photo, text="")
            img_label.image = photo

            # Update canvas window position
            canvas.coords(canvas.find_all()[0], x_pos, y_pos)

        except Exception as e:
            print(f"Error updating fullscreen image: {e}")

    def update_single_driver_image(self, driver_id, image):
        """Update both thumbnail and fullscreen if open"""
        # Store current image
        self.current_images[driver_id] = image

        # Update thumbnail
        if driver_id in self.screenshot_labels:
            try:
                label = self.screenshot_labels[driver_id]
                if label.winfo_exists():
                    photo = ctk.CTkImage(light_image=image, dark_image=image, size=(380, 214))
                    label.configure(image=photo, text="")
                    label.image = photo
            except Exception as e:
                print(f"Error updating thumbnail: {e}")

        # Update fullscreen if open
        self.update_fullscreen_image(driver_id, image)

    def process_screenshot_queue(self):
        """Process images captured in background threads"""
        try:
            while not self.screenshot_queue.empty():
                driver_id, image = self.screenshot_queue.get()
                self.update_single_driver_image(driver_id, image)
        except Exception as e:
            print(f"Error processing screenshot queue: {e}")

        if self.is_monitoring and self.window and self.window.winfo_exists():
            self.window.after(200, self.process_screenshot_queue)

    def update_interval_changed(self, value):
        """Update the refresh interval"""
        self.update_interval = int(value)
        try:
            if self.window and self.window.winfo_exists():
                self.status_label.configure(text=f"Active Drivers: {len(self.driver_pool.in_use)} | "
                                                 f"Update: {self.update_interval}s")
        except:
            pass

    def capture_and_queue(self, driver, driver_id):
        """Capture screenshot in background and queue it for UI update"""
        try:
            image = self.capture_screenshot(driver)
            if image:
                self.screenshot_queue.put((driver_id, image))
        except Exception as e:
            print(f"Error capturing screenshot in background: {e}")

    def force_refresh(self):
        """Force an immediate refresh of all drivers"""
        self.update_all_drivers()



    def create_driver_frame(self, driver_id, driver_index):
        """Create a frame for a single driver with screenshot and log"""
        frame = ctk.CTkFrame(self.scroll_frame, corner_radius=10, border_width=2)
        frame.grid(row=driver_index, column=0, padx=5, pady=5, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        # Left side - Screenshot
        screenshot_frame = ctk.CTkFrame(frame, width=400, height=200)
        screenshot_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        screenshot_frame.grid_propagate(False)
        # Header with fullscreen button
        header_frame = ctk.CTkFrame(screenshot_frame)
        header_frame.pack(pady=5, fill="x")

        header_label = ctk.CTkLabel(
            header_frame,
            text=f"Driver {driver_index + 1} (ID: {driver_id})",
            font=("Arial", 14, "bold")
        )
        header_label.pack(side="left", padx=10)

        # Fullscreen button
        fullscreen_btn = ctk.CTkButton(
            header_frame,
            text="⛶",  # Fullscreen icon
            width=30,
            height=30,
            command=lambda: self.open_fullscreen(driver_id),
            fg_color="transparent",
            hover_color="gray30",
            border_width=1,
            font=("Arial", 16)
        )
        fullscreen_btn.pack(side="right", padx=5)

        # Screenshot display
        screenshot_label = ctk.CTkLabel(screenshot_frame, text="Loading screenshot...")
        screenshot_label.pack(expand=True, fill="both", padx=5, pady=5)
        self.screenshot_labels[driver_id] = screenshot_label

        # Driver state label
        state_label = ctk.CTkLabel(screenshot_frame, text="State: Unknown",
                                   font=("Arial", 10))
        state_label.pack(pady=5)
        self.driver_frames[driver_id] = {"state_label": state_label, "frame": frame}

        # Right side - Logs
        log_frame = ctk.CTkFrame(frame)
        log_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        # Log header
        ctk.CTkLabel(log_frame, text="Thread Logs",
                     font=("Arial", 12, "bold")).grid(row=0, column=0, pady=5, sticky="w", padx=5)

        # Log text box
        log_text = ctk.CTkTextbox(log_frame, wrap="word", font=("Consolas", 9),
                                  height=150, width=600)
        log_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.log_texts[driver_id] = log_text

        return frame

    def capture_screenshot(self, driver):
        """Capture screenshot from driver and convert to PIL Image"""
        try:
            # Get screenshot as PNG and don't resize yet (keep original quality)
            png_data = driver.get_screenshot_as_png()
            image = Image.open(BytesIO(png_data))

            # Create thumbnail version for the list view
            thumbnail = image.copy()
            thumbnail.thumbnail((1080, 1920), Image.Resampling.BILINEAR)
            return thumbnail
        except Exception as e:
            return None

    def update_driver_state_in_background(self, driver, driver_id):
        """Get driver state and URL in background thread"""
        try:
            # Temporary: Simulate states for testing
            states = ['idle', 'logging in', 'entering docket', 'downloading', 'captcha', 'downloading oc retrying']

            # Use a deterministic but changing state for testing
            state_index = (driver_id // 100) % len(states)  # Some pseudo-random but consistent state
            state = driver.state

            # Or for random states:
            # state = random.choice(states)

            url = None
            try:
                url = driver.current_url
                if len(url) > 60:
                    url = url[:57] + "..."
            except:
                pass

            # Queue the update for main thread
            if self.window and self.window.winfo_exists():
                self.window.after(0, self.update_driver_state_ui, driver_id, state, url)
        except Exception as e:
            print(f"Error getting driver state: {e}")

    def update_driver_state_ui(self, driver_id, state, url):
        """Update driver state in UI (main thread)"""
        try:
            if driver_id not in self.driver_frames:
                return

            state_label = self.driver_frames[driver_id].get("state_label")
            if not state_label or not state_label.winfo_exists():
                return

            state_color = {
                'idle': 'green',
                'logging in': 'orange',
                'entering docket': 'yellow',
                'downloading': 'cyan',
                'captcha': 'red'
            }.get(state, 'orange')

            text = f"State: {state}"
            if url:
                text += f" | URL: {url}"

            state_label.configure(text=text, text_color=state_color)
        except Exception as e:
            print(f"Error updating driver state UI: {e}")

    def update_driver_display(self, driver, driver_id, driver_index, update_screenshot=False):
        """Update screenshot and info for a single driver"""
        try:
            # Only capture screenshot if requested (round-robin)
            if update_screenshot:
                threading.Thread(
                    target=self.capture_and_queue,
                    args=(driver, driver_id),
                    daemon=True
                ).start()

            # Update driver state in background thread (non-blocking)
            threading.Thread(
                target=self.update_driver_state_in_background,
                args=(driver, driver_id),
                daemon=True
            ).start()

        except Exception as e:
            print(f"Error updating driver display: {e}")

    def update_all_drivers(self):
        """Update displays for all active drivers (but only screenshot one)"""
        if not self.is_monitoring or not self.window or not self.window.winfo_exists():
            return

        try:
            # Get all active drivers
            all_drivers = self.driver_pool.in_use + self.driver_pool.available

            # Update status
            active_count = len(self.driver_pool.in_use)
            total_count = len(all_drivers)
            self.status_label.configure(
                text=f"Active: {active_count} | Available: {total_count - active_count} | "
                     f"Update: {self.update_interval}s"
            )

            # Remove frames for drivers that no longer exist
            current_driver_ids = {id(driver) for driver in all_drivers}
            for driver_id in list(self.driver_frames.keys()):
                if driver_id not in current_driver_ids:
                    self.cleanup_driver_data(driver_id)

            # Determine which driver gets screenshot update this cycle
            if all_drivers:
                # Wrap around if index is out of bounds
                if self.current_driver_index >= len(all_drivers):
                    self.current_driver_index = 0

                driver_to_screenshot = all_drivers[self.current_driver_index]
                driver_to_screenshot_id = id(driver_to_screenshot)

                # Move to next driver for next cycle
                self.current_driver_index = (self.current_driver_index + 1) % len(all_drivers)
            else:
                driver_to_screenshot_id = None

            # Update or create frames for each driver
            for index, driver in enumerate(all_drivers):
                driver_id = id(driver)

                # Create frame if it doesn't exist
                if driver_id not in self.driver_frames:
                    self.create_driver_frame(driver_id, index)

                # Update the display (only screenshot the selected driver)
                update_screenshot = (driver_id == driver_to_screenshot_id)
                self.update_driver_display(driver, driver_id, index, update_screenshot)

        except Exception as e:
            pass

    def monitor_loop(self):
        """Main monitoring loop that runs in background thread"""
        while self.is_monitoring:
            try:
                if self.window and self.window.winfo_exists():
                    # Schedule update on main thread
                    self.window.after(0, self.update_all_drivers)
                    time.sleep(self.update_interval)
                else:
                    break
            except Exception as e:
                print(f"Error in monitor loop: {e}")
                time.sleep(1)

    def append_log(self, driver_id, message):
        """Append a log message to a specific driver's log box"""
        try:
            if driver_id in self.log_texts:
                log_widget = self.log_texts[driver_id]
                if log_widget.winfo_exists():
                    log_widget.insert("end", f"{message}\n")
                    log_widget.see("end")

                    # Keep only last 100 lines
                    lines = log_widget.get("1.0", "end").split("\n")
                    if len(lines) > 100:
                        log_widget.delete("1.0", f"{len(lines) - 100}.0")
        except Exception as e:
            print(f"Error appending log: {e}")

    def on_close(self):
        """Handle window close"""
        self.is_monitoring = False

        # Close all fullscreen windows
        for driver_id in list(self.fullscreen_windows.keys()):
            self.close_fullscreen(driver_id)

        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)

        # Clear all data
        self.driver_frames.clear()
        self.screenshot_labels.clear()
        self.current_images.clear()
        self.zoom_levels.clear()
        self.pan_positions.clear()

        if self.window:
            self.window.destroy()
            self.window = None


# Enhanced pysnooper wrapper to capture logs to GUI
class DriverLogger:
    """Custom logger that captures pysnooper output and sends to GUI"""

    def __init__(self, driver_id, monitor_window):
        self.driver_id = driver_id
        self.monitor_window = monitor_window
        self.buffer = []
        self.lock = threading.Lock()
        self.last_flush = time.time()
        self.flush_interval = 0.1  # Flush every 100ms to reduce GUI updates

    def write(self, text):
        """Capture text and send to GUI (thread-safe)"""
        if not text.strip():
            return

        with self.lock:
            self.buffer.append(text.strip())

            # Auto-flush if buffer is large or enough time has passed
            current_time = time.time()
            if len(self.buffer) >= 10 or (current_time - self.last_flush) >= self.flush_interval:
                self._flush_buffer()
                self.last_flush = current_time

    def _flush_buffer(self):
        """Internal method to flush buffer to GUI"""
        if not self.buffer:
            return

        try:
            if self.monitor_window and self.monitor_window.window:
                # Combine multiple lines into one message for efficiency
                message = '\n'.join(self.buffer)

                # Schedule GUI update on main thread
                self.monitor_window.window.after(0,
                                                 self.monitor_window.append_log,
                                                 self.driver_id,
                                                 message
                                                 )
                self.buffer.clear()
        except Exception as e:
            print(f"Error flushing to GUI: {e}")
            self.buffer.clear()  # Clear buffer to prevent memory leak

    def flush(self):
        """Explicitly flush buffer"""
        with self.lock:
            self._flush_buffer()

    def close(self):
        """Close logger and flush remaining buffer"""
        self.flush()

    def __del__(self):
        """Ensure buffer is flushed when logger is destroyed"""
        try:
            self.flush()
        except:
            pass


