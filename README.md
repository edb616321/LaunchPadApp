# Command Center LaunchPad (CCL)

A modern, multi-panel command center with application launcher, video player, and dual-pane file manager. Built with CustomTkinter for a clean, vibrant blue interface.

## Current Status: PRODUCTION

**Last Updated:** 2026-02-16

### Working Features
- Application launcher with large icons (200x200px cards)
- Multi-monitor app launching (M2, M3, M4 buttons)
- QuickPlayer video/audio/image player with MPV backend
- QuickFiles dual-pane file manager with thumbnail view
- Named bookmark buttons (D:, Home, LaunchPad, etc.)
- File list with Name, Size, Created, Modified columns
- Thumbnail view with grid display (50 item limit for performance)
- Real Windows thumbnails via IShellItemImageFactory COM API
- Right-click context menu with file operations
- System volume control in header
- Image controls: Fit to Window, Actual Size, Zoom slider (10-400%)
- Scrollbars for zoomed images
- QuickImage features: Convert Format, Resize, Adjust Quality
- Edit in QuickDrop integration
- Resizable dual-pane panels with active pane tracking
- Recursive search with blinking indicator

### QuickPlayer Audio Engine (2026-02-16)
- **Dual-player architecture**: Separate MPV instances for audio (vo=null) and video (vo=gpu)
- **High-quality pipeline**: 48kHz/float32/stereo, WASAPI, 1s buffer, gapless playback
- **Polling-based UI updates**: No property observers (eliminates GIL contention crackling)
- **Process priority**: ABOVE_NORMAL for audio thread scheduling
- **10-band EQ via Equalizer APO**: System-level WASAPI EQ (±20dB range, real-time config file updates)
- **Skip buttons**: ⏪ -15s / ⏩ +30s (keyboard: Left/Right, Shift for ±30s)
- **Mouse wheel volume**: Scroll on player area = player volume, scroll on CCL = system volume
- **Pop-out fullscreen player**: Same audio quality, auto-hide controls, keyboard shortcuts

### Panel Default Sizes
- Quick Links: 20% (600px)
- QuickPlayer: 40% (1200px)
- QuickFiles Left: 30%
- QuickFiles Right: 10%

### Known Issues / In Progress
- **Equalizer APO requires reboot**: Installed at `D:\EqualizerAPO\`, needs one reboot to activate the driver-level audio hook. After that, EQ presets work instantly.
- **MPV af filters broken**: This mpv.net build (v0.37.0) accepts `af` property changes but never applies them to the audio pipeline. EQ is handled by Equalizer APO instead.
- **Large folder thumbnails**: Limited to 50 items to prevent UI freezing

## Overview

Command Center LaunchPad is a visual command center that lives on your ultra-wide monitor (Monitor 1) and provides:
- **Quick Links**: Application launcher grid
- **QuickPlayer**: Video/audio player with drag-and-drop
- **QuickFiles**: Dual-pane file manager

## Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│                    COMMAND CENTER LAUNCHPAD                            │
│  [M2] [M3] [M4]                              [Volume] [Date/Time]      │
├──────────────┬──────────────┬──────────────────────────────────────────┤
│  QUICK LINKS │  QUICKPLAYER │           QUICKFILES                     │
│              │              │  [D:][Home][LaunchPad][Downloads]...     │
│  [App1]      │  🎬 Video    │  ┌─────────────┬─────────────┐           │
│  [App2]      │   Player     │  │ LEFT PANE   │ RIGHT PANE  │           │
│  [App3]      │              │  │ 📁 FOLDER:  │ 📁 FOLDER:  │           │
│  [App4]      │  [Controls]  │  │ 🔎 SEARCH:  │ 🔎 SEARCH:  │           │
│  ...         │              │  │ [files...]  │ [files...]  │           │
│              │              │  └─────────────┴─────────────┘           │
│              │              │  [Copy F5] [Move F6] [Delete] [New]      │
└──────────────┴──────────────┴──────────────────────────────────────────┘
```

## Installation

### Requirements

- Python 3.10 or higher
- Windows OS
- mpv.net (for video playback)

### Setup

```powershell
# Install Python packages
pip install customtkinter screeninfo pygetwindow Pillow pywin32 requests mutagen pycaw comtypes

# Navigate to app directory
cd D:\LaunchPadApp

# Run the launcher
python launcher.py
```

### Optional: MPV for Video Playback

1. Install mpv.net from: https://github.com/mpv-player/mpv/releases
2. Default path: `C:\Users\<username>\AppData\Local\Programs\mpv.net`

## Features

### Quick Links (Application Launcher)

- **200x200px app cards** with 24pt font names
- **Double-click to launch** (Windows-style)
- **Monitor targeting**: Click M2/M3/M4 then click app
- **Right-click menu**: Edit, Duplicate, Delete
- **Categories**: Web, Development, Tools, Productivity, Media, Games

### QuickPlayer (Video/Audio/Image Player)

- **Drag-and-drop** video/audio/image files
- **Supported formats**: MP4, AVI, MKV, MOV, WMV, WebM, MP3, WAV, FLAC, PNG, JPG, GIF, etc.
- **Dual-player audio engine**: Separate MPV instance for audio files (vo=null, zero GPU/Tk interaction) eliminates crackling. Video files use GPU-embedded player.
- **High-quality audio**: 48kHz sample rate, 32-bit float, stereo, WASAPI, 1s buffer, gapless playback, ReplayGain album normalization
- **Playback controls**: Play/Pause, Stop, ⏪ Skip Back (-15s), ⏩ Skip Forward (+30s), Seek slider, Volume (0-150%)
- **10-band Equalizer**: Powered by Equalizer APO (system-level WASAPI). ±20dB range. Presets: Flat, Warm, Bass+, Treble+, Vocal
- **Mouse wheel volume**: Scroll on player area adjusts player volume (±5%), scroll elsewhere on CCL adjusts system volume (±2%)
- **Keyboard shortcuts**: Space (play/pause), Left/Right (seek ±15s/30s), Shift+Left/Right (±30s), Up/Down (volume), M (mute)
- **Pop-out fullscreen**: Full keyboard/mouse control, auto-hiding controls, resumes position on close
- **Image controls** (top bar):
  - Fit to Window: Scale image to fit display
  - Actual Size: Show image at 100% zoom
  - Zoom slider: 10% to 400%
  - Mousewheel zoom support
- **Scrollbars** for panning zoomed images
- **External open support**: TCP listener on port 51478 for "Open with" integration

### QuickFiles (Dual-Pane File Manager)

- **Dual panes** for easy file operations
- **Named bookmarks**: D:, Home, LaunchPad, QuickTube, F:, Downloads, Desktop, Documents
- **File columns**: Name, Size (right-aligned), Created, Modified (centered)
- **Human-readable dates**: "Today 2:30 PM", "Yesterday", "Sun 19th", "Jan 5th, 2024"
- **View modes**: List view or Thumbnail view (toggle button)
- **Thumbnail view**: Grid of image previews with 50 item limit for performance
- **Search/filter**: Type patterns like `*.mp3`, `*.txt`, `file.*`, `*.doc?`
- **Right-click menu**:
  - Open / Open in Explorer
  - Play in QuickPlayer (for media files)
  - Edit in QuickDrop (for images)
  - QuickImage submenu (for images):
    - Convert Format (PNG, JPEG, WebP, BMP, GIF, TIFF)
    - Resize Image (with presets)
    - Adjust Quality (1-100%)
  - Refresh
  - Copy / Cut / Paste
  - Rename / Delete
  - New Folder
  - Properties

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F5 | Copy selected files to other pane |
| F6 | Move selected files to other pane |
| Tab | Switch between panes |
| Backspace | Go to parent directory |
| Enter | Open selected file/folder |
| Double-click | Open file/folder |

## File Structure

```
D:\LaunchPadApp\
├── launcher.py           # Main application (~1500 lines)
├── quickfiles.py         # Dual-pane file manager with thumbnails (~1800 lines)
├── quickplayer.py        # Dual-player media widget (~1700 lines)
├── file_operations.py    # File copy/move/delete operations
├── apps.json             # User's app shortcuts
├── quickfiles.json       # File manager bookmarks & settings
├── shell_thumbs/         # Disk cache for IShellItemImageFactory thumbnails
├── video_thumbs/         # Disk cache for FFmpeg video thumbnails
├── audio_diag.py         # Audio diagnostic test script
├── audio_test.py         # A/B audio config test script
└── README.md             # This file

D:\EqualizerAPO\           # System-level audio EQ (requires reboot to activate)
├── config/
│   ├── config.txt         # Main config (includes quickplayer_eq.txt)
│   └── quickplayer_eq.txt # Written by QuickPlayer EQ panel in real-time
└── ...
```

## Configuration Files

### apps.json
```json
{
  "apps": [
    {
      "name": "Chrome",
      "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "category": "Web",
      "monitor": 0,
      "args": []
    }
  ]
}
```

### quickfiles.json
```json
{
  "bookmarks": {
    "D:": {"path": "D:\\", "name": "D:"},
    "Home": {"path": "C:\\Users\\username", "name": "Home"}
  },
  "left_pane": {"path": "D:\\"},
  "right_pane": {"path": "F:\\"}
}
```

## Theme Colors

Vibrant blue theme:
```python
COLORS = {
    "bg_dark": "#001A4D",      # Deep navy background
    "card_bg": "#0047AB",      # Cobalt blue cards
    "card_hover": "#0066FF",   # Bright blue hover
    "text": "#FFFFFF",         # White text
    "accent": "#00BFFF",       # Sky blue accents
    "accent_hover": "#1E90FF", # Dodger blue hover
}
```

## Monitor Configuration

- **Monitor 1** (Ultra-wide 5120x1440): CCL stays here
- **M2**: Left workspace (identified by X < -3000)
- **M3**: Top-front workspace (1920x1080 at 0,0) - DEFAULT
- **M4**: Right workspace (identified by X > 3000)

## Troubleshooting

### Search not filtering files
- Search filters the **current folder only** (not recursive)
- Make sure you're in a folder that has matching files
- Check console for `[SEARCH TRIGGERED]` messages

### MPV warning "main thread is not in main loop"
- This is a non-critical threading warning
- Video playback still works
- Can be ignored

### Window positioning fails
- Some apps don't support automated positioning
- 3-second delay allows app to load before moving
- Check console for positioning debug messages

### App won't launch
- Verify the path is correct (use Browse button)
- For apps with arguments, use the `args` array in apps.json

## Version History

**v3.0** (2026-02-16) - Current
- **Dual-player audio architecture**: Separate MPV instances for audio (vo=null) and video (vo=gpu) - eliminates all crackling/popping
- **High-quality audio pipeline**: 48kHz/float32/stereo, WASAPI, 1s buffer, gapless, ReplayGain
- **Equalizer APO integration**: 10-band graphic EQ via system-level WASAPI driver (±20dB, real-time)
- **Polling-based UI**: Replaced MPV property observers with 1s polling timer (eliminates GIL contention)
- **Skip buttons**: ⏪ -15s / ⏩ +30s on both embedded and pop-out players
- **Mouse wheel volume**: Player area = player volume, CCL background = system volume
- **Keyboard shortcuts**: Space, Left/Right, Shift+Left/Right, Up/Down, M (mute)
- **Pop-out player improvements**: Skip buttons, mouse wheel volume, matching seek times
- **QuickFiles thumbnail fix**: Text no longer cut off in Large view
- **Process priority**: ABOVE_NORMAL for better audio scheduling
- **EQ presets**: Flat, Warm, Bass+, Treble+, Vocal (headphone-tuned)

**v2.1** (2026-01-24)
- Added thumbnail view to QuickFiles with 50 item limit
- Added image controls to QuickPlayer (Fit to Window, Actual Size, Zoom 10-400%)
- Added scrollbars for panning zoomed images
- Added mousewheel zoom support
- Added QuickImage features: Convert Format, Resize, Adjust Quality
- Added Edit in QuickDrop integration
- Fixed right-click context menu in thumbnail view
- Optimized panel default sizes (20%/40%/30%/10%)

**v2.0** (2026-01-22)
- Added QuickFiles dual-pane file manager
- Added QuickPlayer video/audio player
- Added search filtering with wildcard patterns
- Added named bookmark buttons
- Increased all fonts to 20-26pt for readability
- Added Size, Created, Modified columns
- Added human-readable date formatting
- Added right-click context menu with file operations
- Added Play in QuickPlayer option for media files

**v1.5** (2025-11-12)
- Added system volume control slider
- Added command-line arguments support for apps
- Fixed Thorium browser multiple windows issue

**v1.0** (2025-10-27)
- Initial release
- Multi-monitor support
- Application launcher
- Category organization

## Technical Details

- **Framework**: CustomTkinter + ttk.Treeview
- **Audio/Video**: python-mpv (libmpv v0.37.0 from mpv.net)
- **Audio EQ**: Equalizer APO v1.4.2 (system-level WASAPI filter)
- **Thumbnails**: IShellItemImageFactory COM API with 6-thread pool + disk cache
- **Monitor Detection**: screeninfo (characteristic-based, not index-based)
- **Window Positioning**: pygetwindow with retry logic
- **File Operations**: shutil with threading
- **Data Storage**: JSON format

## Known Limitations

1. Equalizer APO requires a one-time reboot after installation to activate
2. MPV's `af` audio filter property is broken in mpv.net v0.37.0 (accepts but doesn't apply)
3. MPV requires separate installation (mpv.net)
4. Some apps resist window positioning
5. Thumbnail view limited to 50 items for performance (large folders show partial)
6. EQ is system-wide (Equalizer APO affects all audio, not just QuickPlayer)

---

**Command Center LaunchPad** - Your multi-monitor productivity hub
