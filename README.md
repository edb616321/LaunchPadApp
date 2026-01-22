# Command Center LaunchPad (CCL)

A modern, multi-panel command center with application launcher, video player, and dual-pane file manager. Built with CustomTkinter for a clean, vibrant blue interface.

## Current Status: IN DEVELOPMENT

**Last Updated:** 2026-01-22

### Working Features
- Application launcher with large icons (200x200px cards)
- Multi-monitor app launching (M2, M3, M4 buttons)
- QuickPlayer video/audio player with MPV backend
- QuickFiles dual-pane file manager
- Named bookmark buttons (D:, Home, LaunchPad, etc.)
- File list with Name, Size, Created, Modified columns
- Right-click context menu with file operations
- System volume control in header

### Known Issues / In Progress
- **Search filtering**: Code implemented but may have UI responsiveness issues
- **MPV threading warning**: Non-critical "main thread is not in main loop" warning appears
- **Window handle exhaustion**: Can occur if app crashes repeatedly without cleanup

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

### QuickPlayer (Video/Audio Player)

- **Drag-and-drop** video/audio files
- **Supported formats**: MP4, AVI, MKV, MOV, WMV, WebM, MP3, WAV, FLAC, etc.
- **Playback controls**: Play/Pause, Seek, Volume
- **40pt title font** for readability

### QuickFiles (Dual-Pane File Manager)

- **Dual panes** for easy file operations
- **Named bookmarks**: D:, Home, LaunchPad, QuickTube, F:, Downloads, Desktop, Documents
- **File columns**: Name, Size (right-aligned), Created, Modified (centered)
- **Human-readable dates**: "Today 2:30 PM", "Yesterday", "Sun 19th", "Jan 5th, 2024"
- **Search/filter**: Type patterns like `*.mp3`, `*.txt`, `file.*`, `*.doc?`
- **Right-click menu**:
  - Open / Open in Explorer
  - Play in QuickPlayer (for media files)
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
├── launcher.py           # Main application (~1400 lines)
├── quickfiles.py         # Dual-pane file manager (~1200 lines)
├── quickplayer.py        # Video player widget (~350 lines)
├── file_operations.py    # File copy/move/delete operations
├── apps.json             # User's app shortcuts
├── quickfiles.json       # File manager bookmarks & settings
└── README.md             # This file
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

**v2.0** (2026-01-22) - Current
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
- **Video**: python-mpv (libmpv wrapper)
- **Monitor Detection**: screeninfo (characteristic-based, not index-based)
- **Window Positioning**: pygetwindow with retry logic
- **File Operations**: shutil with threading
- **Data Storage**: JSON format

## Known Limitations

1. Search is folder-local only (no recursive search yet)
2. MPV requires separate installation
3. Some apps resist window positioning
4. Drag-and-drop between panes not yet implemented

---

**Command Center LaunchPad** - Your multi-monitor productivity hub
