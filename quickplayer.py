"""
QuickPlayer - Multi-format Viewer Widget for Command Center LaunchPad
Supports video, audio, images, markdown, HTML, and text files
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

# Add mpv.net path to find libmpv-2.dll
MPV_PATH = r"C:\Users\edb616321\AppData\Local\Programs\mpv.net"
if MPV_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = MPV_PATH + os.pathsep + os.environ["PATH"]

try:
    import mpv
    HAS_MPV = True
except Exception as e:
    HAS_MPV = False
    print(f"[QUICKPLAYER] MPV not available: {e}")

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


class QuickPlayerWidget(ctk.CTkFrame):
    """Multi-format viewer widget with drag-and-drop support"""

    def __init__(self, parent, log_callback: Optional[Callable[[str, str], None]] = None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self.log_callback = log_callback
        self.player: Optional[mpv.MPV] = None
        self.current_file: Optional[str] = None
        self.is_playing = False
        self.duration = 0.0
        self.current_mode = "none"  # none, video, image, text
        self.current_image = None  # Keep reference to prevent garbage collection
        self._header_frame = None  # Store reference to header for packing order

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
        header = self._header_frame  # Local alias for existing code

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

        # VIDEO VIEW - Video frame for MPV
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

        self.vol_label = ctk.CTkLabel(
            self.video_controls_frame,
            text="🔊",
            font=ctk.CTkFont(size=28)
        )
        self.vol_label.pack(side="left", padx=(15, 5))

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

        # EQ toggle button
        self.eq_btn = ctk.CTkButton(
            self.video_controls_frame,
            text="EQ",
            width=70,
            height=60,
            font=ctk.CTkFont(size=22, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self._toggle_eq
        )
        self.eq_btn.pack(side="left", padx=(0, 10), pady=10)

        # === 10-BAND EQUALIZER PANEL (hidden by default) ===
        self._eq_visible = False
        self._eq_values = [0.0] * 10  # -20 to +20 dB per band
        self._eq_sliders = []

        self.eq_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], height=180)
        # Don't pack yet - toggled by EQ button

        eq_bands = ["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"]

        # Top row: label + preset buttons
        eq_top = ctk.CTkFrame(self.eq_frame, fg_color="transparent")
        eq_top.pack(fill="x", padx=10, pady=(5, 0))

        ctk.CTkLabel(
            eq_top, text="EQUALIZER",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(side="left", padx=5)

        # Preset buttons
        for preset_name, preset_vals in [
            ("Flat", [0]*10),
            ("Warm", [6, 4, 2, 0, -2, 0, -2, -4, -2, 0]),
            ("Bass+", [12, 10, 7, 3, 0, 0, 0, 0, 0, 0]),
            ("Treble+", [0, 0, 0, 0, 0, 3, 7, 10, 12, 12]),
            ("Vocal", [-4, -2, 0, 4, 8, 8, 4, 0, -2, -4]),
        ]:
            ctk.CTkButton(
                eq_top, text=preset_name,
                width=80, height=30,
                font=ctk.CTkFont(size=14),
                fg_color=COLORS["bg_dark"],
                hover_color=COLORS["card_hover"],
                command=lambda v=preset_vals: self._apply_eq_preset(v)
            ).pack(side="left", padx=3)

        # Sliders row
        eq_sliders_frame = ctk.CTkFrame(self.eq_frame, fg_color="transparent")
        eq_sliders_frame.pack(fill="both", expand=True, padx=5, pady=5)

        for i, band_label in enumerate(eq_bands):
            col_frame = ctk.CTkFrame(eq_sliders_frame, fg_color="transparent")
            col_frame.pack(side="left", fill="both", expand=True, padx=2)

            # dB value label at top
            db_label = ctk.CTkLabel(
                col_frame, text="0",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text"], width=35
            )
            db_label.pack(pady=(0, 2))

            slider = ctk.CTkSlider(
                col_frame,
                from_=20, to=-20,
                orientation="vertical",
                height=90, width=20,
                button_color=COLORS["accent"],
                button_hover_color=COLORS["accent_hover"],
                progress_color=COLORS["accent"],
                command=lambda val, idx=i, lbl=db_label: self._on_eq_change(idx, val, lbl)
            )
            slider.pack(fill="y", expand=True)
            slider.set(0)
            self._eq_sliders.append(slider)

            # Band label at bottom
            ctk.CTkLabel(
                col_frame, text=band_label,
                font=ctk.CTkFont(size=11),
                text_color="#88BBDD"
            ).pack(pady=(2, 0))

        # Store original image for rescaling
        self._original_image = None
        self._original_image_path = None

        # NOW pack the content container - it expands into remaining space above controls
        self.content_container.pack(fill="both", expand=True, padx=10, pady=5)

    def _setup_player(self):
        """Initialize TWO MPV players: one for audio (clean, no GPU) and one for video"""
        if not HAS_MPV:
            print("[QUICKPLAYER] MPV not available, video playback disabled")
            return

        self._poll_timer_id = None
        self.player = None           # Active player reference (points to audio or video player)
        self._audio_player = None    # Audio-only: vo=null, zero Tk interaction
        self._video_player = None    # Video: embedded in Tk frame with GPU rendering

        # Shared audio settings - high-quality WASAPI pipeline
        shared_opts = dict(
            ao='wasapi',
            audio_buffer=1.0,
            audio_stream_silence='yes',
            volume_max=150,
            gapless_audio='weak',
            demuxer_max_bytes=50*1024*1024,
            demuxer_readahead_secs=30,
            keep_open=True,
            idle=True,
            osd_level=0,
            input_default_bindings=False,
            input_vo_keyboard=False,
        )

        # AUDIO PLAYER - completely isolated from Tk/GPU.
        # High-quality settings safe here because vo=null means zero GIL contention.
        try:
            self._audio_player = mpv.MPV(
                vo='null',               # No video output at all
                audio_samplerate=48000,   # Native WASAPI rate - avoids resampler artifacts
                audio_format='float',     # 32-bit float - maximum internal precision
                audio_channels='stereo',  # Force stereo for headphone playback
                replaygain='album',       # Album-level normalization for consistent volume
                **shared_opts,
            )
            print("[QUICKPLAYER] Audio player initialized (vo=null, 48kHz/float, headphone-tuned)")
        except Exception as e:
            print(f"[QUICKPLAYER] Failed to init audio player: {e}")

        # VIDEO PLAYER - embedded in Tk frame for video files
        try:
            self.video_frame.update_idletasks()
            wid = self.video_frame.winfo_id()
            self._video_player = mpv.MPV(
                wid=str(int(wid)),
                hwdec='auto-safe',
                vo='gpu',
                video_sync='audio',       # Audio is master clock
                audio_samplerate=48000,
                audio_format='float',
                audio_channels='stereo',
                **shared_opts,
            )
            print("[QUICKPLAYER] Video player initialized (vo=gpu, embedded, 48kHz/float)")
        except Exception as e:
            print(f"[QUICKPLAYER] Failed to init video player: {e}")

        # Default to audio player
        self.player = self._audio_player or self._video_player

    def _start_poll(self):
        """Start polling MPV state every 500ms (2 updates/sec - minimal GIL impact)"""
        self._stop_poll()  # Cancel any existing timer

        def poll():
            if not self.player:
                return
            try:
                # Single batch read - minimize GIL hold time
                pos = self.player.time_pos
                dur = self.player.duration
                paused = self.player.pause

                if dur is not None:
                    self.duration = dur
                if pos is not None:
                    self._update_time(pos)
                if paused is not None:
                    new_playing = not paused
                    if new_playing != self.is_playing:
                        self.is_playing = new_playing
                        self._update_play_button()
            except Exception:
                pass  # Player might be stopped/terminated

            self._poll_timer_id = self.after(1000, poll)

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
        # Register drop target on content container
        try:
            self.content_container.drop_target_register('DND_Files')
            self.content_container.dnd_bind('<<Drop>>', self._on_drop)
        except:
            pass  # TkDND not available

        # Also bind to the whole widget for fallback click-to-open
        self.content_container.bind('<Button-1>', lambda e: self._open_file())
        self.placeholder.bind('<Button-1>', lambda e: self._open_file())

    def _setup_keybindings(self):
        """Setup keyboard shortcuts for media playback (bound to top-level window)"""
        # Bind to the top-level window so keys work regardless of focus
        # We use a short delay so the top-level window exists when we bind
        def bind_to_toplevel():
            try:
                top = self.winfo_toplevel()

                # Play/Pause (only when player has a file loaded)
                top.bind('<space>', lambda e: self._kb_play_pause(e))

                # Seek: Left/Right = 5s, Shift = 30s
                top.bind('<Left>', lambda e: self._kb_seek(e, -15))
                top.bind('<Right>', lambda e: self._kb_seek(e, 30))
                top.bind('<Shift-Left>', lambda e: self._kb_seek(e, -30))
                top.bind('<Shift-Right>', lambda e: self._kb_seek(e, 30))

                # Volume: Up/Down = +/- 5
                top.bind('<Up>', lambda e: self._kb_volume(e, 5))
                top.bind('<Down>', lambda e: self._kb_volume(e, -5))

                # Mute toggle
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
                return "break"  # Consume the event

        # Bind to all child widgets in the player
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
        """Keyboard play/pause - only acts when player is active"""
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._toggle_play()

    def _kb_seek(self, event, seconds):
        """Keyboard seek - only acts when player is active"""
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._seek_by(seconds)

    def _kb_volume(self, event, delta):
        """Keyboard volume - only acts when player is active"""
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._adjust_volume(delta)

    def _kb_mute(self, event):
        """Keyboard mute - only acts when player is active"""
        if self._is_typing(event):
            return
        if self.current_mode == "video" and self.current_file:
            self._toggle_mute()

    def _seek_by(self, seconds: int):
        """Seek forward or backward by seconds"""
        if self.player and self.current_mode == "video":
            try:
                self.player.seek(seconds, 'relative')
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
                self.player.mute = not self.player.mute
            except:
                pass

    def _on_drop(self, event):
        """Handle file drop"""
        try:
            # Get dropped data
            data = event.data

            # Handle Windows file paths with curly braces
            if data.startswith('{') and data.endswith('}'):
                data = data[1:-1]

            # Split list of files
            files = self.tk.splitlist(data)

            if files:
                file_path = files[0]
                # Clean up path - remove curly braces if present
                if file_path.startswith('{') and file_path.endswith('}'):
                    file_path = file_path[1:-1]
                # Normalize path
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

        # Determine file type and load appropriately
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
            # Try to load as text
            self._load_text(file_path, filename)

    def _hide_all_views(self):
        """Hide all content views"""
        self._stop_poll()
        self.video_frame.pack_forget()
        self.image_frame.pack_forget()
        self.text_frame.pack_forget()
        # Hide image controls bar (top)
        self.image_controls_bar.pack_forget()
        # Hide video controls (bottom)
        self.video_controls_frame.pack_forget()
        # Stop video if playing
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
        """Load video/audio file - picks clean audio player or GPU video player"""
        self.current_mode = "video"
        # Show bottom controls bar for video, hide top image bar
        self._show_image_controls(False)
        self.controls_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.video_controls_frame.pack(side="left", fill="both", expand=True)
        self.video_frame.pack(fill="both", expand=True)
        self.video_frame.focus_set()

        # Pick the right player: audio files get the clean vo=null player
        ext = os.path.splitext(file_path)[1].lower()
        if ext in AUDIO_EXTENSIONS and self._audio_player:
            # Stop video player if it was active
            if self.player is self._video_player:
                try:
                    self._video_player.stop()
                except Exception:
                    pass
            self.player = self._audio_player
        elif self._video_player:
            # Stop audio player if it was active
            if self.player is self._audio_player:
                try:
                    self._audio_player.stop()
                except Exception:
                    pass
            self.player = self._video_player

        if self.player:
            try:
                self.player.loadfile(file_path)
                self._start_poll()
                # Re-apply EQ after file starts decoding
                if hasattr(self, '_eq_values') and any(v != 0 for v in self._eq_values):
                    self.after(300, self._apply_eq)
                self._log(f"Playing: {filename}", "success")
            except Exception as e:
                self._log(f"Load error: {e}", "error")
        else:
            self._log("Video player not available", "error")

    def _load_image(self, file_path: str, filename: str):
        """Load and display image"""
        self.current_mode = "image"
        # Hide video controls bar (bottom), show image controls bar (top)
        self.controls_frame.pack_forget()  # Hide entire bottom bar for images
        self._show_image_controls(True)
        self.image_frame.pack(fill="both", expand=True)

        if not HAS_PIL:
            self._log("PIL not available for image viewing", "error")
            return

        try:
            # Load and store original image for rescaling
            self._original_image = Image.open(file_path)
            self._original_image_path = file_path
            img_width, img_height = self._original_image.size

            # Update info label
            self.image_info_label.configure(text=f"{img_width} x {img_height}")

            # Default to fit-to-window
            self._fit_image()

            self._log(f"Viewing: {filename} ({img_width}x{img_height})", "success")

        except Exception as e:
            self._log(f"Image load error: {e}", "error")

    def _show_image_controls(self, show: bool):
        """Show or hide image controls bar at TOP"""
        if show:
            # Pack image controls bar right after header (at top, before content)
            self.image_controls_bar.pack(fill="x", padx=5, pady=(0, 5), after=self._header_frame)
        else:
            self.image_controls_bar.pack_forget()

    def _fit_image(self):
        """Scale image to fit the canvas"""
        if not self._original_image:
            return

        try:
            # Get canvas size
            self.image_canvas.update_idletasks()
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()

            if canvas_width < 100:
                canvas_width = 800
            if canvas_height < 100:
                canvas_height = 600

            # Calculate zoom to fit
            img_width, img_height = self._original_image.size
            scale = min(canvas_width / img_width, canvas_height / img_height)
            self._zoom_level = int(scale * 100)

            # Update slider without triggering callback
            self.zoom_slider.set(self._zoom_level)
            self.zoom_value_label.configure(text=f"{self._zoom_level}%")

            # Apply zoom
            self._apply_zoom()

            # Update button states
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

        # Update button states
        self.fit_btn.configure(fg_color=COLORS["card_bg"])
        self.actual_btn.configure(fg_color=COLORS["accent"])

    def _on_zoom(self, value):
        """Handle zoom slider change"""
        self._zoom_level = int(value)
        self.zoom_value_label.configure(text=f"{self._zoom_level}%")
        self._apply_zoom()

        # Clear button highlights when using slider
        self.fit_btn.configure(fg_color=COLORS["card_bg"])
        self.actual_btn.configure(fg_color=COLORS["card_bg"])

    def _apply_zoom(self):
        """Apply current zoom level to image"""
        if not self._original_image:
            return

        try:
            img = self._original_image.copy()
            img_width, img_height = img.size

            # Calculate new size based on zoom
            new_width = int(img_width * self._zoom_level / 100)
            new_height = int(img_height * self._zoom_level / 100)

            # Minimum size
            new_width = max(10, new_width)
            new_height = max(10, new_height)

            # Resize image
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to PhotoImage
            self.current_image = ImageTk.PhotoImage(img)

            # Clear canvas and display image
            self.image_canvas.delete("all")
            self.image_canvas.create_image(0, 0, image=self.current_image, anchor="nw", tags="image")

            # Update scroll region to match image size
            self.image_canvas.configure(scrollregion=(0, 0, new_width, new_height))

        except Exception as e:
            self._log(f"Zoom error: {e}", "error")

    def _on_image_mousewheel(self, event):
        """Vertical scroll with mousewheel"""
        self.image_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_image_shift_mousewheel(self, event):
        """Horizontal scroll with shift+mousewheel"""
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

            # Clear text widget
            self.text_widget.delete("1.0", "end")

            if HAS_MARKDOWN:
                # Convert markdown to HTML-like formatted text (basic rendering)
                # For now, just display with some basic formatting
                self._render_markdown(content)
            else:
                # Display raw markdown
                self.text_widget.insert("1.0", content)

            self._log(f"Viewing: {filename}", "success")

        except Exception as e:
            self._log(f"Markdown load error: {e}", "error")

    def _render_markdown(self, content: str):
        """Render markdown with basic formatting"""
        lines = content.split('\n')
        for line in lines:
            # Headers
            if line.startswith('### '):
                self.text_widget.insert("end", line[4:] + '\n', "h3")
            elif line.startswith('## '):
                self.text_widget.insert("end", line[3:] + '\n', "h2")
            elif line.startswith('# '):
                self.text_widget.insert("end", line[2:] + '\n', "h1")
            # Code blocks
            elif line.startswith('```'):
                self.text_widget.insert("end", line + '\n', "code")
            # List items
            elif line.startswith('- ') or line.startswith('* '):
                self.text_widget.insert("end", '  • ' + line[2:] + '\n')
            # Numbered lists
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
            self.player.pause = not self.player.pause
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
                seek_time = (value / 100) * self.duration
                self.player.seek(seek_time, 'absolute')
            except:
                pass

    def _on_volume(self, value):
        """Handle volume slider (0-150 range)"""
        vol = int(value)
        if self.player:
            try:
                self.player.volume = vol
            except:
                pass
        try:
            self.vol_pct_label.configure(text=f"{vol}%")
        except:
            pass

    def _toggle_eq(self):
        """Toggle equalizer panel visibility"""
        if self._eq_visible:
            self.eq_frame.pack_forget()
            self._eq_visible = False
            self.eq_btn.configure(fg_color=COLORS["card_bg"])
        else:
            # Pack EQ between content and controls bar
            self.eq_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 5), before=self.controls_frame)
            self._eq_visible = True
            self.eq_btn.configure(fg_color=COLORS["accent"])

    def _on_eq_change(self, band_idx: int, value: float, db_label):
        """Handle individual EQ band change"""
        value = round(value, 1)
        self._eq_values[band_idx] = value
        db_label.configure(text=f"{value:+.0f}")
        self._apply_eq()

    def _apply_eq_preset(self, values: list):
        """Apply an EQ preset"""
        self._eq_values = list(values)
        for i, slider in enumerate(self._eq_sliders):
            slider.set(values[i])
        # Update all dB labels
        eq_sliders_frame = self.eq_frame.winfo_children()[-1]  # last child is sliders frame
        for i, col_frame in enumerate(eq_sliders_frame.winfo_children()):
            children = col_frame.winfo_children()
            if children:
                children[0].configure(text=f"{values[i]:+.0f}")  # dB label is first child
        self._apply_eq()

    # Equalizer APO config path - writes EQ settings to this file,
    # APO driver picks up changes instantly at the WASAPI level.
    _APO_EQ_FILE = r"D:\EqualizerAPO\config\quickplayer_eq.txt"

    def _apply_eq(self):
        """Apply EQ via Equalizer APO (system-level WASAPI filter).

        Writes a GraphicEQ config to APO's config file. APO monitors
        the file and applies changes in real-time at the audio driver
        level - no mpv filter chain needed.
        """
        freqs = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

        try:
            # Build GraphicEQ line: "31 0; 62 0; 125 5; ..." etc.
            pairs = [f"{f} {g:.1f}" for f, g in zip(freqs, self._eq_values)]
            graphic_eq = "; ".join(pairs)

            # Calculate preamp to prevent clipping (negative of max gain)
            max_gain = max(self._eq_values)
            preamp = -max_gain if max_gain > 0 else 0

            config = f"Preamp: {preamp:.1f} dB\nGraphicEQ: {graphic_eq}\n"

            with open(self._APO_EQ_FILE, 'w') as f:
                f.write(config)

        except Exception as e:
            print(f"[QUICKPLAYER] EQ write error: {e}")

    def _update_time(self, current_time: float):
        """Update time display"""
        if self.duration > 0:
            # Update time label
            cur_min = int(current_time // 60)
            cur_sec = int(current_time % 60)
            dur_min = int(self.duration // 60)
            dur_sec = int(self.duration % 60)
            self.time_label.configure(text=f"{cur_min:02d}:{cur_sec:02d} / {dur_min:02d}:{dur_sec:02d}")

            # Update progress slider (without triggering seek)
            progress = (current_time / self.duration) * 100
            self.progress_slider.set(progress)

    def _update_play_button(self):
        """Update play button icon"""
        if self.is_playing:
            self.play_btn.configure(text="⏸")
        else:
            self.play_btn.configure(text="▶")

    def _pop_out(self):
        """Pop out current video into fullscreen window"""
        if not self.current_file:
            self._log("No file loaded to pop out", "error")
            return

        ext = os.path.splitext(self.current_file)[1].lower()
        if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
            self._log("Pop out only works for video/audio files", "error")
            return

        # Get current playback position
        position = 0.0
        if self.player:
            try:
                pos = self.player.time_pos
                if pos is not None:
                    position = pos
            except:
                pass

        # Pause embedded player
        if self.player and self.is_playing:
            try:
                self.player.pause = True
            except:
                pass

        file_path = self.current_file

        def on_popout_close(resume_pos):
            """Called when pop-out closes - resume in embedded player"""
            if self.player and self.current_file == file_path:
                try:
                    self.player.seek(resume_pos, 'absolute')
                    self.player.pause = False
                except:
                    pass

        # Create pop-out window
        QuickPlayerPopOut(self.winfo_toplevel(), file_path, position, on_popout_close)

    def destroy(self):
        """Clean up both players"""
        self._stop_poll()
        for p in (self._audio_player, self._video_player):
            if p:
                try:
                    p.terminate()
                except:
                    pass
        super().destroy()


class QuickPlayerPopOut(tk.Toplevel):
    """Fullscreen pop-out video player window"""

    def __init__(self, parent, file_path: str, start_position: float = 0.0,
                 on_close_callback=None, standalone: bool = False):
        super().__init__(parent)

        self.file_path = file_path
        self.start_position = start_position
        self.on_close_callback = on_close_callback
        self.standalone = standalone
        self.player: Optional[mpv.MPV] = None
        self.is_playing = False
        self.duration = 0.0
        self._controls_visible = True
        self._hide_timer = None
        self._is_fullscreen = True
        self._closing = False

        # Window setup
        self.title(f"QuickPlayer - {os.path.basename(file_path)}")
        self.configure(bg='black')
        self.attributes('-fullscreen', True)
        self.focus_set()

        self._build_ui()
        self._bind_keys()
        self._init_player()

        # Start auto-hide timer for controls
        self._reset_hide_timer()

    def _build_ui(self):
        """Build the pop-out player UI"""
        # Video area fills entire window
        self.video_frame = tk.Frame(self, bg='black')
        self.video_frame.pack(fill="both", expand=True)

        # Controls overlay at bottom
        self.controls_frame = tk.Frame(self, bg='#1a1a2e', height=70)
        self.controls_frame.pack(side="bottom", fill="x")
        self.controls_frame.pack_propagate(False)

        # Play/Pause button
        self.play_btn = tk.Button(
            self.controls_frame, text="⏸", font=("Segoe UI", 22),
            bg='#0047AB', fg='white', activebackground='#0066FF',
            activeforeground='white', bd=0, width=4,
            command=self._toggle_play
        )
        self.play_btn.pack(side="left", padx=10, pady=8)

        # Stop button
        self.stop_btn = tk.Button(
            self.controls_frame, text="⏹", font=("Segoe UI", 22),
            bg='#333355', fg='white', activebackground='#555577',
            activeforeground='white', bd=0, width=4,
            command=self._stop
        )
        self.stop_btn.pack(side="left", padx=5, pady=8)

        # Skip back button (-15s)
        self.skip_back_btn = tk.Button(
            self.controls_frame, text="⏪", font=("Segoe UI", 20),
            bg='#333355', fg='white', activebackground='#555577',
            activeforeground='white', bd=0, width=4,
            command=lambda: self._seek_relative(-15)
        )
        self.skip_back_btn.pack(side="left", padx=3, pady=8)

        # Skip forward button (+30s)
        self.skip_fwd_btn = tk.Button(
            self.controls_frame, text="⏩", font=("Segoe UI", 20),
            bg='#333355', fg='white', activebackground='#555577',
            activeforeground='white', bd=0, width=4,
            command=lambda: self._seek_relative(30)
        )
        self.skip_fwd_btn.pack(side="left", padx=(3, 10), pady=8)

        # Time label
        self.time_label = tk.Label(
            self.controls_frame, text="00:00 / 00:00",
            font=("Segoe UI", 16, "bold"), bg='#1a1a2e', fg='white'
        )
        self.time_label.pack(side="left", padx=15)

        # Seek slider - use tk.Scale for simplicity in Toplevel
        self.seek_var = tk.DoubleVar(value=0)
        self.seek_slider = tk.Scale(
            self.controls_frame, from_=0, to=1000, orient="horizontal",
            variable=self.seek_var, showvalue=False,
            bg='#1a1a2e', fg='white', troughcolor='#333355',
            highlightthickness=0, sliderrelief="flat",
            command=self._on_seek
        )
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10, pady=12)

        # Volume label
        vol_label = tk.Label(
            self.controls_frame, text="🔊", font=("Segoe UI", 18),
            bg='#1a1a2e', fg='white'
        )
        vol_label.pack(side="left", padx=(10, 2))

        # Volume slider (0-150 with boost)
        self.vol_var = tk.IntVar(value=100)
        self.vol_slider = tk.Scale(
            self.controls_frame, from_=0, to=150, orient="horizontal",
            variable=self.vol_var, showvalue=True, length=120,
            bg='#1a1a2e', fg='white', troughcolor='#333355',
            highlightthickness=0, sliderrelief="flat",
            command=self._on_volume
        )
        self.vol_slider.pack(side="left", padx=(0, 10), pady=12)

        # Back to CCL / Close button
        close_text = "✕ Close" if self.standalone else "↩ Back to CCL"
        self.close_btn = tk.Button(
            self.controls_frame, text=close_text, font=("Segoe UI", 14, "bold"),
            bg='#8B0000', fg='white', activebackground='#CC0000',
            activeforeground='white', bd=0, padx=15,
            command=self._close_popout
        )
        self.close_btn.pack(side="right", padx=10, pady=8)

        # Bind mouse movement on video frame to show controls
        self.video_frame.bind('<Motion>', self._on_mouse_move)
        self.controls_frame.bind('<Motion>', self._on_mouse_move)
        self.bind('<Motion>', self._on_mouse_move)

        # Mouse wheel = volume (linked to slider)
        self.bind_all('<MouseWheel>', self._on_mousewheel_volume)

        # Double-click to toggle fullscreen
        self.video_frame.bind('<Double-Button-1>', lambda e: self._toggle_fullscreen())

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

    def _toggle_mute(self):
        """Toggle mute"""
        if self.player:
            try:
                self.player.mute = not self.player.mute
            except:
                pass

    def _init_player(self):
        """Initialize MPV player in the pop-out window"""
        if not HAS_MPV:
            return

        self._poll_timer_id = None

        try:
            self.video_frame.update_idletasks()
            wid = self.video_frame.winfo_id()

            self.player = mpv.MPV(
                wid=str(int(wid)),
                # Video
                hwdec='auto-safe',
                vo='gpu',
                video_sync='audio',
                # Audio - high-quality headphone-tuned
                ao='wasapi',
                audio_buffer=1.0,
                audio_stream_silence='yes',
                audio_samplerate=48000,
                audio_format='float',
                audio_channels='stereo',
                volume_max=150,
                gapless_audio='weak',
                demuxer_max_bytes=50*1024*1024,
                demuxer_readahead_secs=30,
                # General
                keep_open=True,
                idle=True,
                osd_level=0,
                input_default_bindings=False,
                input_vo_keyboard=False,
            )

            # NO property observers - use polling instead (same fix as embedded player)

            # Load the file
            self.player.loadfile(self.file_path)

            # Start polling timer for UI updates
            self._start_poll()

            # Seek to position after a short delay
            if self.start_position > 0:
                def do_seek():
                    try:
                        if self.player and self.start_position > 0:
                            self.player.seek(self.start_position, 'absolute')
                            self.start_position = 0
                    except:
                        pass
                self.after(500, do_seek)

            self.is_playing = True
            print(f"[POPOUT] Playing: {self.file_path}")

        except Exception as e:
            print(f"[POPOUT] Failed to init MPV: {e}")
            self.player = None

    def _start_poll(self):
        """Start polling MPV state every 250ms"""
        self._stop_poll()

        def poll():
            if not self.player or self._closing:
                return
            try:
                pos = self.player.time_pos
                dur = self.player.duration
                if dur is not None:
                    self.duration = dur
                if pos is not None:
                    self._update_time(pos)

                paused = self.player.pause
                if paused is not None:
                    new_playing = not paused
                    if new_playing != self.is_playing:
                        self.is_playing = new_playing
                        self._update_play_button()
            except Exception:
                pass

            self._poll_timer_id = self.after(1000, poll)

        self._poll_timer_id = self.after(1000, poll)

    def _stop_poll(self):
        """Stop the polling timer"""
        if hasattr(self, '_poll_timer_id') and self._poll_timer_id is not None:
            try:
                self.after_cancel(self._poll_timer_id)
            except Exception:
                pass
            self._poll_timer_id = None

    def _update_time(self, current_time: float):
        """Update time display and seek slider"""
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
        """Update play/pause button text"""
        if self._closing:
            return
        self.play_btn.configure(text="⏸" if self.is_playing else "▶")

    def _toggle_play(self):
        """Toggle play/pause"""
        if self.player:
            try:
                self.player.pause = not self.player.pause
            except:
                pass

    def _stop(self):
        """Stop playback"""
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
        """Handle seek slider"""
        if self.player and self.duration > 0:
            try:
                seek_time = (float(value) / 1000) * self.duration
                self.player.seek(seek_time, 'absolute')
            except:
                pass

    def _seek_relative(self, seconds: int):
        """Seek forward/backward by seconds"""
        if self.player:
            try:
                self.player.seek(seconds, 'relative')
            except:
                pass

    def _on_volume(self, value):
        """Handle volume slider"""
        if self.player:
            try:
                self.player.volume = int(value)
            except:
                pass

    def _adjust_volume(self, delta: int):
        """Adjust volume by delta (0-150 range)"""
        current = self.vol_var.get()
        new_vol = max(0, min(150, current + delta))
        self.vol_var.set(new_vol)
        if self.player:
            try:
                self.player.volume = new_vol
            except:
                pass

    def _on_mousewheel_volume(self, event):
        """Mouse wheel controls volume, linked to slider"""
        delta = 5 if event.delta > 0 else -5
        self._adjust_volume(delta)

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self._is_fullscreen = not self._is_fullscreen
        self.attributes('-fullscreen', self._is_fullscreen)

    def _on_mouse_move(self, event=None):
        """Show controls on mouse movement"""
        if not self._controls_visible:
            self.controls_frame.pack(side="bottom", fill="x")
            self._controls_visible = True
            self.configure(cursor='')
        self._reset_hide_timer()

    def _reset_hide_timer(self):
        """Reset the auto-hide timer for controls"""
        if self._hide_timer:
            self.after_cancel(self._hide_timer)
        self._hide_timer = self.after(3000, self._hide_controls)

    def _hide_controls(self):
        """Hide controls after timeout"""
        if self.is_playing and not self._closing:
            self.controls_frame.pack_forget()
            self._controls_visible = False
            self.configure(cursor='none')

    def _close_popout(self):
        """Close the pop-out window and return to embedded mode"""
        self._closing = True
        self._stop_poll()

        # Get current position before closing
        resume_pos = 0.0
        if self.player:
            try:
                pos = self.player.time_pos
                if pos is not None:
                    resume_pos = pos
            except:
                pass

        # Clean up player
        if self.player:
            try:
                self.player.stop()
                _time.sleep(0.1)
                self.player.terminate()
            except:
                pass
            self.player = None

        # Cancel hide timer
        if self._hide_timer:
            self.after_cancel(self._hide_timer)

        # Notify parent to resume
        if self.on_close_callback:
            try:
                self.on_close_callback(resume_pos)
            except:
                pass

        self.destroy()

        # If standalone, quit the app
        if self.standalone:
            try:
                self.master.quit()
            except:
                pass
