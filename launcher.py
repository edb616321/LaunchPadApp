"""
Command Center LaunchPad
A visual application launcher for multi-monitor setups
Built with CustomTkinter
"""

import customtkinter as ctk
import tkinter as tk
import screeninfo
import json
import os
import subprocess
import time
import pygetwindow as gw
from tkinter import messagebox, filedialog
from typing import Dict, List, Optional
import threading
from datetime import datetime
from PIL import Image, ImageTk
import win32ui
import win32gui
import win32con
import win32api
import requests
from io import BytesIO
from urllib.parse import urlparse
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import sqlite3
import webbrowser
import urllib3

# Import QuickFiles file manager and QuickPlayer
from quickfiles import QuickFilesWidget
from quickplayer import QuickPlayerWidget

# Suppress SSL warnings for internal servers with self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
APP_TITLE = "Command Center LaunchPad"
APPS_FILE = "apps.json"
CONFIG_FILE = "config.json"

# VIBRANT SATURATED Blue Theme - NO GREY!
COLORS = {
    "bg_dark": "#001A4D",        # DEEP SATURATED NAVY BLUE
    "card_bg": "#0047AB",        # VIBRANT COBALT BLUE (very saturated)
    "card_hover": "#0066FF",     # BRIGHT BLUE hover
    "text": "#FFFFFF",           # BRIGHT WHITE text
    "accent": "#00BFFF",         # VIVID SKY BLUE buttons
    "accent_hover": "#1E90FF",   # DODGER BLUE hover
}


class CommandCenterApp(ctk.CTk):
    """Main application window"""

    def __init__(self):
        # Set appearance mode BEFORE calling super().__init__()
        ctk.set_appearance_mode("dark")

        super().__init__()

        # Window configuration
        self.title(APP_TITLE)

        # Get monitor configuration
        self.monitors = self.get_monitors()
        self.ultra_wide = self.identify_monitor_by_characteristics('ultra-wide')

        # Position launcher on the ultra-wide monitor (5120x1440)
        if self.ultra_wide:
            x = self.ultra_wide.x
            y = self.ultra_wide.y

            # Set initial geometry then maximize
            self.geometry(f"3000x1400+{x}+{y}")
            print(f"[LAUNCHER] Positioned on ultra-wide at ({x}, {y})")

            # Auto-maximize after window is created
            self.after(100, lambda: self.state('zoomed'))
            print(f"[LAUNCHER] Auto-maximizing window")
        else:
            # Fallback if ultra-wide not found
            self.geometry("1500x800")
            print("[LAUNCHER] Warning: Ultra-wide not found, using default position")

        # Configure colors
        self.configure(fg_color=COLORS["bg_dark"])

        # Initialize data
        self.apps = []
        self.selected_monitor = 0  # Default to M3 (screeninfo index 0 - top-front monitor)

        # Icon cache to avoid re-extracting icons on every refresh
        self.icon_cache = {}

        # Build UI
        self.setup_ui()

        # Load apps
        self.load_apps()

    def get_monitors(self) -> List[screeninfo.Monitor]:
        """Get all connected monitors"""
        try:
            monitors = screeninfo.get_monitors()
            # Log monitor configuration for debugging
            print("=" * 60)
            print("MONITOR CONFIGURATION DETECTED:")
            for i, m in enumerate(monitors):
                print(f"  Index {i}: {m.width}x{m.height} at ({m.x}, {m.y})")
            print("=" * 60)
            return monitors
        except Exception as e:
            print(f"Error getting monitors: {e}")
            return []

    def identify_monitor_by_characteristics(self, role: str) -> Optional[screeninfo.Monitor]:
        """Identify a monitor by its physical characteristics (resolution, position)

        Roles: 'ultra-wide', 'top-front', 'left', 'right'
        """
        for m in self.monitors:
            # Ultra-wide: 5120x1440 resolution (unique)
            if role == 'ultra-wide' and m.width == 5120 and m.height == 1440:
                return m

            # Top-front (primary): 1920x1080 at (0, 0)
            if role == 'top-front' and m.width == 1920 and m.height == 1080 and m.x == 0 and m.y == 0:
                return m

            # Left monitor: 1920x1080 at negative X, far left (most negative X)
            if role == 'left' and m.width == 1920 and m.height == 1080 and m.x < -3000:
                return m

            # Right monitor: 1920x1080 at positive X, far right (most positive X)
            if role == 'right' and m.width == 1920 and m.height == 1080 and m.x > 3000:
                return m

        return None

    def get_monitor_by_index(self, index: int) -> Optional[screeninfo.Monitor]:
        """Get a monitor by logical index (M2, M3, M4) - uses characteristic-based detection

        Logical mapping:
        - index 0 = M3 = top-front monitor (1920x1080 at 0,0)
        - index 2 = M4 = right monitor (1920x1080 at positive X)
        - index 3 = M2 = left monitor (1920x1080 at negative X)
        - NEVER use ultra-wide (5120x1440) for app launching!
        """
        # Map logical indices to monitor roles
        role_map = {
            0: 'top-front',  # M3 default
            2: 'right',      # M4
            3: 'left'        # M2
        }

        role = role_map.get(index)
        if role:
            monitor = self.identify_monitor_by_characteristics(role)
            if monitor:
                print(f"[MONITOR] Logical index {index} -> {role} monitor at ({monitor.x}, {monitor.y})")
                return monitor

        # Fallback to top-front if not found
        print(f"[MONITOR] Warning: Could not find monitor for index {index}, defaulting to top-front")
        return self.identify_monitor_by_characteristics('top-front')

    def setup_ui(self):
        """Setup the user interface"""

        # Main container with padding
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Top bar with title and controls - EVEN BIGGER
        top_bar = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_dark"], height=120)
        top_bar.pack(fill="x", pady=(0, 20))
        top_bar.pack_propagate(False)

        # Reposition button (fix window position) - on far left
        reposition_btn = ctk.CTkButton(
            top_bar,
            text="📍",
            width=50,
            height=50,
            font=ctk.CTkFont(size=24),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["accent"],
            command=self.reposition_window
        )
        reposition_btn.pack(side="left", padx=(10, 5), pady=10)

        # Title - BIGGER
        title_label = ctk.CTkLabel(
            top_bar,
            text=APP_TITLE,
            font=ctk.CTkFont(size=40, weight="bold"),
            text_color=COLORS["text"]
        )
        title_label.pack(side="left", padx=15, pady=10)

        # Monitor selector buttons
        monitor_frame = ctk.CTkFrame(top_bar, fg_color=COLORS["bg_dark"])
        monitor_frame.pack(side="left", padx=35, pady=10)

        ctk.CTkLabel(
            monitor_frame,
            text="Launch on:",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left", padx=(0, 18))

        # Monitor buttons (M2, M3, M4) - map to correct physical monitors
        # M2 = screeninfo index 3 (Monitor 4 - LEFT), M3 = screeninfo index 0 (Monitor 3 - TOP-FRONT), M4 = screeninfo index 2 (Monitor 2 - RIGHT)
        # (skipping index 1 which is the ultra-wide launcher monitor)
        self.monitor_buttons = {}
        monitor_mapping = [3, 0, 2]  # M2=left(3), M3=top-front(0) DEFAULT, M4=right(2)
        for i, label in enumerate(["M2", "M3", "M4"], start=0):
            physical_index = monitor_mapping[i]
            btn = ctk.CTkButton(
                monitor_frame,
                text=label,
                width=95,
                height=60,
                font=ctk.CTkFont(size=22, weight="bold"),
                fg_color=COLORS["card_bg"],
                hover_color=COLORS["accent"],
                command=lambda m=physical_index: self.select_monitor(m)
            )
            btn.pack(side="left", padx=6)
            self.monitor_buttons[physical_index] = btn

        # Set M3 as default selected monitor (highlight the button)
        self.select_monitor(0)  # M3 = screeninfo index 0

        # BIGGER Date/Time label - after monitor buttons
        self.datetime_label = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(size=36, weight="bold"),
            text_color=COLORS["accent"]
        )
        self.datetime_label.pack(side="left", padx=45, pady=10)

        # Volume Control
        volume_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        volume_frame.pack(side="left", padx=30, pady=10)

        volume_label = ctk.CTkLabel(
            volume_frame,
            text="🔊",
            font=ctk.CTkFont(size=28)
        )
        volume_label.pack(side="left", padx=(0, 10))

        self.volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0,
            to=100,
            width=200,
            height=20,
            command=self.set_volume,
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            progress_color=COLORS["accent"]
        )
        self.volume_slider.pack(side="left")

        # Initialize volume slider to current system volume
        self.init_volume()

        # Mouse wheel anywhere in CCL = system volume control
        self.bind_all('<MouseWheel>', self._on_mousewheel_volume)

        # URL/Web Search bar
        search_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        search_frame.pack(side="left", padx=30, pady=10)

        search_label = ctk.CTkLabel(
            search_frame,
            text="🔍",
            font=ctk.CTkFont(size=28)
        )
        search_label.pack(side="left", padx=(0, 10))

        self.url_search_entry = ctk.CTkEntry(
            search_frame,
            width=400,
            height=50,
            font=ctk.CTkFont(size=20),
            placeholder_text="Enter URL or search query...",
            fg_color=COLORS["card_bg"],
            border_color=COLORS["accent"],
            text_color=COLORS["text"]
        )
        self.url_search_entry.pack(side="left", padx=(0, 10))
        self.url_search_entry.bind("<Return>", self._on_url_search_submit)

        go_btn = ctk.CTkButton(
            search_frame,
            text="Go",
            width=70,
            height=50,
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._on_url_search_click
        )
        go_btn.pack(side="left")

        # Add App button - BIGGER
        add_btn = ctk.CTkButton(
            top_bar,
            text="+ Add App",
            width=175,
            height=65,
            font=ctk.CTkFont(size=22, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self.add_app_dialog
        )
        add_btn.pack(side="right", padx=12, pady=10)

        # Settings button - BIGGER
        settings_btn = ctk.CTkButton(
            top_bar,
            text="Settings",
            width=155,
            height=65,
            font=ctk.CTkFont(size=22, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self.show_settings
        )
        settings_btn.pack(side="right", padx=6, pady=10)

        # Start time update loop
        self.update_datetime()

        # Content area: Split into 3 RESIZABLE panels using PanedWindow
        # Using tk.PanedWindow for resizable panels
        content_paned = tk.PanedWindow(
            main_frame,
            orient=tk.HORIZONTAL,
            bg=COLORS["bg_dark"],
            sashwidth=8,  # Width of the draggable sash
            sashrelief=tk.RAISED,
            sashpad=2
        )
        content_paned.pack(fill="both", expand=True)

        # Left side: App shortcuts (initial width 900px, resizable)
        left_frame = ctk.CTkFrame(content_paned, fg_color=COLORS["bg_dark"])

        # Scrollable frame for app grid
        self.scroll_frame = ctk.CTkScrollableFrame(
            left_frame,
            fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["card_bg"],
            scrollbar_button_hover_color=COLORS["card_hover"]
        )
        self.scroll_frame.pack(fill="both", expand=True)

        # Configure grid for app cards
        self.app_grid = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS["bg_dark"])
        self.app_grid.pack(fill="both", expand=True)

        content_paned.add(left_frame, width=600, minsize=200, stretch="never")  # 20%

        # Middle: QuickPlayer video player (35%)
        middle_frame = ctk.CTkFrame(content_paned, fg_color=COLORS["bg_dark"])

        # Create QuickPlayer widget
        self.quickplayer = QuickPlayerWidget(
            middle_frame,
            log_callback=self.log_message
        )
        self.quickplayer.pack(fill="both", expand=True)

        content_paned.add(middle_frame, width=1200, minsize=300, stretch="never")  # 40%

        # Hidden log storage (for log_message compatibility)
        self.log_messages = []
        self.activity_log_frame = None  # No visible log frame

        # Right side: QuickFiles file manager (takes remaining space, resizable)
        right_frame = ctk.CTkFrame(content_paned, fg_color=COLORS["bg_dark"])

        # Create QuickFiles widget with play_callback to QuickPlayer
        self.quickfiles = QuickFilesWidget(
            right_frame,
            log_callback=self.log_message,
            play_callback=self.quickplayer.load_file  # Play media in QuickPlayer
        )
        self.quickfiles.pack(fill="both", expand=True)

        content_paned.add(right_frame, minsize=600, stretch="always")

        # Log welcome message
        self.log_message("Command Center LaunchPad initialized", "success")

    def select_monitor(self, monitor_index: int):
        """Select target monitor for app launching"""
        self.selected_monitor = monitor_index

        # Update button colors to show selection
        for idx, btn in self.monitor_buttons.items():
            if idx == monitor_index:
                btn.configure(fg_color=COLORS["accent"])
            else:
                btn.configure(fg_color=COLORS["card_bg"])

    def reposition_window(self):
        """Reposition window to correct location on ultra-wide monitor"""
        # Refresh monitor info in case it changed
        self.monitors = self.get_monitors()
        self.ultra_wide = self.identify_monitor_by_characteristics('ultra-wide')

        if self.ultra_wide:
            x = self.ultra_wide.x
            y = self.ultra_wide.y

            # First restore window if maximized (prevents issues)
            self.state('normal')
            self.update()

            # Set correct size and position
            self.geometry(f"3000x1400+{x}+{y}")

            # Force update
            self.update_idletasks()

            self.log_message(f"Window repositioned to ({x}, {y})", "success")
            print(f"[REPOSITION] Moved window to ultra-wide at ({x}, {y})")
        else:
            self.log_message("Ultra-wide monitor not found!", "error")
            print("[REPOSITION] ERROR: Ultra-wide monitor not detected")

    def update_datetime(self):
        """Update the date/time display"""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M:%S %p")
        self.datetime_label.configure(text=f"{date_str}  •  {time_str}")

        # Update every second
        self.after(1000, self.update_datetime)

    def get_volume_interface(self):
        """Get the Windows audio interface"""
        try:
            from pycaw.pycaw import AudioUtilities

            devices = AudioUtilities.GetSpeakers()
            return devices.EndpointVolume
        except Exception as e:
            print(f"Error getting volume interface: {e}")
            return None

    def init_volume(self):
        """Initialize volume slider to current system volume"""
        try:
            volume = self.get_volume_interface()
            if volume:
                current_volume = volume.GetMasterVolumeLevelScalar() * 100
                self.volume_slider.set(current_volume)
        except Exception as e:
            print(f"Error initializing volume: {e}")
            self.volume_slider.set(50)  # Default to 50% if error

    def set_volume(self, value):
        """Set system volume from slider"""
        try:
            volume = self.get_volume_interface()
            if volume:
                # Convert 0-100 to 0.0-1.0
                volume.SetMasterVolumeLevelScalar(value / 100, None)
        except Exception as e:
            print(f"Error setting volume: {e}")

    def _on_mousewheel_volume(self, event):
        """Mouse wheel adjusts system volume - only in header/quick links area"""
        # Walk up widget tree to check what area the scroll is in
        try:
            widget = event.widget
            while widget:
                name = widget.__class__.__name__
                # Skip if inside QuickPlayer (has its own volume control)
                if name == 'QuickPlayerWidget':
                    return
                # Skip if inside QuickFiles (needs scroll for file browsing)
                if name in ('FileListPane', 'QuickFilesWidget'):
                    return
                widget = widget.master
        except Exception:
            pass

        # Also skip any scrollable widget directly (safety net)
        try:
            cls = event.widget.winfo_class().lower()
            if 'canvas' in cls or 'listbox' in cls or 'text' in cls or 'treeview' in cls:
                return
        except Exception:
            pass

        # Adjust system volume by 2% per scroll notch
        delta = 2 if event.delta > 0 else -2
        try:
            volume = self.get_volume_interface()
            if volume:
                current = volume.GetMasterVolumeLevelScalar() * 100
                new_vol = max(0, min(100, current + delta))
                volume.SetMasterVolumeLevelScalar(new_vol / 100, None)
                self.volume_slider.set(new_vol)
        except Exception:
            pass

    def _on_url_search_submit(self, event):
        """Handle Enter key in URL/search bar"""
        self._handle_url_search()

    def _on_url_search_click(self):
        """Handle Go button click"""
        self._handle_url_search()

    def _handle_url_search(self):
        """Process URL or search query from the search bar"""
        query = self.url_search_entry.get().strip()
        if not query:
            return

        # Check if it's a URL (starts with http/https or looks like a domain)
        is_url = (
            query.startswith("http://") or
            query.startswith("https://") or
            query.startswith("www.") or
            ("." in query and " " not in query and "/" in query) or
            (query.count(".") >= 1 and " " not in query and len(query.split(".")[-1]) <= 4)
        )

        if is_url:
            # It's a URL - open directly
            url = query
            if not url.startswith("http"):
                url = "https://" + url
            self.log_message(f"Opening URL: {url}", "info")
            webbrowser.open(url)
        else:
            # It's a search query - use Google search
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            self.log_message(f"Web search: {query}", "info")
            webbrowser.open(search_url)

        # Clear the entry after submission
        self.url_search_entry.delete(0, "end")

    def log_message(self, message: str, level: str = "info"):
        """Log a message (prints to console only now that Activity Log is replaced)"""
        # Get current timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Print to console for debugging (handle unicode/emoji encoding errors)
        try:
            print(f"[{timestamp}] [{level.upper()}] {message}")
        except UnicodeEncodeError:
            # Windows console can't handle emojis, print ASCII-safe version
            safe_message = message.encode('ascii', errors='replace').decode('ascii')
            print(f"[{timestamp}] [{level.upper()}] {safe_message}")

    def clear_activity_log(self):
        """Clear activity log (no-op, log display removed)"""
        self.log_messages = []
        print("[LOG] Activity log cleared")

    def load_apps(self):
        """Load apps from JSON file"""
        if os.path.exists(APPS_FILE):
            try:
                with open(APPS_FILE, 'r') as f:
                    self.apps = json.load(f)
            except Exception as e:
                print(f"Error loading apps: {e}")
                self.apps = []
        else:
            # Create sample apps for demonstration
            # Use screeninfo indices: 0, 2, 3 (NOT 1 - that's the launcher monitor!)
            self.apps = [
                {
                    "name": "Chrome",
                    "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    "category": "Web",
                    "monitor": 0  # M3 = screeninfo index 0 (DEFAULT - top-front)
                },
                {
                    "name": "VS Code",
                    "path": "C:\\Users\\edb616321\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
                    "category": "Development",
                    "monitor": 0  # M3 = screeninfo index 0 (DEFAULT - top-front)
                },
                {
                    "name": "Notepad",
                    "path": "notepad.exe",
                    "category": "Tools",
                    "monitor": 0  # M3 = screeninfo index 0 (DEFAULT - top-front)
                },
            ]
            self.save_apps()

        self.refresh_app_grid()

    def save_apps(self):
        """Save apps to JSON file"""
        try:
            with open(APPS_FILE, 'w') as f:
                json.dump(self.apps, f, indent=2)
        except Exception as e:
            error_msg = f"Failed to save apps: {str(e)}"
            self.log_message(error_msg, "error")
            messagebox.showerror("Error", error_msg)

    def refresh_app_grid(self):
        """Refresh the app grid display"""
        # Clear existing widgets
        for widget in self.app_grid.winfo_children():
            widget.destroy()

        # Group apps by category
        categories = {}
        for app in self.apps:
            cat = app.get("category", "Other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(app)

        # Define custom category order (Quick Links first, then AI, etc.)
        category_order = [
            "Quick Links",
            "AI",
            "Remote",
            "Development",
            "File Managers",
            "Utilities",
            "Web",
            "Productivity",
            "Media",
            "Games",
            "Learning and Certifications",
            "Other"
        ]

        # Sort categories by custom order
        def category_sort_key(cat):
            try:
                return category_order.index(cat)
            except ValueError:
                return len(category_order)  # Put unknown categories at the end

        sorted_categories = sorted(categories.items(), key=lambda x: category_sort_key(x[0]))

        # Cards per row - 3 per row
        cards_per_row = 3

        # Display apps by category
        row = 0
        for category, apps in sorted_categories:
            # Category header - HUGE READABLE FONT
            cat_label = ctk.CTkLabel(
                self.app_grid,
                text=category,
                font=ctk.CTkFont(size=32, weight="bold"),
                text_color=COLORS["accent"],
                anchor="w"
            )
            cat_label.grid(row=row, column=0, columnspan=cards_per_row, sticky="w", pady=(25, 15), padx=10)
            row += 1

            # App cards - dynamic columns based on panel width
            col = 0
            for app in apps:
                self.create_app_card(self.app_grid, app, row, col)
                col += 1
                if col >= cards_per_row:
                    col = 0
                    row += 1

            if col > 0:
                row += 1

    def create_app_card(self, parent, app: Dict, row: int, col: int):
        """Create an app card button with REAL ICON"""

        # Create card frame - 200x200 pixels for MUCH BIGGER readability
        card_frame = ctk.CTkFrame(
            parent,
            fg_color=COLORS["card_bg"],
            corner_radius=12,
            width=200,
            height=200
        )
        card_frame.grid(row=row, column=col, padx=8, pady=8)
        card_frame.grid_propagate(False)

        # Extract and display REAL icon from .exe
        icon_image = self.extract_icon(app['path'], size=100)

        if icon_image:
            # REAL icon from executable
            icon_label = ctk.CTkLabel(
                card_frame,
                image=icon_image,
                text=""
            )
            icon_label.image = icon_image  # Keep reference
        else:
            # Fallback to emoji if icon extraction fails
            emoji_icon = self.get_app_icon(app)
            icon_label = ctk.CTkLabel(
                card_frame,
                text=emoji_icon,
                font=ctk.CTkFont(size=72),
                text_color=COLORS["text"]
            )

        icon_label.pack(expand=True, pady=(15, 0))

        # App name label - HUGE READABLE FONT
        name_label = ctk.CTkLabel(
            card_frame,
            text=app['name'],
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"],
            wraplength=180
        )
        name_label.pack(expand=True, pady=(0, 15))

        # Make the entire frame double-clickable (like Windows)
        card_frame.bind("<Double-Button-1>", lambda e: self.launch_app(app))
        icon_label.bind("<Double-Button-1>", lambda e: self.launch_app(app))
        name_label.bind("<Double-Button-1>", lambda e: self.launch_app(app))

        # Hover effect
        def on_enter(e):
            card_frame.configure(fg_color=COLORS["card_hover"])
        def on_leave(e):
            card_frame.configure(fg_color=COLORS["card_bg"])

        card_frame.bind("<Enter>", on_enter)
        card_frame.bind("<Leave>", on_leave)
        icon_label.bind("<Enter>", on_enter)
        icon_label.bind("<Leave>", on_leave)
        name_label.bind("<Enter>", on_enter)
        name_label.bind("<Leave>", on_leave)

        # Bind right-click for context menu
        card_frame.bind("<Button-3>", lambda e: self.show_context_menu(e, app))
        icon_label.bind("<Button-3>", lambda e: self.show_context_menu(e, app))
        name_label.bind("<Button-3>", lambda e: self.show_context_menu(e, app))

    def extract_icon(self, exe_path: str, size: int = 80):
        """Extract REAL icon from Windows executable or fetch favicon from URL"""
        # Check cache first
        cache_key = f"{exe_path}_{size}"
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]

        try:
            # Handle URLs - fetch favicon
            if exe_path.startswith("http://") or exe_path.startswith("https://"):
                icon = self.fetch_favicon(exe_path, size)
                if icon:
                    self.icon_cache[cache_key] = icon
                return icon

            # Check if file exists
            if not os.path.exists(exe_path):
                return None

            # Extract icon using Windows API
            ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
            ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)

            large, small = win32gui.ExtractIconEx(exe_path, 0)

            if large:
                # Use the large icon
                hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                hbmp = win32ui.CreateBitmap()
                hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
                hdc = hdc.CreateCompatibleDC()

                hdc.SelectObject(hbmp)
                hdc.DrawIcon((0, 0), large[0])

                # Convert to PIL Image
                bmpstr = hbmp.GetBitmapBits(True)
                img = Image.frombuffer(
                    'RGB',
                    (ico_x, ico_y),
                    bmpstr, 'raw', 'BGRX', 0, 1
                )

                # Resize to requested size
                img = img.resize((size, size), Image.Resampling.LANCZOS)

                # Convert to CTkImage for proper HighDPI scaling
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

                # Clean up
                win32gui.DestroyIcon(large[0])
                if small:
                    for icon in small:
                        win32gui.DestroyIcon(icon)

                # Cache the icon
                self.icon_cache[cache_key] = photo
                return photo

        except Exception as e:
            # Suppress expected errors silently:
            # - "Access is denied" for folders
            # - WindowsApps paths (Windows Store apps have restricted access)
            # - "file cannot be accessed" errors
            error_str = str(e).lower()
            is_expected_error = (
                "access is denied" in error_str or
                "windowsapps" in exe_path.lower() or
                "cannot be accessed" in error_str
            )
            if not is_expected_error:
                print(f"Could not extract icon from {exe_path}: {e}")
            return None

        return None

    def fetch_favicon(self, url: str, size: int = 80):
        """Fetch favicon from website URL"""
        try:
            # Parse URL to get domain
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"

            # Try multiple favicon sources
            favicon_urls = [
                # Google's favicon service (most reliable)
                f"https://www.google.com/s2/favicons?domain={parsed.netloc}&sz=256",
                # DuckDuckGo's favicon service
                f"https://icons.duckduckgo.com/ip3/{parsed.netloc}.ico",
                # Direct favicon.ico
                f"{domain}/favicon.ico",
                # Common alternative location
                f"{domain}/apple-touch-icon.png"
            ]

            for favicon_url in favicon_urls[:2]:  # Only try first 2 sources (Google + DuckDuckGo)
                try:
                    # Fetch favicon with short timeout, disable SSL verification for internal IPs
                    verify_ssl = not parsed.netloc.startswith('10.') and not parsed.netloc.startswith('192.168.')
                    response = requests.get(favicon_url, timeout=1, headers={'User-Agent': 'Mozilla/5.0'}, verify=verify_ssl)

                    if response.status_code == 200 and len(response.content) > 0:
                        # Load image from response
                        img = Image.open(BytesIO(response.content))

                        # Convert to RGBA if needed
                        if img.mode != 'RGBA':
                            img = img.convert('RGBA')

                        # Resize to requested size
                        img = img.resize((size, size), Image.Resampling.LANCZOS)

                        # Convert to CTkImage for proper HighDPI scaling
                        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

                        # Only print success for direct domain fetches (not external services)
                        if 'google.com' not in favicon_url and 'duckduckgo.com' not in favicon_url:
                            print(f"[OK] Fetched favicon from: {favicon_url}")
                        return photo

                except Exception as e:
                    # Only print errors for direct domain fetches, not external services
                    if 'google.com' not in favicon_url and 'duckduckgo.com' not in favicon_url:
                        pass  # Suppress noisy errors
                    continue

            # All attempts failed - only print if verbose
            # print(f"Could not fetch favicon for {url}")
            return None

        except Exception as e:
            print(f"Error fetching favicon: {e}")
            return None

    def get_app_icon(self, app: Dict) -> str:
        """Get an icon/emoji for the app based on name or category"""
        name = app['name'].lower()
        category = app.get('category', '').lower()

        # Map app names to emojis
        if 'chrome' in name or 'browser' in name or 'edge' in name or 'firefox' in name:
            return '🌐'
        elif 'code' in name or 'visual studio' in name or 'vscode' in name:
            return '💻'
        elif 'notepad' in name or 'note' in name:
            return '📝'
        elif 'excel' in name:
            return '📊'
        elif 'word' in name:
            return '📄'
        elif 'outlook' in name or 'mail' in name:
            return '📧'
        elif 'spotify' in name or 'music' in name:
            return '🎵'
        elif 'discord' in name or 'slack' in name or 'teams' in name:
            return '💬'
        elif 'photoshop' in name or 'gimp' in name:
            return '🎨'
        elif 'video' in name or 'vlc' in name:
            return '🎬'
        elif 'file' in name or 'explorer' in name:
            return '📁'
        elif 'terminal' in name or 'powershell' in name or 'cmd' in name:
            return '⚡'
        elif 'calculator' in name:
            return '🔢'
        elif 'game' in name or category == 'games':
            return '🎮'
        elif category == 'web':
            return '🌐'
        elif category == 'development':
            return '⚙️'
        elif category == 'tools':
            return '🔧'
        elif category == 'productivity':
            return '📋'
        elif category == 'media':
            return '🎬'
        else:
            return '📦'  # Default icon

    def show_context_menu(self, event, app: Dict):
        """Show context menu for app card"""
        from tkinter import Menu

        menu = Menu(self, tearoff=0, bg=COLORS["card_bg"], fg=COLORS["text"],
                    activebackground=COLORS["accent"], activeforeground=COLORS["text"])

        menu.add_command(label="Edit", command=lambda: self.edit_app_dialog(app))
        menu.add_command(label="Duplicate", command=lambda: self.duplicate_app(app))
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self.delete_app(app))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def edit_app_dialog(self, app: Dict):
        """Show dialog to edit an existing app"""
        # Create dialog window
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Application")
        dialog.geometry("500x400")
        dialog.configure(fg_color=COLORS["bg_dark"])

        # Make dialog modal
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 500) // 2
        y = self.winfo_y() + (self.winfo_height() - 400) // 2
        dialog.geometry(f"500x400+{x}+{y}")

        # Form fields
        frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_dark"])
        frame.pack(fill="both", expand=True, padx=30, pady=30)

        # App Name
        ctk.CTkLabel(frame, text="App Name:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        name_entry = ctk.CTkEntry(frame, width=440, height=35)
        name_entry.insert(0, app["name"])
        name_entry.pack(pady=(0, 15))

        # App Path
        ctk.CTkLabel(frame, text="Path/URL:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        path_frame = ctk.CTkFrame(frame, fg_color=COLORS["bg_dark"])
        path_frame.pack(fill="x", pady=(0, 15))

        path_entry = ctk.CTkEntry(path_frame, width=350, height=35)
        path_entry.insert(0, app["path"])
        path_entry.pack(side="left", padx=(0, 10))

        def browse_file():
            filename = filedialog.askopenfilename(
                title="Select Application",
                filetypes=[("Executables", "*.exe"), ("All Files", "*.*")]
            )
            if filename:
                path_entry.delete(0, "end")
                path_entry.insert(0, filename)

        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=80,
            height=35,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=browse_file
        )
        browse_btn.pack(side="left")

        # Category
        ctk.CTkLabel(frame, text="Category:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        category_var = ctk.StringVar(value=app.get("category", "Other"))
        category_menu = ctk.CTkOptionMenu(
            frame,
            width=440,
            height=35,
            variable=category_var,
            values=["Quick Links", "AI", "Remote", "Development", "File Managers", "Utilities", "Web", "Productivity", "Media", "Games", "Learning and Certifications", "Other"]
        )
        category_menu.pack(pady=(0, 15))

        # Default Monitor
        ctk.CTkLabel(frame, text="Default Monitor:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        # Reverse map: screeninfo index to button label (skipping 1 = ultra-wide)
        monitor_map_reverse = {3: "M2", 0: "M3", 2: "M4"}
        monitor_var = ctk.StringVar(value=monitor_map_reverse.get(app.get("monitor", 0), "M3"))
        monitor_menu = ctk.CTkOptionMenu(
            frame,
            width=440,
            height=35,
            variable=monitor_var,
            values=["M2", "M3", "M4"]
        )
        monitor_menu.pack(pady=(0, 20))

        # Buttons
        button_frame = ctk.CTkFrame(frame, fg_color=COLORS["bg_dark"])
        button_frame.pack(fill="x", pady=(20, 0))

        def save_changes():
            name = name_entry.get().strip()
            path = path_entry.get().strip()

            if not name or not path:
                messagebox.showwarning("Validation Error", "Name and Path are required!")
                return

            # Map M2/M3/M4 to screeninfo indices (skipping 1 = ultra-wide)
            monitor_map = {"M2": 3, "M3": 0, "M4": 2}

            app["name"] = name
            app["path"] = path
            app["category"] = category_var.get()
            app["monitor"] = monitor_map[monitor_var.get()]

            self.save_apps()
            self.refresh_app_grid()
            dialog.destroy()

        save_btn = ctk.CTkButton(
            button_frame,
            text="Save Changes",
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=save_changes
        )
        save_btn.pack(side="right")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            height=40,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=dialog.destroy
        )
        cancel_btn.pack(side="right", padx=(0, 10))

    def duplicate_app(self, app: Dict):
        """Duplicate an app"""
        new_app = app.copy()
        new_app["name"] = f"{app['name']} (Copy)"
        self.apps.append(new_app)
        self.save_apps()
        self.refresh_app_grid()

    def delete_app(self, app: Dict):
        """Delete an app"""
        if messagebox.askyesno("Delete App", f"Are you sure you want to delete '{app['name']}'?"):
            self.apps.remove(app)
            self.save_apps()
            self.refresh_app_grid()

    def launch_app(self, app: Dict):
        """Launch an application - NEVER launch on monitor index 1 (ultra-wide)"""
        try:
            path = app["path"]
            # DEFAULT TO M3 (index 0 - top-front monitor) - NEVER use index 1 (ultra-wide launcher monitor)
            # IMPORTANT: Use "is not None" check because monitor index 0 is falsy!
            monitor = self.selected_monitor if self.selected_monitor is not None else app.get("monitor", 0)

            # CRITICAL SAFEGUARD: Never allow monitor 1 (ultra-wide)
            if monitor == 1:
                print(f"ERROR: Attempted to launch {app['name']} on monitor 1 (ultra-wide)! Forcing to M3 (index 0 - top-front)")
                self.log_message(f"Safeguard: Prevented launch on ultra-wide", "warning")
                monitor = 0

            app_name = app["name"]

            # Get monitor name for logging
            monitor_names = {0: "M3 (Top-Front)", 2: "M4 (Right)", 3: "M2 (Left)"}
            monitor_display = monitor_names.get(monitor, f"Monitor {monitor}")

            # Log the launch
            self.log_message(f"Launching {app_name} on {monitor_display}", "info")

            # Check if it's a URL
            if path.startswith("http://") or path.startswith("https://"):
                webbrowser.open(path)
                self.log_message(f"Opened URL: {app_name}", "success")
                return
            # Check if it's a folder path
            elif os.path.isdir(path):
                # Open folder in Windows File Explorer
                os.startfile(path)
                print(f"Opened folder: {path}")
                self.log_message(f"Opened folder: {app_name}", "success")
                return  # Don't try to position window for folders
            # Check if it's a Python script
            elif path.endswith(".py"):
                # Run Python scripts with python.exe
                python_path = "C:\\Python314\\python.exe"
                process = subprocess.Popen([python_path, path], cwd=os.path.dirname(path))
                print(f"Launched Python script: {path}")
                self.log_message(f"Started Python script: {app_name}", "success")
                return  # Don't try to position window for console scripts
            else:
                # Launch executable (with optional arguments)
                args = app.get("args", [])  # Get optional args from JSON
                if args:
                    process = subprocess.Popen([path] + args)
                else:
                    process = subprocess.Popen([path])

                # Position window on target monitor with AGGRESSIVE retries
                def position_window():
                    # Wait for window to fully load
                    time.sleep(3.0)

                    # Try MANY times - apps MUST NOT stay on M1 (ultra-wide)
                    success = False
                    for attempt in range(10):  # Increased from 5 to 10 attempts
                        try:
                            if self.move_window_to_monitor(app_name, monitor):
                                print(f"[OK] Successfully positioned {app_name} on monitor {monitor} (attempt {attempt + 1})")
                                success = True
                                break
                            time.sleep(0.7)  # Wait between attempts
                        except Exception as e:
                            print(f"[FAIL] Attempt {attempt + 1} failed: {e}")
                            time.sleep(0.7)

                    if success:
                        self.after(0, lambda: self.log_message(f"Positioned {app_name} successfully", "success"))
                    else:
                        print(f"ERROR: Failed to position {app_name} after 10 attempts! App may be on wrong monitor!")
                        self.after(0, lambda: self.log_message(f"Failed to position {app_name} - manual adjustment needed", "warning"))

                # Run positioning in separate thread to not block UI
                threading.Thread(target=position_window, daemon=True).start()

            print(f"[LAUNCH] Starting {app_name} -> target monitor {monitor} (M2=index 3, M3=index 0, M4=index 2)")

        except Exception as e:
            error_msg = f"Failed to launch {app['name']}: {str(e)}"
            self.log_message(error_msg, "error")
            messagebox.showerror("Launch Error", error_msg)

    def move_window_to_monitor(self, app_name: str, monitor_index: int) -> bool:
        """Move a window to a specific monitor - returns True if successful"""
        try:
            # Get the target monitor
            target_monitor = self.get_monitor_by_index(monitor_index)
            if not target_monitor:
                print(f"Monitor {monitor_index} not found")
                return False

            # Find windows with matching title (partial match - flexible)
            all_windows = gw.getAllWindows()
            print(f"[SEARCH] Looking for window with name containing '{app_name}'")
            print(f"[SEARCH] Found {len(all_windows)} total windows")

            # Try multiple match strategies
            # 1. Exact substring match
            matching_windows = [w for w in all_windows if app_name.lower() in w.title.lower() and w.visible]
            print(f"[SEARCH] Exact match found {len(matching_windows)} windows")

            # 2. If no match, try matching key words (for "4K Video Downloader" -> "4k", "video", "downloader")
            if not matching_windows:
                keywords = [word.lower() for word in app_name.split() if len(word) > 2]
                print(f"[SEARCH] Trying keyword match with: {keywords}")
                matching_windows = [w for w in all_windows
                                   if any(keyword in w.title.lower() for keyword in keywords) and w.visible]
                print(f"[SEARCH] Keyword match found {len(matching_windows)} windows")

            if matching_windows:
                window = matching_windows[0]  # Take the first match
                print(f"[FOUND] Window: '{window.title}' at ({window.left}, {window.top}) size {window.width}x{window.height}")

                # First, restore window if it's maximized (prevents spanning issues)
                try:
                    if window.isMaximized:
                        print(f"[RESTORE] Window is maximized, restoring...")
                        window.restore()
                        time.sleep(0.3)  # Give it time to restore
                except Exception as e:
                    print(f"[RESTORE] Failed: {e}")

                # Calculate position on target monitor (centered)
                desired_width = 1200
                desired_height = 800

                # Don't make window bigger than monitor
                if desired_width > target_monitor.width - 200:
                    desired_width = target_monitor.width - 200
                if desired_height > target_monitor.height - 200:
                    desired_height = target_monitor.height - 200

                x = target_monitor.x + (target_monitor.width - desired_width) // 2
                y = target_monitor.y + (target_monitor.height - desired_height) // 2

                print(f"[MOVE] Target monitor {monitor_index}: {target_monitor.width}x{target_monitor.height} at ({target_monitor.x}, {target_monitor.y})")
                print(f"[MOVE] Moving window to ({x}, {y}) size ({desired_width}x{desired_height})")

                # Move and resize window
                window.moveTo(x, y)
                time.sleep(0.2)
                window.resizeTo(desired_width, desired_height)

                print(f"[SUCCESS] Moved {app_name} to monitor {monitor_index}")
                return True
            else:
                print(f"[NOT FOUND] No window matching '{app_name}'")
                return False

        except Exception as e:
            print(f"Error moving window: {e}")
            return False

    def add_app_dialog(self):
        """Show dialog to add a new app"""
        # Create dialog window
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Application")
        dialog.geometry("500x400")
        dialog.configure(fg_color=COLORS["bg_dark"])

        # Make dialog modal
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 500) // 2
        y = self.winfo_y() + (self.winfo_height() - 400) // 2
        dialog.geometry(f"500x400+{x}+{y}")

        # Form fields
        frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_dark"])
        frame.pack(fill="both", expand=True, padx=30, pady=30)

        # App Name
        ctk.CTkLabel(frame, text="App Name:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        name_entry = ctk.CTkEntry(frame, width=440, height=35)
        name_entry.pack(pady=(0, 15))

        # App Path
        ctk.CTkLabel(frame, text="Path/URL:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        path_frame = ctk.CTkFrame(frame, fg_color=COLORS["bg_dark"])
        path_frame.pack(fill="x", pady=(0, 15))

        path_entry = ctk.CTkEntry(path_frame, width=350, height=35)
        path_entry.pack(side="left", padx=(0, 10))

        def browse_file():
            filename = filedialog.askopenfilename(
                title="Select Application",
                filetypes=[("Executables", "*.exe"), ("All Files", "*.*")]
            )
            if filename:
                path_entry.delete(0, "end")
                path_entry.insert(0, filename)

        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=80,
            height=35,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=browse_file
        )
        browse_btn.pack(side="left")

        # Category
        ctk.CTkLabel(frame, text="Category:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        category_var = ctk.StringVar(value="Other")
        category_menu = ctk.CTkOptionMenu(
            frame,
            width=440,
            height=35,
            variable=category_var,
            values=["Quick Links", "AI", "Remote", "Development", "File Managers", "Utilities", "Web", "Productivity", "Media", "Games", "Learning and Certifications", "Other"]
        )
        category_menu.pack(pady=(0, 15))

        # Default Monitor
        ctk.CTkLabel(frame, text="Default Monitor:", text_color=COLORS["text"]).pack(anchor="w", pady=(0, 5))
        monitor_var = ctk.StringVar(value="M3")
        monitor_menu = ctk.CTkOptionMenu(
            frame,
            width=440,
            height=35,
            variable=monitor_var,
            values=["M2", "M3", "M4"]
        )
        monitor_menu.pack(pady=(0, 20))

        # Buttons
        button_frame = ctk.CTkFrame(frame, fg_color=COLORS["bg_dark"])
        button_frame.pack(fill="x", pady=(20, 0))

        def save_app():
            name = name_entry.get().strip()
            path = path_entry.get().strip()

            if not name or not path:
                messagebox.showwarning("Validation Error", "Name and Path are required!")
                return

            # Map M2/M3/M4 to screeninfo indices (skipping 1 = ultra-wide)
            monitor_map = {"M2": 3, "M3": 0, "M4": 2}

            new_app = {
                "name": name,
                "path": path,
                "category": category_var.get(),
                "monitor": monitor_map[monitor_var.get()]
            }

            self.apps.append(new_app)
            self.save_apps()
            self.refresh_app_grid()
            dialog.destroy()

        save_btn = ctk.CTkButton(
            button_frame,
            text="Add App",
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=save_app
        )
        save_btn.pack(side="right")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            height=40,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=dialog.destroy
        )
        cancel_btn.pack(side="right", padx=(0, 10))

    def show_settings(self):
        """Show settings dialog"""
        # Create settings dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("600x500")
        dialog.configure(fg_color=COLORS["bg_dark"])

        # Make dialog modal
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 600) // 2
        y = self.winfo_y() + (self.winfo_height() - 500) // 2
        dialog.geometry(f"600x500+{x}+{y}")

        # Settings frame
        frame = ctk.CTkFrame(dialog, fg_color=COLORS["bg_dark"])
        frame.pack(fill="both", expand=True, padx=30, pady=30)

        # Title
        ctk.CTkLabel(
            frame,
            text="Theme Customization",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(anchor="w", pady=(0, 20))

        # Color settings info
        info_text = """
Theme colors (hex values):

Background: Dark gray background of the main window
Card Background: Background color of app cards
Card Hover: Color when hovering over cards
Text Color: Color of all text elements
Accent Color: Color of buttons and highlights
Accent Hover: Color when hovering over accent buttons
        """

        info_label = ctk.CTkLabel(
            frame,
            text=info_text,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"],
            justify="left"
        )
        info_label.pack(anchor="w", pady=(0, 20))

        # Display current colors
        colors_frame = ctk.CTkFrame(frame, fg_color=COLORS["card_bg"], corner_radius=10)
        colors_frame.pack(fill="x", pady=(0, 20), padx=10)

        color_display = ctk.CTkLabel(
            colors_frame,
            text=f"""Current Theme (Mellow Dark):

Background: {COLORS['bg_dark']}
Card Background: {COLORS['card_bg']}
Card Hover: {COLORS['card_hover']}
Text: {COLORS['text']}
Accent: {COLORS['accent']}
Accent Hover: {COLORS['accent_hover']}
            """,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text"],
            justify="left"
        )
        color_display.pack(padx=20, pady=20)

        # Note about customization
        note_label = ctk.CTkLabel(
            frame,
            text="To customize colors, edit the COLORS dictionary in launcher.py\nand restart the application.",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=COLORS["card_hover"],
            justify="center"
        )
        note_label.pack(pady=(10, 20))

        # Close button
        close_btn = ctk.CTkButton(
            frame,
            text="Close",
            width=120,
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=dialog.destroy
        )
        close_btn.pack(pady=(20, 0))


def main():
    """Main entry point"""
    # Force appearance mode and disable default themes
    ctk.set_appearance_mode("dark")
    ctk.deactivate_automatic_dpi_awareness()

    app = CommandCenterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
