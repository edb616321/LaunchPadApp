"""
QuickFiles - Dual-Pane File Manager Widget for Command Center LaunchPad
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from datetime import datetime
from tkinter import messagebox, Menu
import threading
import subprocess
import shutil

from file_operations import (
    FileOperationManager, OperationProgress, OperationType,
    FileOperationResult, format_size, format_date
)

# Color theme matching CCL
COLORS = {
    "bg_dark": "#001A4D",
    "card_bg": "#0047AB",
    "card_hover": "#0066FF",
    "text": "#FFFFFF",
    "accent": "#00BFFF",
    "accent_hover": "#1E90FF",
    "border": "#1E3A5F",
    "selected": "#0066FF",
    "folder": "#FFD700",
    "file": "#FFFFFF",
}

QUICKFILES_CONFIG = "quickfiles.json"

# Default bookmarks with display names
DEFAULT_BOOKMARKS = {
    "D:": {"path": "D:\\", "name": "D:"},
    "Home": {"path": "C:\\Users\\edb616321", "name": "Home"},
    "LaunchPad": {"path": "D:\\LaunchPadApp", "name": "LaunchPad"},
    "QuickTube": {"path": "D:\\QuickTube", "name": "QuickTube"},
    "F:": {"path": "F:\\", "name": "F:"},
    "Downloads": {"path": "C:\\Users\\edb616321\\Downloads", "name": "Downloads"},
    "Desktop": {"path": "C:\\Users\\edb616321\\Desktop", "name": "Desktop"},
    "Documents": {"path": "C:\\Users\\edb616321\\Documents", "name": "Documents"},
}


class FileItem:
    """Represents a file or folder - LAZY stat() for performance"""
    def __init__(self, path: str, is_dir: bool = None):
        self.path = path
        self.name = os.path.basename(path) or path
        # Use provided is_dir or check (os.path.isdir is fast)
        self.is_dir = is_dir if is_dir is not None else os.path.isdir(path)
        # Lazy - don't stat() until needed
        self._size = None
        self._modified = None
        self._created = None
        self._stat_loaded = False

    def _load_stat(self):
        """Load stat info lazily"""
        if self._stat_loaded:
            return
        self._stat_loaded = True
        try:
            stat = os.stat(self.path)
            self._size = stat.st_size if not self.is_dir else 0
            self._modified = stat.st_mtime
            self._created = stat.st_ctime  # Creation time on Windows
        except (OSError, PermissionError):
            self._size = 0
            self._modified = 0
            self._created = 0

    @property
    def size(self):
        self._load_stat()
        return self._size

    @property
    def modified(self):
        self._load_stat()
        return self._modified

    @property
    def created(self):
        self._load_stat()
        return self._created

    @property
    def extension(self) -> str:
        if self.is_dir:
            return ""
        return Path(self.path).suffix.lower()

    @property
    def icon(self) -> str:
        if self.is_dir:
            return "📁"
        ext = self.extension
        if ext in ['.py', '.pyw']:
            return "🐍"
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            return "📜"
        elif ext in ['.html', '.htm']:
            return "🌐"
        elif ext in ['.css', '.scss', '.sass']:
            return "🎨"
        elif ext in ['.json', '.xml', '.yaml', '.yml']:
            return "📋"
        elif ext in ['.md', '.txt', '.log']:
            return "📝"
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg']:
            return "🖼️"
        elif ext in ['.mp3', '.wav', '.flac', '.ogg', '.m4a']:
            return "🎵"
        elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm']:
            return "🎬"
        elif ext in ['.pdf']:
            return "📕"
        elif ext in ['.doc', '.docx']:
            return "📄"
        elif ext in ['.xls', '.xlsx']:
            return "📊"
        elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            return "📦"
        elif ext in ['.exe', '.msi']:
            return "⚙️"
        elif ext in ['.bat', '.cmd', '.ps1']:
            return "⚡"
        else:
            return "📄"


# =============================================================================
# QuickMedia Feature Dialogs
# =============================================================================

def find_ffmpeg() -> Optional[str]:
    """Find FFmpeg executable"""
    # Check common locations
    paths_to_check = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        shutil.which("ffmpeg"),
    ]
    for path in paths_to_check:
        if path and os.path.exists(path):
            return path
    return None


class AudioAdjustDialog(ctk.CTkToplevel):
    """Dialog for adjusting audio volume and normalization"""

    def __init__(self, parent, file_path: str, log_callback=None):
        super().__init__(parent)

        self.file_path = file_path
        self.log_callback = log_callback
        self.ffmpeg_path = find_ffmpeg()

        self.title("Adjust Audio")
        self.geometry("500x350")
        self.configure(fg_color=COLORS["bg_dark"])
        self.grab_set()

        self._setup_ui()

    def _log(self, msg, level="info"):
        if self.log_callback:
            self.log_callback(msg, level)

    def _setup_ui(self):
        # Title
        ctk.CTkLabel(
            self,
            text="🔊 Adjust Audio",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(pady=20)

        # File name
        filename = os.path.basename(self.file_path)
        ctk.CTkLabel(
            self,
            text=filename[:60] + "..." if len(filename) > 60 else filename,
            font=ctk.CTkFont(size=16),
            text_color=COLORS["text"]
        ).pack(pady=5)

        # Volume adjustment slider
        vol_frame = ctk.CTkFrame(self, fg_color="transparent")
        vol_frame.pack(fill="x", padx=40, pady=20)

        ctk.CTkLabel(
            vol_frame,
            text="Volume Adjustment (dB):",
            font=ctk.CTkFont(size=18),
            text_color=COLORS["text"]
        ).pack(anchor="w")

        slider_frame = ctk.CTkFrame(vol_frame, fg_color="transparent")
        slider_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(slider_frame, text="-20", text_color=COLORS["text"]).pack(side="left")

        self.volume_slider = ctk.CTkSlider(
            slider_frame,
            from_=-20,
            to=20,
            number_of_steps=40,
            width=300,
            command=self._update_volume_label
        )
        self.volume_slider.set(0)
        self.volume_slider.pack(side="left", padx=10, expand=True)

        ctk.CTkLabel(slider_frame, text="+20", text_color=COLORS["text"]).pack(side="left")

        self.volume_label = ctk.CTkLabel(
            vol_frame,
            text="0 dB",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"]
        )
        self.volume_label.pack(pady=5)

        # Normalize checkbox
        self.normalize_var = tk.BooleanVar(value=False)
        self.normalize_check = ctk.CTkCheckBox(
            self,
            text="Normalize Audio (loudnorm filter)",
            font=ctk.CTkFont(size=16),
            variable=self.normalize_var,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"]
        )
        self.normalize_check.pack(pady=10)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame,
            text="Apply",
            width=120,
            height=45,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._apply
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=120,
            height=45,
            font=ctk.CTkFont(size=18),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self.destroy
        ).pack(side="left", padx=10)

    def _update_volume_label(self, value):
        self.volume_label.configure(text=f"{int(value):+d} dB")

    def _apply(self):
        if not self.ffmpeg_path:
            messagebox.showerror("Error", "FFmpeg not found! Please install FFmpeg.")
            return

        volume_db = int(self.volume_slider.get())
        normalize = self.normalize_var.get()

        # Generate output filename
        base, ext = os.path.splitext(self.file_path)
        output_path = f"{base}_adjusted{ext}"

        # Build FFmpeg command
        filters = []
        if volume_db != 0:
            filters.append(f"volume={volume_db}dB")
        if normalize:
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

        if not filters:
            messagebox.showinfo("Info", "No adjustments selected.")
            return

        filter_str = ",".join(filters)

        cmd = [
            self.ffmpeg_path, "-y", "-i", self.file_path,
            "-af", filter_str,
            "-c:v", "copy",
            output_path
        ]

        self._log(f"Adjusting audio: {os.path.basename(self.file_path)}", "info")
        self.destroy()

        # Run in background thread
        def run_ffmpeg():
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self._log(f"Audio adjusted: {os.path.basename(output_path)}", "success")
                else:
                    self._log(f"FFmpeg error: {result.stderr[:200]}", "error")
            except Exception as e:
                self._log(f"Error: {str(e)}", "error")

        threading.Thread(target=run_ffmpeg, daemon=True).start()


class ConvertDialog(ctk.CTkToplevel):
    """Dialog for converting media files to different formats"""

    def __init__(self, parent, file_path: str, log_callback=None):
        super().__init__(parent)

        self.file_path = file_path
        self.log_callback = log_callback
        self.ffmpeg_path = find_ffmpeg()

        self.title("Convert Media")
        self.geometry("500x400")
        self.configure(fg_color=COLORS["bg_dark"])
        self.grab_set()

        self._setup_ui()

    def _log(self, msg, level="info"):
        if self.log_callback:
            self.log_callback(msg, level)

    def _setup_ui(self):
        # Title
        ctk.CTkLabel(
            self,
            text="🔄 Convert Media",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(pady=20)

        # File name
        filename = os.path.basename(self.file_path)
        ctk.CTkLabel(
            self,
            text=filename[:60] + "..." if len(filename) > 60 else filename,
            font=ctk.CTkFont(size=16),
            text_color=COLORS["text"]
        ).pack(pady=5)

        # Current format
        current_ext = os.path.splitext(self.file_path)[1].lower()
        ctk.CTkLabel(
            self,
            text=f"Current format: {current_ext}",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text"]
        ).pack(pady=5)

        # Output format selection
        format_frame = ctk.CTkFrame(self, fg_color="transparent")
        format_frame.pack(fill="x", padx=40, pady=20)

        ctk.CTkLabel(
            format_frame,
            text="Convert to:",
            font=ctk.CTkFont(size=18),
            text_color=COLORS["text"]
        ).pack(anchor="w")

        # Video formats
        video_formats = [".mp4", ".mkv", ".avi", ".mov", ".webm"]
        audio_formats = [".mp3", ".m4a", ".wav", ".flac", ".ogg"]

        self.format_var = ctk.StringVar(value=".mp4")

        # Determine if source is audio or video
        audio_exts = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}
        is_audio = current_ext in audio_exts

        formats = audio_formats if is_audio else video_formats

        format_menu = ctk.CTkOptionMenu(
            format_frame,
            width=300,
            height=40,
            font=ctk.CTkFont(size=16),
            variable=self.format_var,
            values=formats
        )
        format_menu.pack(pady=10)

        # Quality preset
        quality_frame = ctk.CTkFrame(self, fg_color="transparent")
        quality_frame.pack(fill="x", padx=40, pady=10)

        ctk.CTkLabel(
            quality_frame,
            text="Quality:",
            font=ctk.CTkFont(size=18),
            text_color=COLORS["text"]
        ).pack(anchor="w")

        self.quality_var = ctk.StringVar(value="High")
        quality_menu = ctk.CTkOptionMenu(
            quality_frame,
            width=300,
            height=40,
            font=ctk.CTkFont(size=16),
            variable=self.quality_var,
            values=["High", "Medium", "Low", "Lossless"]
        )
        quality_menu.pack(pady=10)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame,
            text="Convert",
            width=120,
            height=45,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._convert
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=120,
            height=45,
            font=ctk.CTkFont(size=18),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self.destroy
        ).pack(side="left", padx=10)

    def _convert(self):
        if not self.ffmpeg_path:
            messagebox.showerror("Error", "FFmpeg not found! Please install FFmpeg.")
            return

        target_format = self.format_var.get()
        quality = self.quality_var.get()

        # Generate output filename
        base = os.path.splitext(self.file_path)[0]
        output_path = f"{base}_converted{target_format}"

        # Build FFmpeg command based on format and quality
        cmd = [self.ffmpeg_path, "-y", "-i", self.file_path]

        # Quality settings
        if target_format in [".mp4", ".mkv", ".avi", ".mov"]:
            # Video formats
            if quality == "High":
                cmd.extend(["-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "192k"])
            elif quality == "Medium":
                cmd.extend(["-c:v", "libx264", "-crf", "23", "-c:a", "aac", "-b:a", "128k"])
            elif quality == "Low":
                cmd.extend(["-c:v", "libx264", "-crf", "28", "-c:a", "aac", "-b:a", "96k"])
            else:  # Lossless
                cmd.extend(["-c:v", "libx264", "-crf", "0", "-c:a", "flac"])
        elif target_format == ".mp3":
            if quality == "High":
                cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
            elif quality == "Medium":
                cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
            else:
                cmd.extend(["-c:a", "libmp3lame", "-b:a", "128k"])
        elif target_format == ".m4a":
            cmd.extend(["-c:a", "aac", "-b:a", "256k" if quality == "High" else "128k"])
        elif target_format == ".wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif target_format == ".flac":
            cmd.extend(["-c:a", "flac"])

        cmd.append(output_path)

        self._log(f"Converting: {os.path.basename(self.file_path)} -> {target_format}", "info")
        self.destroy()

        # Run in background thread
        def run_ffmpeg():
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self._log(f"Converted: {os.path.basename(output_path)}", "success")
                else:
                    self._log(f"FFmpeg error: {result.stderr[:200]}", "error")
            except Exception as e:
                self._log(f"Error: {str(e)}", "error")

        threading.Thread(target=run_ffmpeg, daemon=True).start()


class MobileEmailDialog(ctk.CTkToplevel):
    """Dialog for optimizing media for mobile/email sharing"""

    def __init__(self, parent, file_path: str, log_callback=None):
        super().__init__(parent)

        self.file_path = file_path
        self.log_callback = log_callback
        self.ffmpeg_path = find_ffmpeg()

        self.title("Optimize for Mobile/Email")
        self.geometry("550x450")
        self.configure(fg_color=COLORS["bg_dark"])
        self.grab_set()

        self._setup_ui()

    def _log(self, msg, level="info"):
        if self.log_callback:
            self.log_callback(msg, level)

    def _setup_ui(self):
        # Title
        ctk.CTkLabel(
            self,
            text="📱 Optimize for Mobile/Email",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(pady=20)

        # File name
        filename = os.path.basename(self.file_path)
        ctk.CTkLabel(
            self,
            text=filename[:50] + "..." if len(filename) > 50 else filename,
            font=ctk.CTkFont(size=16),
            text_color=COLORS["text"]
        ).pack(pady=5)

        # Get current file size
        try:
            size_bytes = os.path.getsize(self.file_path)
            size_mb = size_bytes / (1024 * 1024)
            ctk.CTkLabel(
                self,
                text=f"Current size: {size_mb:.1f} MB",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text"]
            ).pack(pady=5)
        except:
            pass

        # Preset selection
        preset_frame = ctk.CTkFrame(self, fg_color="transparent")
        preset_frame.pack(fill="x", padx=40, pady=20)

        ctk.CTkLabel(
            preset_frame,
            text="Optimization Preset:",
            font=ctk.CTkFont(size=18),
            text_color=COLORS["text"]
        ).pack(anchor="w")

        self.preset_var = ctk.StringVar(value="mobile_hd")

        presets = [
            ("mobile_hd", "Mobile HD (720p, ~10MB/min)"),
            ("mobile_sd", "Mobile SD (480p, ~5MB/min)"),
            ("email_small", "Email Small (360p, ~3MB/min)"),
            ("email_tiny", "Email Tiny (240p, ~1MB/min)"),
            ("whatsapp", "WhatsApp (16MB limit)"),
        ]

        for preset_id, preset_label in presets:
            ctk.CTkRadioButton(
                preset_frame,
                text=preset_label,
                font=ctk.CTkFont(size=14),
                variable=self.preset_var,
                value=preset_id,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"]
            ).pack(anchor="w", pady=3)

        # Target size option
        size_frame = ctk.CTkFrame(self, fg_color="transparent")
        size_frame.pack(fill="x", padx=40, pady=10)

        self.target_size_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            size_frame,
            text="Target file size (MB):",
            font=ctk.CTkFont(size=14),
            variable=self.target_size_var,
            fg_color=COLORS["accent"]
        ).pack(side="left")

        self.target_size_entry = ctk.CTkEntry(
            size_frame,
            width=80,
            height=30,
            font=ctk.CTkFont(size=14)
        )
        self.target_size_entry.insert(0, "25")
        self.target_size_entry.pack(side="left", padx=10)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame,
            text="Optimize",
            width=120,
            height=45,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._optimize
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=120,
            height=45,
            font=ctk.CTkFont(size=18),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self.destroy
        ).pack(side="left", padx=10)

    def _optimize(self):
        if not self.ffmpeg_path:
            messagebox.showerror("Error", "FFmpeg not found! Please install FFmpeg.")
            return

        preset = self.preset_var.get()

        # Generate output filename
        base, ext = os.path.splitext(self.file_path)
        output_path = f"{base}_{preset}.mp4"

        # Preset settings: (resolution, video_bitrate, audio_bitrate)
        preset_settings = {
            "mobile_hd": ("1280x720", "1500k", "128k"),
            "mobile_sd": ("854x480", "800k", "96k"),
            "email_small": ("640x360", "500k", "64k"),
            "email_tiny": ("426x240", "250k", "48k"),
            "whatsapp": ("640x360", "600k", "64k"),
        }

        res, vbr, abr = preset_settings.get(preset, preset_settings["mobile_hd"])

        cmd = [
            self.ffmpeg_path, "-y", "-i", self.file_path,
            "-vf", f"scale={res}:force_original_aspect_ratio=decrease,pad={res}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-b:v", vbr,
            "-c:a", "aac", "-b:a", abr,
            "-movflags", "+faststart",
            output_path
        ]

        self._log(f"Optimizing for {preset}: {os.path.basename(self.file_path)}", "info")
        self.destroy()

        # Run in background thread
        def run_ffmpeg():
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    # Get output size
                    try:
                        out_size = os.path.getsize(output_path) / (1024 * 1024)
                        self._log(f"Optimized: {os.path.basename(output_path)} ({out_size:.1f} MB)", "success")
                    except:
                        self._log(f"Optimized: {os.path.basename(output_path)}", "success")
                else:
                    self._log(f"FFmpeg error: {result.stderr[:200]}", "error")
            except Exception as e:
                self._log(f"Error: {str(e)}", "error")

        threading.Thread(target=run_ffmpeg, daemon=True).start()


class FileListPane(ctk.CTkFrame):
    """Single pane showing file list - using native Treeview for speed"""

    def __init__(
        self,
        parent,
        initial_path: str = "D:\\",
        on_path_change: Optional[Callable[[str], None]] = None,
        on_selection_change: Optional[Callable[[List[str]], None]] = None,
        play_callback: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        super().__init__(parent, fg_color=COLORS["card_bg"], corner_radius=10, **kwargs)

        self.current_path = initial_path
        self.items: List[FileItem] = []
        self.recursive_results: List[FileItem] = []  # Results from recursive search
        self.on_path_change = on_path_change
        self.on_selection_change = on_selection_change
        self.play_callback = play_callback  # Callback to play media in QuickPlayer
        self.sort_by = "name"
        self.sort_ascending = True
        self.show_hidden = False

        self._setup_ui()
        self.navigate_to(initial_path)

    def _setup_ui(self):
        """Setup the pane UI with native Treeview for speed"""
        # Top bar with path and search
        top_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"])
        top_frame.pack(fill="x", padx=5, pady=5)

        # Path row with label
        path_row = ctk.CTkFrame(top_frame, fg_color="transparent")
        path_row.pack(fill="x", padx=5, pady=(5, 2))

        # FOLDER label - BIGGER FONT
        folder_label = ctk.CTkLabel(
            path_row,
            text="📁 FOLDER:",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["accent"],
            width=160
        )
        folder_label.pack(side="left", padx=(0, 5))

        # Path entry - BIGGER FONT
        self.path_entry = ctk.CTkEntry(
            path_row,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=26),
            height=50,
            placeholder_text="Enter path..."
        )
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.path_entry.bind("<Return>", self._on_path_entry_submit)

        # Search row with label and entry
        search_row = ctk.CTkFrame(top_frame, fg_color="transparent")
        search_row.pack(fill="x", padx=5, pady=(2, 5))

        # SEARCH label - BIGGER FONT
        search_label = ctk.CTkLabel(
            search_row,
            text="🔎 SEARCH:",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["accent"],
            width=160
        )
        search_label.pack(side="left", padx=(0, 5))

        # Search entry with pattern hints - BIGGER
        # Use StringVar with trace_add for real-time filtering
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)

        self.search_entry = ctk.CTkEntry(
            search_row,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=26),
            height=50,
            placeholder_text="*.mp3  *.txt  file.*  *.doc?  photo*.*",
            textvariable=self.search_var
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Recursive search checkbox - BIGGER FONT
        self.recursive_var = tk.BooleanVar(value=False)
        self.recursive_checkbox = ctk.CTkCheckBox(
            search_row,
            text="Recursive",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            checkbox_width=28,
            checkbox_height=28,
            variable=self.recursive_var,
            command=self._on_recursive_change,
            width=160
        )
        self.recursive_checkbox.pack(side="left", padx=(0, 10))

        # Search result label - shows match count - BIGGER FONT
        self.search_result_label = ctk.CTkLabel(
            search_row,
            text="",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["accent"],
            width=200
        )
        self.search_result_label.pack(side="left", padx=10)

        # Style for Treeview - dark theme with BIG fonts
        style = ttk.Style()
        style.theme_use('clam')

        # Configure Treeview colors and fonts - BIGGER
        style.configure("Custom.Treeview",
            background=COLORS["card_bg"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["card_bg"],
            font=('Segoe UI', 20),  # Bigger font
            rowheight=48  # Taller rows
        )
        style.configure("Custom.Treeview.Heading",
            background=COLORS["bg_dark"],
            foreground=COLORS["accent"],
            font=('Segoe UI', 18, 'bold')  # Bigger headings
        )
        style.map("Custom.Treeview",
            background=[('selected', COLORS["selected"])],
            foreground=[('selected', COLORS["text"])]
        )

        # Frame for Treeview + scrollbar
        tree_frame = tk.Frame(self, bg=COLORS["card_bg"])
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side="right", fill="y")

        # Treeview with Name, Size, Created, Modified columns
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("name", "size", "created", "modified"),
            show="headings",
            style="Custom.Treeview",
            yscrollcommand=scrollbar.set,
            selectmode="extended"
        )

        # Configure columns with alignment
        self.tree.heading("name", text="Name", command=lambda: self._sort_by("name"))
        self.tree.heading("size", text="Size", command=lambda: self._sort_by("size"))
        self.tree.heading("created", text="Created", command=lambda: self._sort_by("created"))
        self.tree.heading("modified", text="Modified", command=lambda: self._sort_by("modified"))

        self.tree.column("name", width=300, minwidth=150, anchor="w")
        self.tree.column("size", width=100, minwidth=80, anchor="e")  # Right-justify
        self.tree.column("created", width=160, minwidth=120, anchor="center")  # Center
        self.tree.column("modified", width=160, minwidth=120, anchor="center")  # Center

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.tree.yview)

        # Bind events
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", self._on_double_click)
        self.tree.bind("<BackSpace>", self._go_parent)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-3>", self._on_right_click)  # Right-click menu

    def _on_search_change(self, *args):
        """Filter file list based on search pattern - INSTANT filtering"""
        pattern = self.search_var.get()
        recursive = self.recursive_var.get() if hasattr(self, 'recursive_var') else False

        if recursive and pattern:
            # Do recursive search in background
            self._do_recursive_search(pattern)
        else:
            # Stop any running search animation
            self._searching_active = False
            # Clear recursive results if not searching recursively
            self.recursive_results = []
            print(f"[SEARCH TRIGGERED] Path: {self.current_path}, Pattern: '{pattern}', Items: {len(self.items)}")
            self._refresh_tree_view()

    def _on_recursive_change(self):
        """Handle recursive checkbox change"""
        pattern = self.search_var.get()
        if pattern:
            # Re-trigger search with new recursive setting
            self._on_search_change()

    def _do_recursive_search(self, pattern: str):
        """Perform recursive search in background thread"""
        import threading

        # Increment search ID to track which search is current
        if not hasattr(self, '_search_id'):
            self._search_id = 0
        self._search_id += 1
        current_search_id = self._search_id
        search_pattern = pattern  # Capture pattern for this search

        def search_worker():
            results = []
            # System folders to skip during recursive search
            skip_dirs = {'$RECYCLE.BIN', '$Recycle.Bin', 'System Volume Information',
                         '$WinREAgent', '$SysReset', 'Recovery', '$GetCurrent'}
            try:
                for root, dirs, files in os.walk(self.current_path):
                    # Check if this search was superseded by a newer one
                    if self._search_id != current_search_id:
                        print(f"[RECURSIVE SEARCH] Cancelled search for '{search_pattern}' (superseded)")
                        return

                    # Skip hidden directories and system folders
                    dirs[:] = [d for d in dirs if not d.startswith('.') and
                               not d.startswith('$') and d not in skip_dirs]

                    for name in files:
                        if self._match_pattern(name, search_pattern):
                            full_path = os.path.join(root, name)
                            try:
                                item = FileItem(full_path, is_dir=False)
                                results.append(item)
                            except (OSError, PermissionError):
                                pass

                    # Also match directories
                    for name in dirs:
                        if self._match_pattern(name, search_pattern):
                            full_path = os.path.join(root, name)
                            try:
                                item = FileItem(full_path, is_dir=True)
                                results.append(item)
                            except (OSError, PermissionError):
                                pass

                    # Limit results to prevent UI freeze
                    if len(results) > 5000:
                        break

            except (OSError, PermissionError):
                pass

            # Only update UI if this is still the current search
            if self._search_id == current_search_id:
                self.recursive_results = results
                self._searching_active = False  # Stop blinking
                self.after(0, self._refresh_tree_view)
                print(f"[RECURSIVE SEARCH] Found {len(results)} matches for '{search_pattern}'")
            else:
                # Search was superseded - new search will handle blinking
                print(f"[RECURSIVE SEARCH] Discarded results for '{search_pattern}' (superseded)")

        # Start search in background
        self.recursive_results = []
        self._searching_active = True  # Flag for blinking animation

        # Clear treeview and show "Searching..." immediately so user doesn't see old unfiltered content
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", iid="__searching__",
            values=("🔍 Searching subfolders...", "", "", ""))

        # Start blinking animation
        self._start_search_blink(current_search_id)

        thread = threading.Thread(target=search_worker, daemon=True)
        thread.start()

    def _start_search_blink(self, search_id: int):
        """Animate blinking 'Searching...' label during recursive search"""
        blink_state = [0]  # 0=visible, 1=dim

        def blink():
            # Stop if search completed or superseded
            if not getattr(self, '_searching_active', False) or self._search_id != search_id:
                return

            # Toggle between bright and dim
            if blink_state[0] == 0:
                self.search_result_label.configure(text="🔍 Searching...", text_color="#FFD700")
                blink_state[0] = 1
            else:
                self.search_result_label.configure(text="🔍 Searching...", text_color="#996600")
                blink_state[0] = 0

            # Continue blinking every 500ms
            self.after(500, blink)

        blink()

    def _stop_search_blink(self):
        """Stop the blinking animation"""
        self._searching_active = False

    def _match_pattern(self, name: str, pattern: str) -> bool:
        """Match filename against wildcard pattern (*, ?)"""
        import fnmatch
        return fnmatch.fnmatch(name.lower(), pattern.lower())

    def _on_path_entry_submit(self, event):
        """Handle path entry submission"""
        path = self.path_entry.get().strip()
        if os.path.isdir(path):
            self.navigate_to(path)
        else:
            messagebox.showwarning("Invalid Path", f"'{path}' is not a valid directory.")

    def navigate_to(self, path: str):
        """Navigate to a directory"""
        if not os.path.isdir(path):
            return

        self.current_path = os.path.abspath(path)

        # Update path entry
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, self.current_path)

        # Load directory contents
        self._load_directory()

        # Notify callback
        if self.on_path_change:
            self.on_path_change(self.current_path)

    def _load_directory(self):
        """Load directory contents into self.items"""
        self.items.clear()

        try:
            with os.scandir(self.current_path) as entries:
                for entry in entries:
                    if not self.show_hidden and entry.name.startswith('.'):
                        continue
                    try:
                        is_dir = entry.is_dir()
                        item = FileItem(entry.path, is_dir=is_dir)
                        self.items.append(item)
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError) as e:
            messagebox.showerror("Access Denied", f"Cannot access: {self.current_path}\n{e}")
            return

        # Sort and display
        self._sort_items()
        self._refresh_tree_view()

    def _refresh_tree_view(self):
        """Refresh the treeview with current items and search filter"""
        # Clear treeview
        self.tree.delete(*self.tree.get_children())

        # Get search pattern from StringVar
        pattern = self.search_var.get().strip() if hasattr(self, 'search_var') else ""
        recursive = self.recursive_var.get() if hasattr(self, 'recursive_var') else False

        # Check if we're showing recursive results
        if recursive and pattern and hasattr(self, 'recursive_results') and self.recursive_results:
            # Show recursive search results
            self._display_recursive_results()
            return

        # Add parent ".." entry if not at root
        if os.path.dirname(self.current_path) != self.current_path:
            self.tree.insert("", "end", iid="__parent__", values=("📁 ..", "", "", ""))

        # Add items to treeview
        matched_count = 0
        for idx, item in enumerate(self.items):
            # Apply search filter - check if pattern matches
            if pattern:
                if not self._match_pattern(item.name, pattern):
                    continue
                matched_count += 1

            icon = "📁" if item.is_dir else "📄"

            # Get size (skip for directories)
            if item.is_dir:
                size_str = "<DIR>"
            else:
                size_str = format_size(item.size)

            # Get dates
            created_str = self._format_datetime(item.created) if hasattr(item, 'created') and item.created else ""
            modified_str = self._format_datetime(item.modified) if item.modified else ""

            self.tree.insert("", "end", iid=str(idx),
                values=(f"{icon} {item.name}", size_str, created_str, modified_str))

        # Update search result label
        if hasattr(self, 'search_result_label'):
            if pattern:
                if matched_count == 0:
                    self.search_result_label.configure(text=f"NO MATCHES", text_color="#FF6B6B")
                else:
                    self.search_result_label.configure(text=f"{matched_count} found", text_color=COLORS["accent"])
                print(f"[SEARCH] Found {matched_count} matches for '{pattern}'")
            else:
                self.search_result_label.configure(text=f"{len(self.items)} items", text_color=COLORS["text"])

    def _display_recursive_results(self):
        """Display recursive search results in treeview"""
        results = self.recursive_results

        for idx, item in enumerate(results):
            icon = "📁" if item.is_dir else "📄"

            # Show filename with parent folder context
            filename = item.name
            try:
                rel_path = os.path.relpath(item.path, self.current_path)
                parent_dir = os.path.dirname(rel_path)
                if parent_dir:
                    # Show as "filename  [in subfolder]" for clarity
                    display_name = f"{filename}  [{parent_dir}]"
                else:
                    display_name = filename
            except ValueError:
                display_name = filename

            # Get size (skip for directories)
            if item.is_dir:
                size_str = "<DIR>"
            else:
                size_str = format_size(item.size)

            # Get dates
            created_str = self._format_datetime(item.created) if hasattr(item, 'created') and item.created else ""
            modified_str = self._format_datetime(item.modified) if item.modified else ""

            # Use "r_" prefix for recursive results to distinguish from regular items
            self.tree.insert("", "end", iid=f"r_{idx}",
                values=(f"{icon} {display_name}", size_str, created_str, modified_str))

        # Update search result label
        count = len(results)
        if count == 0:
            self.search_result_label.configure(text=f"NO MATCHES", text_color="#FF6B6B")
        elif count >= 5000:
            self.search_result_label.configure(text=f"{count}+ found", text_color="#FFD700")
        else:
            self.search_result_label.configure(text=f"{count} found", text_color=COLORS["accent"])

    def _format_datetime(self, timestamp: float) -> str:
        """Format timestamp to readable date - short but human-friendly"""
        if not timestamp:
            return ""
        try:
            dt = datetime.fromtimestamp(timestamp)
            now = datetime.now()
            delta = now - dt

            # Today
            if dt.date() == now.date():
                return f"Today {dt.strftime('%I:%M %p')}"

            # Yesterday
            yesterday = now.date().replace(day=now.day - 1) if now.day > 1 else now.date()
            if dt.date() == yesterday:
                return f"Yesterday {dt.strftime('%I:%M %p')}"

            # Within last week - show day name
            if delta.days < 7:
                day_suffix = self._get_day_suffix(dt.day)
                return f"{dt.strftime('%a')} {dt.day}{day_suffix}"

            # This year - show month and day
            if dt.year == now.year:
                day_suffix = self._get_day_suffix(dt.day)
                return f"{dt.strftime('%b')} {dt.day}{day_suffix}"

            # Older - show full date
            day_suffix = self._get_day_suffix(dt.day)
            return f"{dt.strftime('%b')} {dt.day}{day_suffix}, {dt.year}"
        except:
            return ""

    def _get_day_suffix(self, day: int) -> str:
        """Get ordinal suffix for day (1st, 2nd, 3rd, etc.)"""
        if 11 <= day <= 13:
            return "th"
        suffix = {1: "st", 2: "nd", 3: "rd"}
        return suffix.get(day % 10, "th")

    def _sort_items(self):
        """Sort items by current sort settings"""
        dirs = [i for i in self.items if i.is_dir]
        files = [i for i in self.items if not i.is_dir]

        def sort_key(item):
            if self.sort_by == "name":
                return item.name.lower()
            elif self.sort_by == "size":
                return item.size if not item.is_dir else 0
            elif self.sort_by == "modified":
                return item.modified if item.modified else 0
            elif self.sort_by == "created":
                return item.created if hasattr(item, 'created') and item.created else 0
            return item.name.lower()

        dirs.sort(key=sort_key, reverse=not self.sort_ascending)
        files.sort(key=sort_key, reverse=not self.sort_ascending)
        self.items = dirs + files

    def _sort_by(self, column: str):
        """Sort by column"""
        if self.sort_by == column:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_by = column
            self.sort_ascending = True
        self._sort_items()
        self._refresh_tree_view()

    def _on_double_click(self, event):
        """Handle double-click on treeview item"""
        selection = self.tree.selection()
        if not selection:
            return

        item_id = selection[0]

        if item_id == "__parent__":
            # Go to parent directory
            parent = os.path.dirname(self.current_path)
            self.navigate_to(parent)
        elif item_id.startswith("r_"):
            # Recursive search result
            idx = int(item_id[2:])  # Remove "r_" prefix
            if idx < len(self.recursive_results):
                item = self.recursive_results[idx]
                if item.is_dir:
                    # Navigate to the directory and clear recursive search
                    self.recursive_var.set(False)
                    self.recursive_results = []
                    self.navigate_to(item.path)
                else:
                    # Open file
                    try:
                        os.startfile(item.path)
                    except Exception as e:
                        messagebox.showerror("Error", f"Cannot open: {e}")
        else:
            # Get the actual item from regular items
            idx = int(item_id)
            if idx < len(self.items):
                item = self.items[idx]
                if item.is_dir:
                    self.navigate_to(item.path)
                else:
                    # Open file
                    try:
                        os.startfile(item.path)
                    except Exception as e:
                        messagebox.showerror("Error", f"Cannot open: {e}")

    def _go_parent(self, event):
        """Go to parent directory"""
        parent = os.path.dirname(self.current_path)
        if parent != self.current_path:
            self.navigate_to(parent)

    def _on_select(self, event):
        """Handle selection change"""
        if self.on_selection_change:
            selected_paths = self.get_selected_paths()
            self.on_selection_change(selected_paths)

    def _on_right_click(self, event):
        """Show context menu on right-click"""
        # Select item under cursor
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id != "__parent__":
            # Add to selection if not already selected
            if item_id not in self.tree.selection():
                self.tree.selection_set(item_id)

        # Create context menu - BIGGER FONT
        menu = Menu(self, tearoff=0, font=('Segoe UI', 18),
                   bg=COLORS["card_bg"], fg=COLORS["text"],
                   activebackground=COLORS["accent"], activeforeground=COLORS["text"])

        menu.add_command(label="📂 Open", command=self._open_selected)
        menu.add_command(label="📂 Open in Explorer", command=self._open_in_explorer)

        # Check if selected file is media - add QuickPlayer and QuickMedia options
        paths = self.get_selected_paths()
        if paths and len(paths) == 1:
            ext = os.path.splitext(paths[0])[1].lower()
            video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm', '.m4v', '.flv'}
            audio_exts = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}
            media_exts = video_exts | audio_exts

            if ext in media_exts:
                menu.add_separator()
                menu.add_command(label="🎬 Play in QuickPlayer", command=self._play_in_quickplayer)

                # QuickMedia features submenu
                quickmedia_menu = Menu(menu, tearoff=0, font=('Segoe UI', 16),
                                      bg=COLORS["card_bg"], fg=COLORS["text"],
                                      activebackground=COLORS["accent"], activeforeground=COLORS["text"])
                quickmedia_menu.add_command(label="🔊 Adjust Audio", command=lambda: self._open_audio_adjust(paths[0]))
                quickmedia_menu.add_command(label="🔄 Convert To...", command=lambda: self._open_convert(paths[0]))
                if ext in video_exts:
                    quickmedia_menu.add_command(label="📱 Save for Mobile/Email", command=lambda: self._open_mobile_optimize(paths[0]))
                menu.add_cascade(label="🎛️ QuickMedia", menu=quickmedia_menu)

        menu.add_separator()
        menu.add_command(label="🔄 Refresh", command=self.refresh)
        menu.add_separator()
        menu.add_command(label="📋 Copy", command=self._copy_selected)
        menu.add_command(label="✂️ Cut (Move)", command=self._move_selected)
        menu.add_command(label="📄 Paste", command=self._paste)
        menu.add_separator()
        menu.add_command(label="✏️ Rename", command=self._rename_selected)
        menu.add_command(label="🗑️ Delete", command=self._delete_selected)
        menu.add_separator()
        menu.add_command(label="📁 New Folder", command=self._new_folder)
        menu.add_separator()
        menu.add_command(label="ℹ️ Properties", command=self._show_properties)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _play_in_quickplayer(self):
        """Request to play selected file in QuickPlayer"""
        paths = self.get_selected_paths()
        if paths and hasattr(self, 'play_callback') and self.play_callback:
            self.play_callback(paths[0])

    def _get_log_callback(self):
        """Get log callback from parent widget if available"""
        # Walk up the parent chain to find QuickFilesWidget
        parent = self.master
        while parent:
            if hasattr(parent, 'log_callback'):
                return parent.log_callback
            parent = getattr(parent, 'master', None)
        return None

    def _open_audio_adjust(self, file_path: str):
        """Open audio adjustment dialog"""
        AudioAdjustDialog(self.winfo_toplevel(), file_path, self._get_log_callback())

    def _open_convert(self, file_path: str):
        """Open convert dialog"""
        ConvertDialog(self.winfo_toplevel(), file_path, self._get_log_callback())

    def _open_mobile_optimize(self, file_path: str):
        """Open mobile/email optimization dialog"""
        MobileEmailDialog(self.winfo_toplevel(), file_path, self._get_log_callback())

    def _open_in_explorer(self):
        """Open selected item in Windows Explorer"""
        paths = self.get_selected_paths()
        if paths:
            # Open folder containing the file and select it
            subprocess.run(['explorer', '/select,', paths[0]], shell=True)
        else:
            # Open current folder
            subprocess.run(['explorer', self.current_path], shell=True)

    def _paste(self):
        """Paste from clipboard - placeholder"""
        pass  # Will be implemented by parent widget

    def _show_properties(self):
        """Show file properties"""
        paths = self.get_selected_paths()
        if not paths:
            return

        path = paths[0]
        try:
            stat = os.stat(path)
            size = stat.st_size
            created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            info = f"Path: {path}\n\n"
            info += f"Size: {format_size(size)} ({size:,} bytes)\n\n"
            info += f"Created: {created}\n"
            info += f"Modified: {modified}"

            messagebox.showinfo("Properties", info)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot get properties: {e}")

    def get_selected_paths(self) -> List[str]:
        """Get list of selected file paths from Treeview"""
        paths = []
        for item_id in self.tree.selection():
            if item_id == "__parent__":
                continue
            try:
                if item_id.startswith("r_"):
                    # Recursive search result
                    idx = int(item_id[2:])
                    if idx < len(self.recursive_results):
                        paths.append(self.recursive_results[idx].path)
                else:
                    # Regular item
                    idx = int(item_id)
                    if idx < len(self.items):
                        paths.append(self.items[idx].path)
            except ValueError:
                pass
        return paths

    def get_selected_count(self) -> int:
        """Get count of selected items"""
        count = len(self.tree.selection())
        # Don't count parent ".." entry
        if "__parent__" in self.tree.selection():
            count -= 1
        return count

    def get_selected_size(self) -> int:
        """Get total size of selected items"""
        total = 0
        for item_id in self.tree.selection():
            if item_id == "__parent__":
                continue
            try:
                if item_id.startswith("r_"):
                    # Recursive search result
                    idx = int(item_id[2:])
                    if idx < len(self.recursive_results):
                        total += self.recursive_results[idx].size
                else:
                    # Regular item
                    idx = int(item_id)
                    if idx < len(self.items):
                        total += self.items[idx].size
            except ValueError:
                pass
        return total

    def refresh(self):
        """Refresh current directory"""
        self._load_directory()

    def go_parent(self):
        """Navigate to parent directory"""
        parent = os.path.dirname(self.current_path)
        if parent != self.current_path:
            self.navigate_to(parent)

    def _open_selected(self):
        """Open selected files/folders"""
        paths = self.get_selected_paths()
        for path in paths:
            if os.path.isdir(path):
                self.navigate_to(path)
                break  # Only navigate to first folder
            else:
                try:
                    os.startfile(path)
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot open: {e}")

    def _copy_selected(self):
        """Trigger copy operation - handled by parent"""
        pass

    def _move_selected(self):
        """Trigger move operation - handled by parent"""
        pass

    def _delete_selected(self):
        """Delete selected items"""
        paths = self.get_selected_paths()
        if not paths:
            return

        count = len(paths)

        if messagebox.askyesno("Confirm Delete",
            f"Delete {count} item(s) to Recycle Bin?"):

            op_mgr = FileOperationManager()
            op_mgr.delete_with_progress(
                paths,
                use_recycle_bin=True,
                complete_callback=lambda results: self.after(0, self.refresh)
            )

    def _rename_selected(self):
        """Rename selected item"""
        paths = self.get_selected_paths()
        if len(paths) != 1:
            messagebox.showwarning("Rename", "Select exactly one item to rename.")
            return

        item_path = paths[0]
        old_name = os.path.basename(item_path)

        # Create rename dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Rename")
        dialog.geometry("400x120")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="New name:",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text"]
        ).pack(pady=(20, 5))

        entry = ctk.CTkEntry(dialog, width=350, height=35)
        entry.insert(0, old_name)
        entry.pack(pady=5)
        entry.select_range(0, len(old_name) - len(Path(old_name).suffix) if "." in old_name else len(old_name))
        entry.focus_set()

        def do_rename():
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                new_path = os.path.join(self.current_path, new_name)
                try:
                    os.rename(item_path, new_path)
                    self.refresh()
                except Exception as e:
                    messagebox.showerror("Rename Error", str(e))
            dialog.destroy()

        entry.bind("<Return>", lambda e: do_rename())

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(
            btn_frame, text="Rename", width=100,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=do_rename
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=100,
            fg_color=COLORS["card_bg"], hover_color=COLORS["card_hover"],
            command=dialog.destroy
        ).pack(side="left", padx=5)

    def _new_folder(self):
        """Create new folder"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("New Folder")
        dialog.geometry("400x120")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Folder name:",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text"]
        ).pack(pady=(20, 5))

        entry = ctk.CTkEntry(dialog, width=350, height=35)
        entry.insert(0, "New Folder")
        entry.pack(pady=5)
        entry.select_range(0, "end")
        entry.focus_set()

        def do_create():
            name = entry.get().strip()
            if name:
                new_path = os.path.join(self.current_path, name)
                try:
                    os.makedirs(new_path, exist_ok=False)
                    self.refresh()
                except FileExistsError:
                    messagebox.showerror("Error", f"Folder '{name}' already exists.")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
            dialog.destroy()

        entry.bind("<Return>", lambda e: do_create())

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(
            btn_frame, text="Create", width=100,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=do_create
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=100,
            fg_color=COLORS["card_bg"], hover_color=COLORS["card_hover"],
            command=dialog.destroy
        ).pack(side="left", padx=5)


class QuickFilesWidget(ctk.CTkFrame):
    """Main QuickFiles dual-pane file manager widget"""

    def __init__(self, parent, log_callback: Optional[Callable[[str, str], None]] = None,
                 play_callback: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self.log_callback = log_callback
        self.play_callback = play_callback  # Callback to play media in QuickPlayer
        self.bookmarks = DEFAULT_BOOKMARKS.copy()
        self.active_pane = "left"  # or "right"
        self.op_manager = FileOperationManager()
        self._initialized = False  # Flag to prevent early config saves

        # Clipboard for copy/cut operations
        self.clipboard_paths: List[str] = []
        self.clipboard_operation: Optional[str] = None  # "copy" or "move"

        self._load_config()
        self._setup_ui()
        self._bind_keys()
        self._initialized = True  # Now safe to save config

    def _log(self, message: str, level: str = "info"):
        """Log message to activity log"""
        if self.log_callback:
            self.log_callback(message, level)

    def _load_config(self):
        """Load configuration from JSON"""
        config_path = os.path.join(os.path.dirname(__file__), QUICKFILES_CONFIG)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    loaded_bookmarks = config.get("bookmarks", {})

                    # Convert old format (string paths) to new format (dict with path and name)
                    if loaded_bookmarks:
                        for key, value in loaded_bookmarks.items():
                            if isinstance(value, str):
                                # Old format - convert to new
                                loaded_bookmarks[key] = {"path": value, "name": key}

                    # Merge with defaults (use loaded if exists, otherwise default)
                    self.bookmarks = DEFAULT_BOOKMARKS.copy()
                    self.bookmarks.update(loaded_bookmarks)

                    self.left_path = config.get("left_pane", {}).get("path", "D:\\")
                    self.right_path = config.get("right_pane", {}).get("path", "F:\\")
                    return
            except Exception as e:
                print(f"Error loading QuickFiles config: {e}")

        self.left_path = "D:\\"
        self.right_path = "F:\\"

    def _save_config(self):
        """Save configuration to JSON"""
        config_path = os.path.join(os.path.dirname(__file__), QUICKFILES_CONFIG)
        config = {
            "bookmarks": self.bookmarks,
            "left_pane": {
                "path": self.left_pane.current_path,
                "show_tree": True
            },
            "right_pane": {
                "path": self.right_pane.current_path,
                "show_tree": True
            },
            "show_hidden": False,
            "sort_by": "name",
            "sort_ascending": True
        }
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving QuickFiles config: {e}")

    def _setup_ui(self):
        """Setup the main UI"""
        # Header with title and bookmarks - BIGGER
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], height=70)
        header.pack(fill="x", padx=5, pady=(5, 0))
        header.pack_propagate(False)

        # Title - HUGE READABLE
        title = ctk.CTkLabel(
            header,
            text="📁 QUICKFILES",
            font=ctk.CTkFont(size=40, weight="bold"),
            text_color=COLORS["accent"]
        )
        title.pack(side="left", padx=10)

        # Bookmark buttons with names
        bookmark_frame = ctk.CTkFrame(header, fg_color="transparent")
        bookmark_frame.pack(side="left", padx=10)

        self.bookmark_buttons = {}
        for key, bookmark in self.bookmarks.items():
            if bookmark and bookmark.get("path"):
                name = bookmark.get("name", key)
                btn = ctk.CTkButton(
                    bookmark_frame,
                    text=name,
                    width=max(110, len(name) * 18),
                    height=55,
                    font=ctk.CTkFont(size=26, weight="bold"),  # MUCH BIGGER
                    fg_color=COLORS["card_bg"],
                    hover_color=COLORS["accent"],
                    command=lambda k=key: self._goto_bookmark(k)
                )
                btn.pack(side="left", padx=4)
                self.bookmark_buttons[key] = btn

        # Settings button - BIGGER
        settings_btn = ctk.CTkButton(
            header,
            text="⚙️",
            width=60,
            height=50,
            font=ctk.CTkFont(size=28),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["accent"],
            command=self._show_settings
        )
        settings_btn.pack(side="right", padx=10)

        # Refresh button - BIGGER
        refresh_btn = ctk.CTkButton(
            header,
            text="🔄",
            width=60,
            height=50,
            font=ctk.CTkFont(size=28),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["accent"],
            command=self._refresh_both
        )
        refresh_btn.pack(side="right", padx=5)

        # Dual pane container - using PanedWindow for resizable panels
        # Style the sash (divider) for visibility
        style = ttk.Style()
        style.configure("QuickFiles.TPanedwindow", background=COLORS["accent"])

        panes_frame = ttk.PanedWindow(self, orient="horizontal")
        panes_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Left pane
        self.left_pane = FileListPane(
            panes_frame,
            initial_path=self.left_path,
            on_path_change=lambda p: self._on_path_change("left", p),
            on_selection_change=lambda s: self._on_selection_change("left", s),
            play_callback=self.play_callback
        )
        panes_frame.add(self.left_pane, weight=1)

        # Right pane
        self.right_pane = FileListPane(
            panes_frame,
            initial_path=self.right_path,
            on_path_change=lambda p: self._on_path_change("right", p),
            on_selection_change=lambda s: self._on_selection_change("right", s),
            play_callback=self.play_callback
        )
        panes_frame.add(self.right_pane, weight=1)

        # Wire up context menu clipboard operations
        self.left_pane._copy_selected = lambda: self._clipboard_copy("left")
        self.left_pane._move_selected = lambda: self._clipboard_cut("left")
        self.left_pane._paste = lambda: self._clipboard_paste("left")

        self.right_pane._copy_selected = lambda: self._clipboard_copy("right")
        self.right_pane._move_selected = lambda: self._clipboard_cut("right")
        self.right_pane._paste = lambda: self._clipboard_paste("right")

        # Track clicks on panes to set active pane
        self.left_pane.tree.bind("<Button-1>", lambda e: self._set_active_pane("left"))
        self.left_pane.tree.bind("<FocusIn>", lambda e: self._set_active_pane("left"))
        self.right_pane.tree.bind("<Button-1>", lambda e: self._set_active_pane("right"))
        self.right_pane.tree.bind("<FocusIn>", lambda e: self._set_active_pane("right"))

        # Set initial active pane visual indicator
        self._update_pane_indicators()

        # Status bar - MUCH BIGGER
        self.status_bar = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], height=70)
        self.status_bar.pack(fill="x", padx=5, pady=5)
        self.status_bar.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="Ready",
            font=ctk.CTkFont(size=26),
            text_color=COLORS["text"]
        )
        self.status_label.pack(side="left", padx=10, pady=5)

        # Action buttons - MUCH BIGGER
        btn_frame = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Copy (F5)",
            width=160,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._copy_to_other
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="Move (F6)",
            width=160,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._move_to_other
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="Delete",
            width=140,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color="#8B0000",
            hover_color="#B22222",
            command=self._delete_selected
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="New Folder",
            width=180,
            height=55,
            font=ctk.CTkFont(size=26, weight="bold"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            command=self._new_folder
        ).pack(side="left", padx=5)

    def _bind_keys(self):
        """Bind keyboard shortcuts to the widget"""
        # Bind to self and propagate to children
        def bind_key(key, callback):
            self.bind(key, callback)
            # Also bind to panes after they exist
            if hasattr(self, 'left_pane'):
                self.left_pane.bind(key, callback)
            if hasattr(self, 'right_pane'):
                self.right_pane.bind(key, callback)

        # Function key bookmarks (F1-F10)
        for i in range(1, 11):
            key = f"F{i}"
            bind_key(f"<{key}>", lambda e, k=key: self._goto_bookmark(k))
            bind_key(f"<Shift-{key}>", lambda e, k=key: self._set_bookmark(k))

        # Navigation
        bind_key("<Tab>", self._switch_pane)
        bind_key("<BackSpace>", self._go_parent)

        # Operations - these are already handled by buttons, keys are optional
        bind_key("<Delete>", lambda e: self._delete_selected())
        bind_key("<Control-n>", lambda e: self._new_folder())
        bind_key("<Control-l>", lambda e: self._focus_path_entry())

        # Clipboard shortcuts
        bind_key("<Control-c>", lambda e: self._clipboard_copy(self.active_pane))
        bind_key("<Control-x>", lambda e: self._clipboard_cut(self.active_pane))
        bind_key("<Control-v>", lambda e: self._clipboard_paste(self.active_pane))

    def _get_active_pane(self) -> FileListPane:
        """Get the currently active pane"""
        return self.left_pane if self.active_pane == "left" else self.right_pane

    def _get_other_pane(self) -> FileListPane:
        """Get the inactive pane"""
        return self.right_pane if self.active_pane == "left" else self.left_pane

    def _switch_pane(self, event=None):
        """Switch focus between panes"""
        self.active_pane = "right" if self.active_pane == "left" else "left"
        self._get_active_pane().tree.focus_set()
        self._update_pane_indicators()
        self._update_status()
        return "break"

    def _go_parent(self, event=None):
        """Navigate to parent directory"""
        self._get_active_pane().go_parent()
        return "break"

    def _on_path_change(self, pane: str, path: str):
        """Handle path change in a pane"""
        if self._initialized:  # Only save after full initialization
            self._save_config()
            self._update_status()

    def _on_selection_change(self, pane: str, paths: List[str]):
        """Handle selection change"""
        self.active_pane = pane
        self._update_pane_indicators()
        self._update_status()

    def _set_active_pane(self, pane: str):
        """Set the active pane when clicked"""
        self.active_pane = pane
        self._update_pane_indicators()
        self._update_status()

    def _update_pane_indicators(self):
        """Update visual indicators showing which pane is active"""
        # Active pane gets bright border, inactive gets dim border
        active_color = COLORS["accent"]  # Bright cyan
        inactive_color = COLORS["card_bg"]  # Dark blue

        if self.active_pane == "left":
            self.left_pane.configure(border_color=active_color, border_width=3)
            self.right_pane.configure(border_color=inactive_color, border_width=1)
        else:
            self.left_pane.configure(border_color=inactive_color, border_width=1)
            self.right_pane.configure(border_color=active_color, border_width=3)

    def _update_status(self):
        """Update status bar"""
        pane = self._get_active_pane()
        count = pane.get_selected_count()

        # Build status message
        if count == 0:
            items_count = len(pane.items)
            status_msg = f"{items_count} items in {pane.current_path}"
        else:
            size = pane.get_selected_size()
            status_msg = f"{count} items selected ({format_size(size)})"

        # Add clipboard status if items are in clipboard
        if self.clipboard_paths:
            op = "copy" if self.clipboard_operation == "copy" else "cut"
            status_msg += f"  |  Clipboard: {len(self.clipboard_paths)} items ({op})"

        self.status_label.configure(text=status_msg)

    def _goto_bookmark(self, key: str):
        """Go to bookmark"""
        bookmark = self.bookmarks.get(key)
        if bookmark:
            path = bookmark.get("path") if isinstance(bookmark, dict) else bookmark
            if path and os.path.isdir(path):
                self._get_active_pane().navigate_to(path)
                self._log(f"Jumped to {key}: {path}", "info")
            elif path:
                messagebox.showwarning("Bookmark", f"{key} path no longer exists:\n{path}")

    def _set_bookmark(self, key: str):
        """Set bookmark to current directory"""
        pane = self._get_active_pane()
        if isinstance(self.bookmarks.get(key), dict):
            self.bookmarks[key]["path"] = pane.current_path
        else:
            self.bookmarks[key] = {"path": pane.current_path, "name": key}
        self._save_config()
        if key in self.bookmark_buttons:
            self.bookmark_buttons[key].configure(fg_color=COLORS["card_bg"])
        self._log(f"Set {key} to {pane.current_path}", "success")

    def _copy_to_other(self):
        """Copy selected files to other pane"""
        source_pane = self._get_active_pane()
        dest_pane = self._get_other_pane()

        paths = source_pane.get_selected_paths()
        if not paths:
            messagebox.showinfo("Copy", "No files selected.")
            return

        count = len(paths)
        dest = dest_pane.current_path

        if messagebox.askyesno("Confirm Copy",
            f"Copy {count} item(s) to:\n{dest}?"):

            self._log(f"Copying {count} items to {dest}", "info")

            self.op_manager.copy_with_progress(
                paths,
                dest,
                progress_callback=lambda p: self._update_progress(p),
                complete_callback=lambda r: self._operation_complete("Copy", r, dest_pane)
            )

    def _move_to_other(self):
        """Move selected files to other pane"""
        source_pane = self._get_active_pane()
        dest_pane = self._get_other_pane()

        paths = source_pane.get_selected_paths()
        if not paths:
            messagebox.showinfo("Move", "No files selected.")
            return

        count = len(paths)
        dest = dest_pane.current_path

        if messagebox.askyesno("Confirm Move",
            f"Move {count} item(s) to:\n{dest}?"):

            self._log(f"Moving {count} items to {dest}", "info")

            self.op_manager.move_with_progress(
                paths,
                dest,
                progress_callback=lambda p: self._update_progress(p),
                complete_callback=lambda r: self._operation_complete("Move", r, dest_pane, source_pane)
            )

    def _delete_selected(self):
        """Delete selected files"""
        pane = self._get_active_pane()
        paths = pane.get_selected_paths()

        if not paths:
            messagebox.showinfo("Delete", "No files selected.")
            return

        count = len(paths)

        if messagebox.askyesno("Confirm Delete",
            f"Delete {count} item(s) to Recycle Bin?"):

            self._log(f"Deleting {count} items", "warning")

            self.op_manager.delete_with_progress(
                paths,
                use_recycle_bin=True,
                complete_callback=lambda r: self._operation_complete("Delete", r, pane)
            )

    def _update_progress(self, progress: OperationProgress):
        """Update progress in status bar"""
        self.after(0, lambda: self.status_label.configure(
            text=f"{progress.operation.value.capitalize()}: {progress.current_file} ({progress.percent:.0f}%)"
        ))

    def _operation_complete(
        self,
        op_name: str,
        results: List[FileOperationResult],
        *panes_to_refresh
    ):
        """Handle operation completion"""
        success = sum(1 for r in results if r.success)
        failed = len(results) - success

        if failed == 0:
            self._log(f"{op_name} complete: {success} items", "success")
        else:
            self._log(f"{op_name}: {success} succeeded, {failed} failed", "warning")

        # Refresh panes
        self.after(0, lambda: [p.refresh() for p in panes_to_refresh if p])
        self.after(0, self._update_status)

    def _rename_selected(self):
        """Rename selected item"""
        self._get_active_pane()._rename_selected()

    def _new_folder(self):
        """Create new folder"""
        self._get_active_pane()._new_folder()

    def _focus_path_entry(self):
        """Focus the path entry"""
        self._get_active_pane().path_entry.focus_set()
        self._get_active_pane().path_entry.select_range(0, "end")

    def _refresh_both(self):
        """Refresh both panes"""
        self.left_pane.refresh()
        self.right_pane.refresh()
        self._log("Refreshed file lists", "info")

    def _clipboard_copy(self, pane: str):
        """Copy selected files to clipboard"""
        source_pane = self.left_pane if pane == "left" else self.right_pane
        paths = source_pane.get_selected_paths()

        if not paths:
            messagebox.showinfo("Copy", "No files selected.")
            return

        self.clipboard_paths = paths
        self.clipboard_operation = "copy"
        self._log(f"Copied {len(paths)} item(s) to clipboard", "info")
        self._update_status()

    def _clipboard_cut(self, pane: str):
        """Cut selected files to clipboard (for move)"""
        source_pane = self.left_pane if pane == "left" else self.right_pane
        paths = source_pane.get_selected_paths()

        if not paths:
            messagebox.showinfo("Cut", "No files selected.")
            return

        self.clipboard_paths = paths
        self.clipboard_operation = "move"
        self._log(f"Cut {len(paths)} item(s) to clipboard", "info")
        self._update_status()

    def _clipboard_paste(self, pane: str):
        """Paste files from clipboard to specified pane"""
        if not self.clipboard_paths:
            messagebox.showinfo("Paste", "Clipboard is empty. Copy or cut files first.")
            return

        dest_pane = self.left_pane if pane == "left" else self.right_pane
        dest = dest_pane.current_path

        # Determine source pane for refresh after move
        source_pane = None
        if self.clipboard_operation == "move":
            # Find which pane contains the source files
            if self.clipboard_paths[0].startswith(self.left_pane.current_path):
                source_pane = self.left_pane
            elif self.clipboard_paths[0].startswith(self.right_pane.current_path):
                source_pane = self.right_pane

        count = len(self.clipboard_paths)
        op_name = "Copy" if self.clipboard_operation == "copy" else "Move"

        if messagebox.askyesno(f"Confirm {op_name}",
            f"{op_name} {count} item(s) to:\n{dest}?"):

            self._log(f"{op_name}ing {count} items to {dest}", "info")

            if self.clipboard_operation == "copy":
                self.op_manager.copy_with_progress(
                    self.clipboard_paths,
                    dest,
                    progress_callback=lambda p: self._update_progress(p),
                    complete_callback=lambda r: self._operation_complete(op_name, r, dest_pane)
                )
            else:  # move
                self.op_manager.move_with_progress(
                    self.clipboard_paths,
                    dest,
                    progress_callback=lambda p: self._update_progress(p),
                    complete_callback=lambda r: self._operation_complete(op_name, r, dest_pane, source_pane)
                )
                # Clear clipboard after move
                self.clipboard_paths = []
                self.clipboard_operation = None

    def _show_settings(self):
        """Show settings dialog"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("QuickFiles Settings")
        dialog.geometry("500x400")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.grab_set()

        # Title
        ctk.CTkLabel(
            dialog,
            text="QuickFiles Settings",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(pady=20)

        # Bookmarks section
        ctk.CTkLabel(
            dialog,
            text="Bookmarks (Shift+F1-F10 to set):",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text"]
        ).pack(anchor="w", padx=20, pady=(10, 5))

        bookmarks_frame = ctk.CTkScrollableFrame(
            dialog,
            fg_color=COLORS["card_bg"],
            height=200
        )
        bookmarks_frame.pack(fill="x", padx=20, pady=5)

        for i in range(1, 11):
            key = f"F{i}"
            path = self.bookmarks.get(key, "Not set")

            row = ctk.CTkFrame(bookmarks_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row,
                text=f"{key}:",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["accent"],
                width=40
            ).pack(side="left", padx=5)

            ctk.CTkLabel(
                row,
                text=path if path else "Not set",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text"] if path else COLORS["border"],
                anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=5)

        # Keyboard shortcuts
        ctk.CTkLabel(
            dialog,
            text="Keyboard Shortcuts:",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text"]
        ).pack(anchor="w", padx=20, pady=(20, 5))

        shortcuts = [
            "Tab: Switch panes",
            "F1-F10: Go to bookmark",
            "Shift+F1-F10: Set bookmark",
            "F5: Copy to other pane",
            "F6: Move to other pane",
            "F2: Rename",
            "Del: Delete",
            "Ctrl+N: New folder",
            "Ctrl+L: Focus path bar",
            "Backspace: Go to parent",
        ]

        shortcuts_text = "  •  ".join(shortcuts)
        ctk.CTkLabel(
            dialog,
            text=shortcuts_text,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text"],
            wraplength=450
        ).pack(padx=20, pady=5)

        # Close button
        ctk.CTkButton(
            dialog,
            text="Close",
            width=100,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=dialog.destroy
        ).pack(pady=20)
