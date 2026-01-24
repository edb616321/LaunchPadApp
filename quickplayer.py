"""
QuickPlayer - Multi-format Viewer Widget for Command Center LaunchPad
Supports video, audio, images, markdown, HTML, and text files
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

        # Store original image for rescaling
        self._original_image = None
        self._original_image_path = None

        # NOW pack the content container - it expands into remaining space above controls
        self.content_container.pack(fill="both", expand=True, padx=10, pady=5)

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
        # Register drop target on content container
        try:
            self.content_container.drop_target_register('DND_Files')
            self.content_container.dnd_bind('<<Drop>>', self._on_drop)
        except:
            pass  # TkDND not available

        # Also bind to the whole widget for fallback click-to-open
        self.content_container.bind('<Button-1>', lambda e: self._open_file())
        self.placeholder.bind('<Button-1>', lambda e: self._open_file())

    def _on_drop(self, event):
        """Handle file drop"""
        files = self.tk.splitlist(event.data)
        if files:
            self.load_file(files[0])

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

    def _show_video_controls(self, show: bool):
        """Show or hide video controls (swap inside always-visible bar)"""
        if show:
            self.image_controls_frame.pack_forget()
            self.video_controls_frame.pack(side="left", fill="both", expand=True)
        else:
            self.video_controls_frame.pack_forget()

    def _load_video(self, file_path: str, filename: str):
        """Load video/audio file"""
        self.current_mode = "video"
        # Show bottom controls bar for video, hide top image bar
        self._show_image_controls(False)
        self.controls_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.video_controls_frame.pack(side="left", fill="both", expand=True)
        self.video_frame.pack(fill="both", expand=True)

        if self.player:
            try:
                self.player.loadfile(file_path)
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
