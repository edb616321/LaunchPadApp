"""
QuickPlayer - Video Player Widget for Command Center LaunchPad
Supports drag-and-drop, MPV playback
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import os
from typing import Optional, Callable

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

# Colors matching CCL theme
COLORS = {
    "bg_dark": "#001A4D",
    "card_bg": "#0047AB",
    "card_hover": "#0066FF",
    "text": "#FFFFFF",
    "accent": "#00BFFF",
    "accent_hover": "#1E90FF",
}

# Supported video formats
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv', '.mpg', '.mpeg'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}


class QuickPlayerWidget(ctk.CTkFrame):
    """Video player widget with drag-and-drop support"""

    def __init__(self, parent, log_callback: Optional[Callable[[str, str], None]] = None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self.log_callback = log_callback
        self.player: Optional[mpv.MPV] = None
        self.current_file: Optional[str] = None
        self.is_playing = False
        self.duration = 0.0

        self._setup_ui()
        self._setup_player()
        self._setup_drag_drop()

    def _log(self, message: str, level: str = "info"):
        """Log to activity log"""
        if self.log_callback:
            self.log_callback(message, level)

    def _setup_ui(self):
        """Setup the player UI"""
        # Header - BIGGER
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], height=70)
        header.pack(fill="x", padx=5, pady=5)
        header.pack_propagate(False)

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

        # File name label - BIGGER
        self.file_label = ctk.CTkLabel(
            header,
            text="Drop video here or click Open",
            font=ctk.CTkFont(size=24),
            text_color=COLORS["text"]
        )
        self.file_label.pack(side="left", padx=20)

        # Video container (black background)
        self.video_container = tk.Frame(self, bg='black')
        self.video_container.pack(fill="both", expand=True, padx=10, pady=5)

        # Video frame for MPV
        self.video_frame = tk.Frame(self.video_container, bg='black')
        self.video_frame.pack(fill="both", expand=True)

        # Placeholder text (shown when no video) - BIGGER
        self.placeholder = tk.Label(
            self.video_frame,
            text="🎬\n\nDrag & Drop Video Here\n\nor click Open",
            font=("Segoe UI", 32),
            fg="#6666AA",
            bg="black",
            justify="center"
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Controls bar - BIGGER
        controls = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], height=80)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        controls.pack_propagate(False)

        # Play/Pause button - BIGGER
        self.play_btn = ctk.CTkButton(
            controls,
            text="▶",
            width=80,
            height=60,
            font=ctk.CTkFont(size=32),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._toggle_play
        )
        self.play_btn.pack(side="left", padx=10, pady=10)

        # Stop button - BIGGER
        stop_btn = ctk.CTkButton(
            controls,
            text="⏹",
            width=80,
            height=60,
            font=ctk.CTkFont(size=32),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self._stop
        )
        stop_btn.pack(side="left", padx=5, pady=10)

        # Time label - BIGGER
        self.time_label = ctk.CTkLabel(
            controls,
            text="00:00 / 00:00",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"]
        )
        self.time_label.pack(side="left", padx=15)

        # Progress slider - BIGGER
        self.progress_slider = ctk.CTkSlider(
            controls,
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

        # Volume - BIGGER
        vol_label = ctk.CTkLabel(
            controls,
            text="🔊",
            font=ctk.CTkFont(size=28)
        )
        vol_label.pack(side="left", padx=(15, 5))

        self.volume_slider = ctk.CTkSlider(
            controls,
            from_=0,
            to=100,
            width=120,
            height=24,
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            progress_color=COLORS["accent"],
            command=self._on_volume
        )
        self.volume_slider.pack(side="left", padx=(0, 20))
        self.volume_slider.set(100)

    def _setup_player(self):
        """Initialize MPV player"""
        if not HAS_MPV:
            print("[QUICKPLAYER] MPV not available, video playback disabled")
            return

        try:
            # Wait for frame to be ready
            self.video_frame.update_idletasks()
            wid = self.video_frame.winfo_id()

            self.player = mpv.MPV(
                wid=str(int(wid)),
                hwdec='auto',
                vo='gpu',
                keep_open=True,
                idle=True,
                osd_level=0,
                input_default_bindings=False,
                input_vo_keyboard=False,
            )

            # Observe properties for UI updates
            # Note: These callbacks run in MPV's event thread, not the main thread
            # We use try-except to handle cases where tkinter's mainloop isn't ready
            @self.player.property_observer('time-pos')
            def time_observer(_name, value):
                if value is not None:
                    try:
                        self.after(0, lambda v=value: self._update_time(v))
                    except RuntimeError:
                        pass  # Ignore if main thread not in main loop

            @self.player.property_observer('duration')
            def duration_observer(_name, value):
                if value is not None:
                    self.duration = value

            @self.player.property_observer('pause')
            def pause_observer(_name, value):
                self.is_playing = not value
                try:
                    self.after(0, self._update_play_button)
                except RuntimeError:
                    pass  # Ignore if main thread not in main loop

            print("[QUICKPLAYER] MPV player initialized")

        except Exception as e:
            print(f"[QUICKPLAYER] Failed to init MPV: {e}")
            self.player = None

    def _setup_drag_drop(self):
        """Setup drag and drop support"""
        # Register drop target
        try:
            self.video_frame.drop_target_register('DND_Files')
            self.video_frame.dnd_bind('<<Drop>>', self._on_drop)
        except:
            pass  # TkDND not available

        # Also bind to the whole widget for fallback
        self.video_container.bind('<Button-1>', lambda e: self._open_file())

    def _on_drop(self, event):
        """Handle file drop"""
        files = self.tk.splitlist(event.data)
        if files:
            self.load_file(files[0])

    def _open_file(self):
        """Open file dialog"""
        filetypes = [
            ("Video files", "*.mp4 *.avi *.mkv *.mov *.wmv *.webm *.m4v"),
            ("Audio files", "*.mp3 *.wav *.flac *.m4a *.ogg"),
            ("All files", "*.*")
        ]
        file_path = filedialog.askopenfilename(
            title="Open Video/Audio",
            filetypes=filetypes
        )
        if file_path:
            self.load_file(file_path)

    def load_file(self, file_path: str):
        """Load a video or audio file"""
        if not os.path.exists(file_path):
            self._log(f"File not found: {file_path}", "error")
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in VIDEO_EXTENSIONS and ext not in AUDIO_EXTENSIONS:
            self._log(f"Unsupported format: {ext}", "warning")
            return

        self.current_file = file_path
        filename = os.path.basename(file_path)
        self.file_label.configure(text=filename[:50] + "..." if len(filename) > 50 else filename)

        # Hide placeholder
        self.placeholder.place_forget()

        if self.player:
            try:
                self.player.loadfile(file_path)
                self._log(f"Playing: {filename}", "success")
            except Exception as e:
                self._log(f"Load error: {e}", "error")
        else:
            self._log("Video player not available", "error")

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
        """Handle volume slider"""
        if self.player:
            try:
                self.player.volume = int(value)
            except:
                pass

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

    def destroy(self):
        """Clean up"""
        if self.player:
            try:
                self.player.terminate()
            except:
                pass
        super().destroy()
