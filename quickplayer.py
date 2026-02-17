"""
QuickPlayer - Multi-format Viewer Widget for Command Center LaunchPad
Supports video, audio, images, markdown, HTML, and text files
Uses VLC for media playback with built-in 10-band graphic EQ
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import os
import sys
import socket
import threading
import time as _time
from typing import Optional, Callable

# Raise process priority so audio thread gets more CPU time
try:
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(
        ctypes.windll.kernel32.GetCurrentProcess(), 0x00008000  # ABOVE_NORMAL_PRIORITY_CLASS
    )
except Exception:
    pass

# Port for external "Open with" to send file paths to the running CCL QuickPlayer
QUICKPLAYER_PORT = 51478

# Add VLC to DLL search path
VLC_PATH = r"C:\Program Files\VideoLAN\VLC"
try:
    os.add_dll_directory(VLC_PATH)
except Exception:
    pass
if VLC_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = VLC_PATH + os.pathsep + os.environ["PATH"]

try:
    import vlc
    HAS_VLC = True
except Exception as e:
    HAS_VLC = False
    print(f"[QUICKPLAYER] VLC not available: {e}")

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception as e:
    HAS_PIL = False
    print(f"[QUICKPLAYER] PIL not available: {e}")

try:
    import markdown
    HAS_MARKDOWN = True
except Exception as e:
    HAS_MARKDOWN = False
    print(f"[QUICKPLAYER] Markdown not available: {e}")

# Colors matching CCL theme
COLORS = {
    "bg_dark": "#001A4D",
    "card_bg": "#0047AB",
    "card_hover": "#0066FF",
    "text": "#FFFFFF",
    "accent": "#00BFFF",
    "accent_hover": "#1E90FF",
}

# Supported formats by type
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv', '.mpg', '.mpeg'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico', '.tiff', '.tif'}
TEXT_EXTENSIONS = {'.txt', '.log', '.ini', '.cfg', '.conf', '.json', '.xml', '.yaml', '.yml', '.csv'}
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.html', '.css', '.java', '.c', '.cpp', '.h', '.cs', '.rb', '.go', '.rs', '.php', '.sh', '.bat', '.ps1'}
MARKDOWN_EXTENSIONS = {'.md', '.markdown'}
HTML_EXTENSIONS = {'.html', '.htm'}

# VLC EQ preset names (18 built-in)
VLC_EQ_PRESETS = [
    "Flat", "Classical", "Club", "Dance", "Full Bass",
    "Full Bass+Treble", "Full Treble", "Headphones", "Large Hall",
    "Live", "Party", "Pop", "Reggae", "Rock",
    "Ska", "Soft", "Soft Rock", "Techno"
]

# EQ band center frequencies
EQ_BAND_LABELS = ["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"]


class QuickPlayerWidget(ctk.CTkFrame):
    """Multi-format viewer widget with drag-and-drop support"""

    def __init__(self, parent, log_callback: Optional[Callable[[str, str], None]] = None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self.log_callback = log_callback
        self._vlc_instance: Optional[vlc.Instance] = None
        self.player: Optional[vlc.MediaPlayer] = None
        self._eq: Optional[vlc.AudioEqualizer] = None
        self._eq_enabled = True
        self._eq_default_preset = "Headphones"
        self.current_file: Optional[str] = None
        self.is_playing = False
        self.duration = 0.0
        self.current_mode = "none"  # none, video, image, text
        self.current_image = None  # Keep reference to prevent garbage collection
        self._header_frame = None  # Store reference to header for packing order
        self._eq_panel = None  # EQ panel frame reference
        self._eq_sliders = []  # EQ band slider references
        self._eq_preset_var = None  # StringVar for preset dropdown

        self._setup_ui()
        self._setup_player()
        self._setup_drag_drop()
        self._setup_keybindings()
        self._setup_mousewheel_volume()
        self._start_listener()

    def _start_listener(self):
        """Start TCP listener so external 'Open with' can send file paths to us"""
        def listener_thread():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(('127.0.0.1', QUICKPLAYER_PORT))
                srv.listen(1)
                srv.settimeout(2.0)
                print(f"[QUICKPLAYER] Listening on port {QUICKPLAYER_PORT} for external open requests")
                while True:
                    try:
                        conn, _ = srv.accept()
                        data = conn.recv(4096).decode('utf-8', errors='replace').strip()
                        conn.sendall(b"OK")
                        conn.close()
                        if data and os.path.exists(data):
                            print(f"[QUICKPLAYER] External open: {data}")
                            self.after(0, lambda p=data: self.load_file(p))
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"[QUICKPLAYER] Listener connection error: {e}")
            except Exception as e:
                print(f"[QUICKPLAYER] Listener failed to start: {e}")

        t = threading.Thread(target=listener_thread, daemon=True)
        t.start()

    def _log(self, message: str, level: str = "info"):
        """Log to activity log"""
        if self.log_callback:
            self.log_callback(message, level)

    def _setup_ui(self):
        """Setup the player UI"""
        # Header - BIGGER
        self._header_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], height=70)
        self._header_frame.pack(fill="x", padx=5, pady=5)
        self._header_frame.pack_propagate(False)
        header = self._header_frame

        title = ctk.CTkLabel(
            header,
            text="🎬 QUICKPLAYER",
            font=ctk.CTkFont(size=40, weight="bold"),
            text_color=COLORS["accent"]
        )
        title.pack(side="left", padx=10)

        # Open file button - BIGGER
        open_btn = ctk.CTkButton(
            header,
            text="📂 Open",
            width=140,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["accent"],
            command=self._open_file
        )
        open_btn.pack(side="right", padx=10)

        # Clear button
        clear_btn = ctk.CTkButton(
            header,
            text="✕ Clear",
            width=130,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color="#CC3333",
            command=self.clear
        )
        clear_btn.pack(side="right", padx=5)

        # Pop-Out button
        self.popout_btn = ctk.CTkButton(
            header,
            text="⛶ Pop Out",
            width=160,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["accent"],
            command=self._pop_out
        )
        self.popout_btn.pack(side="right", padx=5)

        # File name label - BIGGER
        self.file_label = ctk.CTkLabel(
            header,
            text="Drop file here or click Open",
            font=ctk.CTkFont(size=24),
            text_color=COLORS["text"]
        )
        self.file_label.pack(side="left", padx=20)

        # === IMAGE CONTROLS BAR (TOP - below header) ===
        self.image_controls_bar = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], height=70)
        # Don't pack yet - only shown for images

        self.fit_btn = ctk.CTkButton(
            self.image_controls_bar,
            text="🔍 Fit to Window",
            width=220,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._fit_image
        )
        self.fit_btn.pack(side="left", padx=15, pady=8)

        self.actual_btn = ctk.CTkButton(
            self.image_controls_bar,
            text="📐 Actual Size",
            width=180,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self._actual_size_image
        )
        self.actual_btn.pack(side="left", padx=10, pady=8)

        # Zoom slider
        self.zoom_label = ctk.CTkLabel(
            self.image_controls_bar,
            text="🔎 Zoom:",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"]
        )
        self.zoom_label.pack(side="left", padx=(30, 5), pady=8)

        self.zoom_slider = ctk.CTkSlider(
            self.image_controls_bar,
            from_=10,
            to=400,
            width=200,
            height=24,
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            progress_color=COLORS["accent"],
            command=self._on_zoom
        )
        self.zoom_slider.pack(side="left", padx=5, pady=8)
        self.zoom_slider.set(100)

        self.zoom_value_label = ctk.CTkLabel(
            self.image_controls_bar,
            text="100%",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"],
            width=70
        )
        self.zoom_value_label.pack(side="left", padx=5, pady=8)

        self.image_info_label = ctk.CTkLabel(
            self.image_controls_bar,
            text="",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=COLORS["text"]
        )
        self.image_info_label.pack(side="left", padx=30, pady=8)

        # Zoom level tracking
        self._zoom_level = 100

        # Main content container (holds all view modes)
        # NOTE: Don't pack yet - will pack after controls are set up
        self.content_container = tk.Frame(self, bg='black')

        # VIDEO VIEW - Video frame for VLC
        self.video_frame = tk.Frame(self.content_container, bg='black')

        # IMAGE VIEW - Scrollable canvas for displaying images
        self.image_frame = tk.Frame(self.content_container, bg='black')

        # Scrollbars
        self.image_vscroll = tk.Scrollbar(self.image_frame, orient="vertical")
        self.image_hscroll = tk.Scrollbar(self.image_frame, orient="horizontal")

        # Canvas with scrollbars
        self.image_canvas = tk.Canvas(
            self.image_frame,
            bg='black',
            highlightthickness=0,
            xscrollcommand=self.image_hscroll.set,
            yscrollcommand=self.image_vscroll.set
        )

        self.image_vscroll.config(command=self.image_canvas.yview)
        self.image_hscroll.config(command=self.image_canvas.xview)

        # Grid layout for canvas + scrollbars
        self.image_canvas.grid(row=0, column=0, sticky="nsew")
        self.image_vscroll.grid(row=0, column=1, sticky="ns")
        self.image_hscroll.grid(row=1, column=0, sticky="ew")

        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        # Bind mousewheel for scrolling
        self.image_canvas.bind("<MouseWheel>", self._on_image_mousewheel)
        self.image_canvas.bind("<Shift-MouseWheel>", self._on_image_shift_mousewheel)

        # TEXT VIEW - Scrollable text widget for text/markdown/html
        self.text_frame = ctk.CTkFrame(self.content_container, fg_color="#0a0a1a")
        self.text_widget = ctk.CTkTextbox(
            self.text_frame,
            fg_color="#0a0a1a",
            text_color="#E0E0E0",
            font=ctk.CTkFont(family="Consolas", size=18),
            wrap="word"
        )
        self.text_widget.pack(fill="both", expand=True, padx=5, pady=5)

        # Placeholder text (shown when nothing loaded) - BIGGER
        self.placeholder = tk.Label(
            self.content_container,
            text="📁\n\nDrag & Drop Files Here\n\nSupports: Video, Audio, Images,\nMarkdown, HTML, Text",
            font=("Segoe UI", 28),
            fg="#6666AA",
            bg="black",
            justify="center"
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # SINGLE Controls bar - ALWAYS VISIBLE at bottom
        self.controls_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], height=80)
        self.controls_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.controls_frame.pack_propagate(False)

        # === VIDEO CONTROLS (left side) ===
        self.video_controls_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.video_controls_frame.pack(side="left", fill="y")

        self.play_btn = ctk.CTkButton(
            self.video_controls_frame,
            text="▶",
            width=80,
            height=60,
            font=ctk.CTkFont(size=32),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._toggle_play
        )
        self.play_btn.pack(side="left", padx=10, pady=10)

        self.stop_btn = ctk.CTkButton(
            self.video_controls_frame,
            text="⏹",
            width=80,
            height=60,
            font=ctk.CTkFont(size=32),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self._stop
        )
        self.stop_btn.pack(side="left", padx=5, pady=10)

        # Skip backward button
        self.skip_back_btn = ctk.CTkButton(
            self.video_controls_frame,
            text="⏪",
            width=70,
            height=60,
            font=ctk.CTkFont(size=28),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=lambda: self._seek_by(-15)
        )
        self.skip_back_btn.pack(side="left", padx=3, pady=10)

        # Skip forward button
        self.skip_fwd_btn = ctk.CTkButton(
            self.video_controls_frame,
            text="⏩",
            width=70,
            height=60,
            font=ctk.CTkFont(size=28),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=lambda: self._seek_by(30)
        )
        self.skip_fwd_btn.pack(side="left", padx=(3, 10), pady=10)

        self.time_label = ctk.CTkLabel(
            self.video_controls_frame,
            text="00:00 / 00:00",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"]
        )
        self.time_label.pack(side="left", padx=15)

        self.progress_slider = ctk.CTkSlider(
            self.video_controls_frame,
            from_=0,
            to=100,
            width=200,
            height=24,
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            progress_color=COLORS["accent"],
            command=self._on_seek
        )
        self.progress_slider.pack(side="left", fill="x", expand=True, padx=15, pady=15)
        self.progress_slider.set(0)

        # EQ button
        self.eq_btn = ctk.CTkButton(
            self.video_controls_frame,
            text="EQ",
            width=60,
            height=60,
            font=ctk.CTkFont(size=22, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self._toggle_eq_panel
        )
        self.eq_btn.pack(side="left", padx=(10, 5), pady=10)

        self.vol_label = ctk.CTkLabel(
            self.video_controls_frame,
            text="🔊",
            font=ctk.CTkFont(size=28)
        )
        self.vol_label.pack(side="left", padx=(10, 5))

        self.volume_slider = ctk.CTkSlider(
            self.video_controls_frame,
            from_=0,
            to=150,
            width=140,
            height=24,
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            progress_color=COLORS["accent"],
            command=self._on_volume
        )
        self.volume_slider.pack(side="left", padx=(0, 5))
        self.volume_slider.set(100)

        self.vol_pct_label = ctk.CTkLabel(
            self.video_controls_frame,
            text="100%",
            font=ctk.CTkFont(size=18),
            text_color=COLORS["text"],
            width=55
        )
        self.vol_pct_label.pack(side="left", padx=(0, 10))

        # Store original image for rescaling
        self._original_image = None
        self._original_image_path = None

        # NOW pack the content container - it expands into remaining space above controls
        self.content_container.pack(fill="both", expand=True, padx=10, pady=5)

    def _setup_player(self):
        """Initialize single VLC Instance + MediaPlayer"""
        if not HAS_VLC:
            print("[QUICKPLAYER] VLC not available, video playback disabled")
            return

        self._poll_timer_id = None

        try:
            # Create VLC instance with minimal options
            self._vlc_instance = vlc.Instance(
                '--no-xlib',
                '--quiet',
                '--no-video-title-show',
            )
            self.player = self._vlc_instance.media_player_new()

            # Initialize EQ with Headphones preset, enabled by default
            headphones_idx = VLC_EQ_PRESETS.index("Headphones")  # index 7
            self._eq = vlc.libvlc_audio_equalizer_new_from_preset(headphones_idx)
            self._eq_enabled = True

            print("[QUICKPLAYER] VLC player initialized")
        except Exception as e:
            print(f"[QUICKPLAYER] Failed to init VLC: {e}")
            self._vlc_instance = None
            self.player = None

    def _start_poll(self):
        """Start polling VLC state every 1000ms"""
        self._stop_poll()

        def poll():
            if not self.player:
                return
            try:
                # Get duration (in ms, convert to seconds)
                dur_ms = self.player.get_length()
                if dur_ms and dur_ms > 0:
                    self.duration = dur_ms / 1000.0

                pos_ms = self.player.get_time()
                if pos_ms is not None and pos_ms >= 0:
                    self._update_time(pos_ms / 1000.0)

                # Update play state
                new_playing = self.player.is_playing() == 1
                if new_playing != self.is_playing:
                    self.is_playing = new_playing
                    self._update_play_button()
            except Exception as e:
                print(f"[QUICKPLAYER] Poll error: {e}")

            # Always reschedule - never let the poll die
            try:
                self._poll_timer_id = self.after(1000, poll)
            except Exception:
                pass

        self._poll_timer_id = self.after(1000, poll)

    def _stop_poll(self):
        """Stop the polling timer"""
        if hasattr(self, '_poll_timer_id') and self._poll_timer_id is not None:
            try:
                self.after_cancel(self._poll_timer_id)
            except Exception:
                pass
            self._poll_timer_id = None

    def _setup_drag_drop(self):
        """Setup drag and drop support"""
        try:
            self.content_container.drop_target_register('DND_Files')
            self.content_container.dnd_bind('<<Drop>>', self._on_drop)
        except:
            pass

        self.content_container.bind('<Button-1>', lambda e: self._open_file())
        self.placeholder.bind('<Button-1>', lambda e: self._open_file())

    def _setup_keybindings(self):
        """Setup keyboard shortcuts for media playback (bound to top-level window)"""
        def bind_to_toplevel():
            try:
                top = self.winfo_toplevel()
                top.bind('<space>', lambda e: self._kb_play_pause(e))
                top.bind('<Left>', lambda e: self._kb_seek(e, -15))
                top.bind('<Right>', lambda e: self._kb_seek(e, 30))
                top.bind('<Shift-Left>', lambda e: self._kb_seek(e, -30))
                top.bind('<Shift-Right>', lambda e: self._kb_seek(e, 30))
                top.bind('<Up>', lambda e: self._kb_volume(e, 5))
                top.bind('<Down>', lambda e: self._kb_volume(e, -5))
                top.bind('<m>', lambda e: self._kb_mute(e))
                top.bind('<M>', lambda e: self._kb_mute(e))
                print("[QUICKPLAYER] Keyboard shortcuts bound to main window")
            except Exception as ex:
                print(f"[QUICKPLAYER] Keybinding error: {ex}")

        self.after(500, bind_to_toplevel)

    def _setup_mousewheel_volume(self):
        """Bind mouse wheel on the player area to adjust player volume"""
        def on_scroll(event):
            if self.current_mode == "video" and self.current_file:
                delta = 5 if event.delta > 0 else -5
                self._adjust_volume(delta)
                return "break"

        self.video_frame.bind('<MouseWheel>', on_scroll)
        self.controls_frame.bind('<MouseWheel>', on_scroll)
        self.content_container.bind('<MouseWheel>', on_scroll)
        self.placeholder.bind('<MouseWheel>', on_scroll)

    def _is_typing(self, event):
        """Check if user is typing in a text input (don't steal keystrokes)"""
        try:
            cls = event.widget.winfo_class().lower()
            return 'entry' in cls or 'text' in cls
        except Exception:
            return False

    def _kb_play_pause(self, event):
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._toggle_play()

    def _kb_seek(self, event, seconds):
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._seek_by(seconds)

    def _kb_volume(self, event, delta):
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._adjust_volume(delta)

    def _kb_mute(self, event):
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._toggle_mute()

    def _seek_by(self, seconds: int):
        """Seek forward or backward by seconds"""
        if self.player and self.current_mode == "video":
            try:
                cur = self.player.get_time()
                if cur is not None and cur >= 0:
                    self.player.set_time(cur + int(seconds * 1000))
            except:
                pass

    def _adjust_volume(self, delta: int):
        """Adjust volume by delta (supports 0-150 range)"""
        current = int(self.volume_slider.get())
        new_vol = max(0, min(150, current + delta))
        self.volume_slider.set(new_vol)
        self._on_volume(new_vol)

    def _toggle_mute(self):
        """Toggle mute"""
        if self.player:
            try:
                self.player.audio_toggle_mute()
            except:
                pass

    def _on_drop(self, event):
        """Handle file drop"""
        try:
            data = event.data
            if data.startswith('{') and data.endswith('}'):
                data = data[1:-1]
            files = self.tk.splitlist(data)
            if files:
                file_path = files[0]
                if file_path.startswith('{') and file_path.endswith('}'):
                    file_path = file_path[1:-1]
                file_path = os.path.normpath(file_path)
                self._log(f"Drop received: {file_path}")
                self.load_file(file_path)
        except Exception as e:
            self._log(f"Drop error: {e}", "error")

    def _open_file(self):
        """Open file dialog"""
        filetypes = [
            ("All supported", "*.mp4 *.avi *.mkv *.mov *.webm *.mp3 *.wav *.flac *.jpg *.jpeg *.png *.gif *.bmp *.webp *.md *.html *.htm *.txt *.json *.xml *.py *.js"),
            ("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv *.webm *.m4v"),
            ("Audio files", "*.mp3 *.wav *.flac *.m4a *.ogg"),
            ("Images", "*.jpg *.jpeg *.png *.gif *.bmp *.webp *.ico *.tiff"),
            ("Documents", "*.md *.markdown *.html *.htm *.txt *.json *.xml"),
            ("Code", "*.py *.js *.ts *.css *.java *.c *.cpp *.cs *.go *.rs"),
            ("All files", "*.*")
        ]
        file_path = filedialog.askopenfilename(
            title="Open File",
            filetypes=filetypes
        )
        if file_path:
            self.load_file(file_path)

    def load_file(self, file_path: str):
        """Load any supported file type"""
        if not os.path.exists(file_path):
            self._log(f"File not found: {file_path}", "error")
            return

        ext = os.path.splitext(file_path)[1].lower()
        self.current_file = file_path
        filename = os.path.basename(file_path)
        self.file_label.configure(text=filename[:50] + "..." if len(filename) > 50 else filename)

        # Hide placeholder and all views first
        self.placeholder.place_forget()
        self._hide_all_views()

        if ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS:
            self._load_video(file_path, filename)
        elif ext in IMAGE_EXTENSIONS:
            self._load_image(file_path, filename)
        elif ext in MARKDOWN_EXTENSIONS:
            self._load_markdown(file_path, filename)
        elif ext in HTML_EXTENSIONS:
            self._load_html(file_path, filename)
        elif ext in TEXT_EXTENSIONS or ext in CODE_EXTENSIONS:
            self._load_text(file_path, filename)
        else:
            self._load_text(file_path, filename)

    def _hide_all_views(self):
        """Hide all content views"""
        self._stop_poll()
        self.video_frame.pack_forget()
        self.image_frame.pack_forget()
        self.text_frame.pack_forget()
        self.image_controls_bar.pack_forget()
        self.video_controls_frame.pack_forget()
        # Close EQ popup if open
        if self._eq_panel:
            try:
                if self._eq_panel.winfo_exists():
                    self._eq_panel.destroy()
            except Exception:
                pass
            self._eq_panel = None
        # Stop VLC if playing
        if self.player and self.current_mode == "video":
            try:
                self.player.stop()
            except:
                pass
        self.current_mode = "none"

    def clear(self):
        """Clear all media and reset to empty state"""
        self._stop_poll()
        self._hide_all_views()
        self.current_file = None
        self.is_playing = False
        self.duration = 0.0
        self.current_image = None
        self.file_label.configure(text="Drop file here or click Open")
        self.progress_slider.set(0)
        self.time_label.configure(text="00:00 / 00:00")
        self._update_play_button()
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._log("Player cleared", "info")

    def _show_video_controls(self, show: bool):
        """Show or hide video controls (swap inside always-visible bar)"""
        if show:
            self.image_controls_bar.pack_forget()
            self.video_controls_frame.pack(side="left", fill="both", expand=True)
        else:
            self.video_controls_frame.pack_forget()

    def _load_video(self, file_path: str, filename: str):
        """Load video/audio file using VLC"""
        self.current_mode = "video"
        self._show_image_controls(False)
        self.controls_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.video_controls_frame.pack(side="left", fill="both", expand=True)
        self.video_frame.pack(fill="both", expand=True)
        self.video_frame.focus_set()

        if not self.player or not self._vlc_instance:
            self._log("VLC player not available", "error")
            return

        ext = os.path.splitext(file_path)[1].lower()
        is_video = ext in VIDEO_EXTENSIONS

        try:
            # Stop any current playback
            self.player.stop()

            # Only embed video output for actual video files
            # For audio, disable video output to prevent DirectX from
            # taking over the Tk window and freezing the UI
            if is_video:
                self.video_frame.update_idletasks()
                hwnd = self.video_frame.winfo_id()
                self.player.set_hwnd(hwnd)
            else:
                self.player.set_hwnd(0)

            # Create media and play
            media = self._vlc_instance.media_new(file_path)
            self.player.set_media(media)

            # Apply EQ if enabled
            if self._eq_enabled and self._eq:
                self.player.set_equalizer(self._eq)

            # Set volume from slider
            vol = int(self.volume_slider.get())

            self.player.play()

            # VLC needs a moment to start before volume can be set
            self.after(300, lambda: self._apply_initial_volume(vol))

            self._start_poll()
            self._log(f"Playing: {filename}", "success")
        except Exception as e:
            self._log(f"Load error: {e}", "error")
            print(f"[QUICKPLAYER] Load error: {e}")

    def _apply_initial_volume(self, vol):
        """Apply volume after VLC has started playing (needs short delay)"""
        if self.player:
            try:
                self.player.audio_set_volume(vol)
            except Exception:
                pass

    def _load_image(self, file_path: str, filename: str):
        """Load and display image"""
        self.current_mode = "image"
        self.controls_frame.pack_forget()
        self._show_image_controls(True)
        self.image_frame.pack(fill="both", expand=True)

        if not HAS_PIL:
            self._log("PIL not available for image viewing", "error")
            return

        try:
            self._original_image = Image.open(file_path)
            self._original_image_path = file_path
            img_width, img_height = self._original_image.size
            self.image_info_label.configure(text=f"{img_width} x {img_height}")
            self._fit_image()
            self._log(f"Viewing: {filename} ({img_width}x{img_height})", "success")
        except Exception as e:
            self._log(f"Image load error: {e}", "error")

    def _show_image_controls(self, show: bool):
        """Show or hide image controls bar at TOP"""
        if show:
            self.image_controls_bar.pack(fill="x", padx=5, pady=(0, 5), after=self._header_frame)
        else:
            self.image_controls_bar.pack_forget()

    def _fit_image(self):
        """Scale image to fit the canvas"""
        if not self._original_image:
            return
        try:
            self.image_canvas.update_idletasks()
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()
            if canvas_width < 100:
                canvas_width = 800
            if canvas_height < 100:
                canvas_height = 600
            img_width, img_height = self._original_image.size
            scale = min(canvas_width / img_width, canvas_height / img_height)
            self._zoom_level = int(scale * 100)
            self.zoom_slider.set(self._zoom_level)
            self.zoom_value_label.configure(text=f"{self._zoom_level}%")
            self._apply_zoom()
            self.fit_btn.configure(fg_color=COLORS["accent"])
            self.actual_btn.configure(fg_color=COLORS["card_bg"])
        except Exception as e:
            self._log(f"Fit image error: {e}", "error")

    def _actual_size_image(self):
        """Display image at 100% (actual size)"""
        if not self._original_image:
            return
        self._zoom_level = 100
        self.zoom_slider.set(100)
        self.zoom_value_label.configure(text="100%")
        self._apply_zoom()
        self.fit_btn.configure(fg_color=COLORS["card_bg"])
        self.actual_btn.configure(fg_color=COLORS["accent"])

    def _on_zoom(self, value):
        """Handle zoom slider change"""
        self._zoom_level = int(value)
        self.zoom_value_label.configure(text=f"{self._zoom_level}%")
        self._apply_zoom()
        self.fit_btn.configure(fg_color=COLORS["card_bg"])
        self.actual_btn.configure(fg_color=COLORS["card_bg"])

    def _apply_zoom(self):
        """Apply current zoom level to image"""
        if not self._original_image:
            return
        try:
            img = self._original_image.copy()
            img_width, img_height = img.size
            new_width = max(10, int(img_width * self._zoom_level / 100))
            new_height = max(10, int(img_height * self._zoom_level / 100))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.current_image = ImageTk.PhotoImage(img)
            self.image_canvas.delete("all")
            self.image_canvas.create_image(0, 0, image=self.current_image, anchor="nw", tags="image")
            self.image_canvas.configure(scrollregion=(0, 0, new_width, new_height))
        except Exception as e:
            self._log(f"Zoom error: {e}", "error")

    def _on_image_mousewheel(self, event):
        self.image_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_image_shift_mousewheel(self, event):
        self.image_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def _load_markdown(self, file_path: str, filename: str):
        """Load and render markdown file"""
        self.current_mode = "text"
        self.text_frame.pack(fill="both", expand=True)
        self._show_video_controls(False)
        self._show_image_controls(False)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.text_widget.delete("1.0", "end")
            if HAS_MARKDOWN:
                self._render_markdown(content)
            else:
                self.text_widget.insert("1.0", content)
            self._log(f"Viewing: {filename}", "success")
        except Exception as e:
            self._log(f"Markdown load error: {e}", "error")

    def _render_markdown(self, content: str):
        """Render markdown with basic formatting"""
        lines = content.split('\n')
        for line in lines:
            if line.startswith('### '):
                self.text_widget.insert("end", line[4:] + '\n', "h3")
            elif line.startswith('## '):
                self.text_widget.insert("end", line[3:] + '\n', "h2")
            elif line.startswith('# '):
                self.text_widget.insert("end", line[2:] + '\n', "h1")
            elif line.startswith('```'):
                self.text_widget.insert("end", line + '\n', "code")
            elif line.startswith('- ') or line.startswith('* '):
                self.text_widget.insert("end", '  • ' + line[2:] + '\n')
            elif len(line) > 2 and line[0].isdigit() and line[1] == '.':
                self.text_widget.insert("end", '  ' + line + '\n')
            else:
                self.text_widget.insert("end", line + '\n')

    def _load_html(self, file_path: str, filename: str):
        """Load HTML file (display as text for now)"""
        self.current_mode = "text"
        self.text_frame.pack(fill="both", expand=True)
        self._show_video_controls(False)
        self._show_image_controls(False)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.text_widget.delete("1.0", "end")
            self.text_widget.insert("1.0", content)
            self._log(f"Viewing: {filename}", "success")
        except Exception as e:
            self._log(f"HTML load error: {e}", "error")

    def _load_text(self, file_path: str, filename: str):
        """Load plain text or code file"""
        self.current_mode = "text"
        self.text_frame.pack(fill="both", expand=True)
        self._show_video_controls(False)
        self._show_image_controls(False)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.text_widget.delete("1.0", "end")
            self.text_widget.insert("1.0", content)
            self._log(f"Viewing: {filename}", "success")
        except Exception as e:
            self._log(f"Text load error: {e}", "error")

    def _toggle_play(self):
        """Toggle play/pause"""
        if not self.player or not self.current_file:
            return
        try:
            if self.player.is_playing():
                self.player.set_pause(1)
            else:
                self.player.set_pause(0)
        except:
            pass

    def _stop(self):
        """Stop playback"""
        self._stop_poll()
        if self.player:
            try:
                self.player.stop()
                self.is_playing = False
                self._update_play_button()
                self.progress_slider.set(0)
                self.time_label.configure(text="00:00 / 00:00")
            except:
                pass

    def _on_seek(self, value):
        """Handle seek slider"""
        if self.player and self.duration > 0:
            try:
                seek_ms = int((value / 100) * self.duration * 1000)
                self.player.set_time(seek_ms)
            except:
                pass

    def _on_volume(self, value):
        """Handle volume slider (0-150 range, VLC accepts 0-200)"""
        vol = int(value)
        if self.player:
            try:
                self.player.audio_set_volume(vol)
            except:
                pass
        try:
            self.vol_pct_label.configure(text=f"{vol}%")
        except:
            pass

    def _update_time(self, current_time: float):
        """Update time display"""
        if self.duration > 0:
            cur_min = int(current_time // 60)
            cur_sec = int(current_time % 60)
            dur_min = int(self.duration // 60)
            dur_sec = int(self.duration % 60)
            self.time_label.configure(text=f"{cur_min:02d}:{cur_sec:02d} / {dur_min:02d}:{dur_sec:02d}")
            progress = (current_time / self.duration) * 100
            self.progress_slider.set(progress)

    def _update_play_button(self):
        """Update play button icon"""
        if self.is_playing:
            self.play_btn.configure(text="⏸")
        else:
            self.play_btn.configure(text="▶")

    # ======================== EQ PANEL (Popup Window) ========================

    def _toggle_eq_panel(self):
        """Toggle the EQ popup window"""
        if self._eq_panel and self._eq_panel.winfo_exists():
            self._eq_panel.destroy()
            self._eq_panel = None
            self.eq_btn.configure(fg_color=COLORS["card_bg"])
        else:
            self._show_eq_panel()
            self.eq_btn.configure(fg_color=COLORS["accent"])

    def _show_eq_panel(self):
        """Show the 10-band EQ as a popup window"""
        if self._eq_panel and self._eq_panel.winfo_exists():
            self._eq_panel.lift()
            self._eq_panel.focus_set()
            return

        # Create popup window
        self._eq_panel = tk.Toplevel(self.winfo_toplevel())
        self._eq_panel.title("QuickPlayer Equalizer")
        self._eq_panel.configure(bg="#001030")
        self._eq_panel.geometry("900x320")
        self._eq_panel.resizable(True, False)
        self._eq_panel.attributes('-topmost', True)
        self._eq_panel.protocol("WM_DELETE_WINDOW", self._close_eq_panel)

        # Position near bottom-center of screen
        self._eq_panel.update_idletasks()
        sw = self._eq_panel.winfo_screenwidth()
        sh = self._eq_panel.winfo_screenheight()
        x = (sw // 2) - 450
        y = sh - 400
        self._eq_panel.geometry(f"900x320+{x}+{y}")

        main = self._eq_panel

        # Top row: Enable toggle + Preset dropdown + Reset + Preamp
        top_row = tk.Frame(main, bg="#001030")
        top_row.pack(fill="x", padx=15, pady=(12, 5))

        # Enable/Disable toggle
        self._eq_enable_var = tk.BooleanVar(value=self._eq_enabled)
        eq_check = tk.Checkbutton(
            top_row, text="EQ Enabled",
            font=("Segoe UI", 14, "bold"),
            fg="#00BFFF", bg="#001030", selectcolor="#001A4D",
            activebackground="#001030", activeforeground="#00BFFF",
            variable=self._eq_enable_var, command=self._on_eq_toggle
        )
        eq_check.pack(side="left", padx=(5, 20))

        # Preset dropdown
        tk.Label(top_row, text="Preset:", font=("Segoe UI", 13, "bold"),
                 fg="white", bg="#001030").pack(side="left", padx=(0, 5))

        # Show current preset name (default: Headphones)
        current_preset = getattr(self, '_eq_default_preset', "Flat")
        self._eq_preset_var = tk.StringVar(value=current_preset)
        import tkinter.ttk as ttk
        style = ttk.Style()
        style.configure("EQ.TCombobox", fieldbackground="#0047AB", background="#0047AB")
        preset_combo = ttk.Combobox(
            top_row, textvariable=self._eq_preset_var,
            values=VLC_EQ_PRESETS, state="readonly", width=18,
            font=("Segoe UI", 12)
        )
        preset_combo.pack(side="left", padx=5)
        preset_combo.bind("<<ComboboxSelected>>",
                          lambda e: self._on_eq_preset(self._eq_preset_var.get()))

        # Reset button
        reset_btn = tk.Button(
            top_row, text="Reset", font=("Segoe UI", 12, "bold"),
            bg="#0047AB", fg="white", activebackground="#CC3333",
            activeforeground="white", bd=0, padx=12, pady=2,
            command=self._reset_eq
        )
        reset_btn.pack(side="left", padx=15)

        # Preamp
        tk.Label(top_row, text="Preamp:", font=("Segoe UI", 12),
                 fg="white", bg="#001030").pack(side="left", padx=(20, 5))

        self._preamp_var = tk.DoubleVar(value=0)
        self._preamp_slider = tk.Scale(
            top_row, from_=-20, to=20, orient="horizontal",
            variable=self._preamp_var, length=140, showvalue=True,
            bg="#001030", fg="white", troughcolor="#333355",
            highlightthickness=0, font=("Segoe UI", 10),
            command=self._on_preamp_change
        )
        self._preamp_slider.pack(side="left", padx=5)

        # Band sliders area
        bands_frame = tk.Frame(main, bg="#001030")
        bands_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self._eq_sliders = []
        self._eq_value_labels = []

        for i in range(10):
            band_frame = tk.Frame(bands_frame, bg="#001030")
            band_frame.pack(side="left", fill="both", expand=True, padx=3)

            # Frequency label at top
            freq_label = tk.Label(
                band_frame, text=EQ_BAND_LABELS[i],
                font=("Segoe UI", 12, "bold"),
                fg="#00BFFF", bg="#001030"
            )
            freq_label.pack(side="top", pady=(2, 0))

            # dB value label
            val_label = tk.Label(
                band_frame, text="0 dB",
                font=("Segoe UI", 10),
                fg="#AAAAFF", bg="#001030", width=6
            )
            val_label.pack(side="top", pady=(0, 2))
            self._eq_value_labels.append(val_label)

            # Vertical scale slider
            slider = tk.Scale(
                band_frame, from_=20, to=-20, orient="vertical",
                length=160, width=18, showvalue=False,
                bg="#001030", fg="white", troughcolor="#333355",
                highlightthickness=0, sliderrelief="flat",
                command=lambda val, idx=i: self._on_eq_band_change(idx, float(val))
            )
            slider.set(0)
            slider.pack(side="top", padx=2, pady=(0, 5))
            self._eq_sliders.append(slider)

        # Sync sliders to current EQ state
        if self._eq:
            preamp = self._eq.get_preamp()
            self._preamp_slider.set(preamp)
            for i in range(10):
                gain = self._eq.get_amp_at_index(i)
                self._eq_sliders[i].set(gain)
                self._eq_value_labels[i].configure(text=f"{gain:.0f} dB")

        print("[QUICKPLAYER] EQ panel opened")

    def _close_eq_panel(self):
        """Close the EQ popup window"""
        if self._eq_panel and self._eq_panel.winfo_exists():
            self._eq_panel.destroy()
            self._eq_panel = None
            self.eq_btn.configure(fg_color=COLORS["card_bg"])

    def _on_eq_toggle(self):
        """Enable/disable EQ"""
        self._eq_enabled = self._eq_enable_var.get()
        if self.player:
            try:
                if self._eq_enabled and self._eq:
                    self.player.set_equalizer(self._eq)
                else:
                    self.player.set_equalizer(None)
            except Exception as e:
                print(f"[QUICKPLAYER] EQ toggle error: {e}")

    def _on_eq_preset(self, preset_name: str):
        """Load an EQ preset"""
        try:
            self._eq_default_preset = preset_name
            idx = VLC_EQ_PRESETS.index(preset_name)
            self._eq = vlc.libvlc_audio_equalizer_new_from_preset(idx)

            # Update sliders to match preset values
            preamp = self._eq.get_preamp()
            self._preamp_slider.set(preamp)

            for i in range(10):
                gain = self._eq.get_amp_at_index(i)
                self._eq_sliders[i].set(gain)
                self._eq_value_labels[i].configure(text=f"{gain:.0f} dB")

            # Apply if enabled
            if self._eq_enabled and self.player:
                self.player.set_equalizer(self._eq)

            # Auto-enable when selecting a non-Flat preset
            if preset_name != "Flat" and not self._eq_enabled:
                self._eq_enabled = True
                self._eq_enable_var.set(True)
                if self.player:
                    self.player.set_equalizer(self._eq)

        except Exception as e:
            print(f"[QUICKPLAYER] EQ preset error: {e}")

    def _on_eq_band_change(self, band_idx: int, value: float):
        """Handle individual EQ band slider change"""
        gain = float(value)
        if self._eq:
            self._eq.set_amp_at_index(gain, band_idx)
            self._eq_value_labels[band_idx].configure(text=f"{gain:.0f} dB")
            if self._eq_enabled and self.player:
                self.player.set_equalizer(self._eq)

    def _on_preamp_change(self, value):
        """Handle preamp slider change"""
        preamp = float(value)
        if self._eq:
            self._eq.set_preamp(preamp)
            if self._eq_enabled and self.player:
                self.player.set_equalizer(self._eq)

    def _reset_eq(self):
        """Reset EQ to flat"""
        self._eq = vlc.AudioEqualizer()  # Fresh flat EQ
        self._preamp_slider.set(0)
        for i in range(10):
            self._eq_sliders[i].set(0)
            self._eq_value_labels[i].configure(text="0 dB")
        self._eq_preset_var.set("Flat")
        if self._eq_enabled and self.player:
            self.player.set_equalizer(self._eq)

    # ======================== POP OUT ========================

    def _pop_out(self):
        """Pop out current video into fullscreen window"""
        if not self.current_file:
            self._log("No file loaded to pop out", "error")
            return

        ext = os.path.splitext(self.current_file)[1].lower()
        if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
            self._log("Pop out only works for video/audio files", "error")
            return

        # Get current playback position (ms)
        position = 0.0
        if self.player:
            try:
                pos_ms = self.player.get_time()
                if pos_ms is not None and pos_ms >= 0:
                    position = pos_ms / 1000.0
            except:
                pass

        # Pause embedded player
        if self.player and self.is_playing:
            try:
                self.player.set_pause(1)
            except:
                pass

        file_path = self.current_file

        # Pass current EQ state to pop-out
        eq_preset_idx = None
        eq_band_gains = None
        eq_preamp = 0.0
        if self._eq_enabled and self._eq:
            eq_preamp = self._eq.get_preamp()
            eq_band_gains = [self._eq.get_amp_at_index(i) for i in range(10)]
            try:
                eq_preset_idx = VLC_EQ_PRESETS.index(self._eq_preset_var.get()) if self._eq_preset_var else None
            except (ValueError, AttributeError):
                eq_preset_idx = None

        def on_popout_close(resume_pos):
            """Called when pop-out closes - resume in embedded player"""
            if self.player and self.current_file == file_path:
                try:
                    self.player.set_time(int(resume_pos * 1000))
                    self.player.set_pause(0)
                except:
                    pass

        QuickPlayerPopOut(
            self.winfo_toplevel(), file_path, position, on_popout_close,
            eq_enabled=self._eq_enabled, eq_preset_idx=eq_preset_idx,
            eq_band_gains=eq_band_gains, eq_preamp=eq_preamp
        )

    def destroy(self):
        """Clean up VLC player, EQ popup, and instance"""
        self._stop_poll()
        # Close EQ popup if open
        if self._eq_panel:
            try:
                if self._eq_panel.winfo_exists():
                    self._eq_panel.destroy()
            except Exception:
                pass
            self._eq_panel = None
        if self.player:
            try:
                self.player.stop()
                self.player.release()
            except:
                pass
        if self._vlc_instance:
            try:
                self._vlc_instance.release()
            except:
                pass
        super().destroy()


class QuickPlayerPopOut(tk.Toplevel):
    """Fullscreen pop-out video player window using VLC"""

    def __init__(self, parent, file_path: str, start_position: float = 0.0,
                 on_close_callback=None, standalone: bool = False,
                 eq_enabled: bool = False, eq_preset_idx: Optional[int] = None,
                 eq_band_gains: Optional[list] = None, eq_preamp: float = 0.0):
        super().__init__(parent)

        self.file_path = file_path
        self.start_position = start_position
        self.on_close_callback = on_close_callback
        self.standalone = standalone
        self._vlc_instance: Optional[vlc.Instance] = None
        self.player: Optional[vlc.MediaPlayer] = None
        self._eq: Optional[vlc.AudioEqualizer] = None
        self.is_playing = False
        self.duration = 0.0
        self._controls_visible = True
        self._hide_timer = None
        self._is_fullscreen = True
        self._closing = False
        self._poll_timer_id = None

        # EQ state from parent
        self._eq_enabled = eq_enabled
        self._eq_preset_idx = eq_preset_idx
        self._eq_band_gains = eq_band_gains
        self._eq_preamp = eq_preamp

        # Window setup
        self.title(f"QuickPlayer - {os.path.basename(file_path)}")
        self.configure(bg='black')
        self.attributes('-fullscreen', True)
        self.focus_set()

        self._build_ui()
        self._bind_keys()
        self._init_player()

        # Don't hide controls immediately - let the cursor poll handle it
        self._reset_hide_timer()

    def _build_ui(self):
        """Build the pop-out player UI"""
        # Use a container so video_frame and controls don't fight for space
        self.main_container = tk.Frame(self, bg='black')
        self.main_container.pack(fill="both", expand=True)

        self.video_frame = tk.Frame(self.main_container, bg='black')
        self.video_frame.pack(fill="both", expand=True)

        # Controls overlay at bottom of the main window (not inside video_frame)
        self.controls_frame = tk.Frame(self, bg='#1a1a2e', height=70)
        self.controls_frame.pack(side="bottom", fill="x")
        self.controls_frame.pack_propagate(False)

        self.play_btn = tk.Button(
            self.controls_frame, text="⏸", font=("Segoe UI", 22),
            bg='#0047AB', fg='white', activebackground='#0066FF',
            activeforeground='white', bd=0, width=4,
            command=self._toggle_play
        )
        self.play_btn.pack(side="left", padx=10, pady=8)

        self.stop_btn = tk.Button(
            self.controls_frame, text="⏹", font=("Segoe UI", 22),
            bg='#333355', fg='white', activebackground='#555577',
            activeforeground='white', bd=0, width=4,
            command=self._stop
        )
        self.stop_btn.pack(side="left", padx=5, pady=8)

        self.skip_back_btn = tk.Button(
            self.controls_frame, text="⏪", font=("Segoe UI", 20),
            bg='#333355', fg='white', activebackground='#555577',
            activeforeground='white', bd=0, width=4,
            command=lambda: self._seek_relative(-15)
        )
        self.skip_back_btn.pack(side="left", padx=3, pady=8)

        self.skip_fwd_btn = tk.Button(
            self.controls_frame, text="⏩", font=("Segoe UI", 20),
            bg='#333355', fg='white', activebackground='#555577',
            activeforeground='white', bd=0, width=4,
            command=lambda: self._seek_relative(30)
        )
        self.skip_fwd_btn.pack(side="left", padx=(3, 10), pady=8)

        self.time_label = tk.Label(
            self.controls_frame, text="00:00 / 00:00",
            font=("Segoe UI", 16, "bold"), bg='#1a1a2e', fg='white'
        )
        self.time_label.pack(side="left", padx=15)

        self.seek_var = tk.DoubleVar(value=0)
        self.seek_slider = tk.Scale(
            self.controls_frame, from_=0, to=1000, orient="horizontal",
            variable=self.seek_var, showvalue=False,
            bg='#1a1a2e', fg='white', troughcolor='#333355',
            highlightthickness=0, sliderrelief="flat",
            command=self._on_seek
        )
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10, pady=12)

        vol_label = tk.Label(
            self.controls_frame, text="🔊", font=("Segoe UI", 18),
            bg='#1a1a2e', fg='white'
        )
        vol_label.pack(side="left", padx=(10, 2))

        self.vol_var = tk.IntVar(value=100)
        self.vol_slider = tk.Scale(
            self.controls_frame, from_=0, to=150, orient="horizontal",
            variable=self.vol_var, showvalue=True, length=120,
            bg='#1a1a2e', fg='white', troughcolor='#333355',
            highlightthickness=0, sliderrelief="flat",
            command=self._on_volume
        )
        self.vol_slider.pack(side="left", padx=(0, 10), pady=12)

        close_text = "✕ Close" if self.standalone else "↩ Back to CCL"
        self.close_btn = tk.Button(
            self.controls_frame, text=close_text, font=("Segoe UI", 14, "bold"),
            bg='#8B0000', fg='white', activebackground='#CC0000',
            activeforeground='white', bd=0, padx=15,
            command=self._close_popout
        )
        self.close_btn.pack(side="right", padx=10, pady=8)

        # NOTE: We do NOT rely on Tk <Motion> events for showing controls
        # because VLC's DirectX surface captures all mouse events from the
        # video_frame HWND, preventing Tk from receiving them.
        # Instead we poll the Windows cursor position via ctypes (see _start_cursor_poll).
        self.controls_frame.bind('<Motion>', self._on_mouse_move)
        self.bind('<MouseWheel>', self._on_mousewheel_volume)
        self.video_frame.bind('<Double-Button-1>', lambda e: self._toggle_fullscreen())

        # Track last known cursor position for polling
        self._last_cursor_x = 0
        self._last_cursor_y = 0
        self._cursor_poll_id = None

    def _bind_keys(self):
        """Bind keyboard shortcuts"""
        self.bind('<space>', lambda e: self._toggle_play())
        self.bind('<Escape>', lambda e: self._close_popout())
        self.bind('<f>', lambda e: self._toggle_fullscreen())
        self.bind('<F>', lambda e: self._toggle_fullscreen())
        self.bind('<F11>', lambda e: self._toggle_fullscreen())
        self.bind('<Left>', lambda e: self._seek_relative(-15))
        self.bind('<Right>', lambda e: self._seek_relative(30))
        self.bind('<Shift-Left>', lambda e: self._seek_relative(-30))
        self.bind('<Shift-Right>', lambda e: self._seek_relative(30))
        self.bind('<Up>', lambda e: self._adjust_volume(5))
        self.bind('<Down>', lambda e: self._adjust_volume(-5))
        self.bind('<m>', lambda e: self._toggle_mute())
        self.bind('<M>', lambda e: self._toggle_mute())
        # Any key press shows controls (so user can always get them back)
        self.bind('<Key>', self._on_any_key)

    def _on_any_key(self, event):
        """Show controls on any key press"""
        # Don't interfere with specific bindings - just make controls visible
        self._show_controls()

    def _toggle_mute(self):
        if self.player:
            try:
                self.player.audio_toggle_mute()
            except:
                pass

    def _init_player(self):
        """Initialize VLC player in the pop-out window"""
        if not HAS_VLC:
            return

        ext = os.path.splitext(self.file_path)[1].lower()
        is_video = ext in VIDEO_EXTENSIONS

        try:
            self._vlc_instance = vlc.Instance(
                '--no-xlib',
                '--quiet',
                '--no-video-title-show',
            )
            self.player = self._vlc_instance.media_player_new()

            # Only embed video output for actual video files
            if is_video:
                self.video_frame.update_idletasks()
                hwnd = self.video_frame.winfo_id()
                self.player.set_hwnd(hwnd)
            else:
                self.player.set_hwnd(0)

            # Apply EQ from parent if enabled
            if self._eq_enabled:
                if self._eq_band_gains:
                    self._eq = vlc.AudioEqualizer()
                    self._eq.set_preamp(self._eq_preamp)
                    for i, gain in enumerate(self._eq_band_gains):
                        self._eq.set_amp_at_index(gain, i)
                elif self._eq_preset_idx is not None:
                    self._eq = vlc.libvlc_audio_equalizer_new_from_preset(self._eq_preset_idx)
                if self._eq:
                    self.player.set_equalizer(self._eq)

            # Load and play
            media = self._vlc_instance.media_new(self.file_path)
            self.player.set_media(media)
            self.player.play()

            # Set volume after a short delay (VLC needs time to initialize audio)
            self.after(300, lambda: self.player.audio_set_volume(self.vol_var.get()) if self.player else None)

            self._start_poll()
            self._start_cursor_poll()

            # Seek to start position after a short delay
            if self.start_position > 0:
                def do_seek():
                    try:
                        if self.player and self.start_position > 0:
                            self.player.set_time(int(self.start_position * 1000))
                            self.start_position = 0
                    except:
                        pass
                self.after(500, do_seek)

            self.is_playing = True
            print(f"[POPOUT] Playing: {self.file_path}")

        except Exception as e:
            print(f"[POPOUT] Failed to init VLC: {e}")
            self.player = None

    def _start_poll(self):
        """Start polling VLC state every 1000ms"""
        self._stop_poll()

        def poll():
            if not self.player or self._closing:
                return
            try:
                dur_ms = self.player.get_length()
                if dur_ms and dur_ms > 0:
                    self.duration = dur_ms / 1000.0

                pos_ms = self.player.get_time()
                if pos_ms is not None and pos_ms >= 0:
                    self._update_time(pos_ms / 1000.0)

                new_playing = self.player.is_playing() == 1
                if new_playing != self.is_playing:
                    self.is_playing = new_playing
                    self._update_play_button()
            except Exception as e:
                print(f"[POPOUT] Poll error: {e}")

            try:
                self._poll_timer_id = self.after(1000, poll)
            except Exception:
                pass

        self._poll_timer_id = self.after(1000, poll)

    def _stop_poll(self):
        if hasattr(self, '_poll_timer_id') and self._poll_timer_id is not None:
            try:
                self.after_cancel(self._poll_timer_id)
            except Exception:
                pass
            self._poll_timer_id = None

    def _update_time(self, current_time: float):
        if self._closing:
            return
        if self.duration > 0:
            cur_min = int(current_time // 60)
            cur_sec = int(current_time % 60)
            dur_min = int(self.duration // 60)
            dur_sec = int(self.duration % 60)
            self.time_label.configure(text=f"{cur_min:02d}:{cur_sec:02d} / {dur_min:02d}:{dur_sec:02d}")
            progress = (current_time / self.duration) * 1000
            self.seek_var.set(progress)

    def _update_play_button(self):
        if self._closing:
            return
        self.play_btn.configure(text="⏸" if self.is_playing else "▶")

    def _toggle_play(self):
        if self.player:
            try:
                if self.player.is_playing():
                    self.player.set_pause(1)
                else:
                    self.player.set_pause(0)
            except:
                pass

    def _stop(self):
        if self.player:
            try:
                self.player.stop()
                self.is_playing = False
                self._update_play_button()
                self.seek_var.set(0)
                self.time_label.configure(text="00:00 / 00:00")
            except:
                pass

    def _on_seek(self, value):
        if self.player and self.duration > 0:
            try:
                seek_ms = int((float(value) / 1000) * self.duration * 1000)
                self.player.set_time(seek_ms)
            except:
                pass

    def _seek_relative(self, seconds: int):
        if self.player:
            try:
                cur = self.player.get_time()
                if cur is not None and cur >= 0:
                    self.player.set_time(cur + int(seconds * 1000))
            except:
                pass

    def _on_volume(self, value):
        if self.player:
            try:
                self.player.audio_set_volume(int(value))
            except:
                pass

    def _adjust_volume(self, delta: int):
        current = self.vol_var.get()
        new_vol = max(0, min(150, current + delta))
        self.vol_var.set(new_vol)
        if self.player:
            try:
                self.player.audio_set_volume(new_vol)
            except:
                pass

    def _on_mousewheel_volume(self, event):
        delta = 5 if event.delta > 0 else -5
        self._adjust_volume(delta)

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        self.attributes('-fullscreen', self._is_fullscreen)

    def _start_cursor_poll(self):
        """Poll Windows cursor position every 200ms to detect mouse movement.
        VLC's DirectX surface steals mouse events from Tk, so we can't use
        Tk's <Motion> binding on the video_frame. Instead we use ctypes
        GetCursorPos to detect movement regardless of what has mouse capture."""
        self._stop_cursor_poll()

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        def poll_cursor():
            if self._closing:
                return
            try:
                pt = POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                cx, cy = pt.x, pt.y
                if cx != self._last_cursor_x or cy != self._last_cursor_y:
                    self._last_cursor_x = cx
                    self._last_cursor_y = cy
                    self._show_controls()
            except Exception:
                pass
            try:
                self._cursor_poll_id = self.after(200, poll_cursor)
            except Exception:
                pass

        self._cursor_poll_id = self.after(200, poll_cursor)

    def _stop_cursor_poll(self):
        if hasattr(self, '_cursor_poll_id') and self._cursor_poll_id is not None:
            try:
                self.after_cancel(self._cursor_poll_id)
            except Exception:
                pass
            self._cursor_poll_id = None

    def _show_controls(self):
        """Show controls and reset the auto-hide timer"""
        if not self._controls_visible and not self._closing:
            self.controls_frame.pack(side="bottom", fill="x")
            self._controls_visible = True
            self.configure(cursor='')
        self._reset_hide_timer()

    def _on_mouse_move(self, event=None):
        """Handle mouse motion on controls_frame (Tk events still work there)"""
        self._show_controls()

    def _reset_hide_timer(self):
        if self._hide_timer:
            try:
                self.after_cancel(self._hide_timer)
            except Exception:
                pass
        self._hide_timer = self.after(3000, self._hide_controls)

    def _hide_controls(self):
        if self.is_playing and not self._closing:
            self.controls_frame.pack_forget()
            self._controls_visible = False
            self.configure(cursor='none')

    def _close_popout(self):
        """Close the pop-out window and return to embedded mode"""
        self._closing = True
        self._stop_poll()
        self._stop_cursor_poll()

        resume_pos = 0.0
        if self.player:
            try:
                pos_ms = self.player.get_time()
                if pos_ms is not None and pos_ms >= 0:
                    resume_pos = pos_ms / 1000.0
            except:
                pass

        if self.player:
            try:
                self.player.stop()
                _time.sleep(0.1)
                self.player.release()
            except:
                pass
            self.player = None

        if self._vlc_instance:
            try:
                self._vlc_instance.release()
            except:
                pass
            self._vlc_instance = None

        if self._hide_timer:
            self.after_cancel(self._hide_timer)

        if self.on_close_callback:
            try:
                self.on_close_callback(resume_pos)
            except:
                pass

        self.destroy()

        if self.standalone:
            try:
                self.master.quit()
            except:
                pass
