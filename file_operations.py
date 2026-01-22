"""
File Operations Module for QuickFiles
Provides threaded file copy, move, delete with progress callbacks
"""

import os
import shutil
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time


class OperationType(Enum):
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"


@dataclass
class FileOperationResult:
    """Result of a file operation"""
    success: bool
    source: str
    destination: Optional[str]
    error: Optional[str] = None
    bytes_transferred: int = 0


@dataclass
class OperationProgress:
    """Progress information for file operations"""
    current_file: str
    current_index: int
    total_files: int
    bytes_done: int
    bytes_total: int
    percent: float
    operation: OperationType


class FileOperationManager:
    """Manages file operations with progress reporting"""

    def __init__(self):
        self.cancelled = False
        self._lock = threading.Lock()

    def cancel(self):
        """Cancel ongoing operation"""
        with self._lock:
            self.cancelled = True

    def is_cancelled(self) -> bool:
        """Check if operation was cancelled"""
        with self._lock:
            return self.cancelled

    def reset(self):
        """Reset cancelled state"""
        with self._lock:
            self.cancelled = False

    def get_total_size(self, paths: List[str]) -> int:
        """Calculate total size of files to operate on"""
        total = 0
        for path in paths:
            if os.path.isfile(path):
                total += os.path.getsize(path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for f in files:
                        try:
                            total += os.path.getsize(os.path.join(root, f))
                        except (OSError, PermissionError):
                            pass
        return total

    def copy_with_progress(
        self,
        sources: List[str],
        destination: str,
        progress_callback: Optional[Callable[[OperationProgress], None]] = None,
        complete_callback: Optional[Callable[[List[FileOperationResult]], None]] = None
    ):
        """Copy files/folders with progress reporting (runs in thread)"""
        thread = threading.Thread(
            target=self._copy_worker,
            args=(sources, destination, progress_callback, complete_callback),
            daemon=True
        )
        thread.start()
        return thread

    def _copy_worker(
        self,
        sources: List[str],
        destination: str,
        progress_callback: Optional[Callable[[OperationProgress], None]],
        complete_callback: Optional[Callable[[List[FileOperationResult]], None]]
    ):
        """Worker thread for copy operation"""
        self.reset()
        results = []
        total_bytes = self.get_total_size(sources)
        bytes_done = 0

        for idx, source in enumerate(sources):
            if self.is_cancelled():
                results.append(FileOperationResult(
                    success=False, source=source, destination=None,
                    error="Operation cancelled"
                ))
                continue

            try:
                source_path = Path(source)
                dest_path = Path(destination) / source_path.name

                # Handle name conflicts
                dest_path = self._get_unique_path(dest_path)

                if source_path.is_file():
                    # Copy file with progress
                    bytes_copied = self._copy_file_with_progress(
                        source, str(dest_path),
                        lambda b: self._report_progress(
                            progress_callback, source_path.name,
                            idx, len(sources), bytes_done + b, total_bytes,
                            OperationType.COPY
                        )
                    )
                    bytes_done += bytes_copied
                    results.append(FileOperationResult(
                        success=True, source=source, destination=str(dest_path),
                        bytes_transferred=bytes_copied
                    ))
                else:
                    # Copy directory
                    bytes_copied = self._copy_dir_with_progress(
                        source, str(dest_path), idx, len(sources),
                        bytes_done, total_bytes, progress_callback
                    )
                    bytes_done += bytes_copied
                    results.append(FileOperationResult(
                        success=True, source=source, destination=str(dest_path),
                        bytes_transferred=bytes_copied
                    ))

            except Exception as e:
                results.append(FileOperationResult(
                    success=False, source=source, destination=None,
                    error=str(e)
                ))

        if complete_callback:
            complete_callback(results)

    def _copy_file_with_progress(
        self,
        source: str,
        destination: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1024 * 1024  # 1MB chunks
    ) -> int:
        """Copy a single file with progress reporting"""
        bytes_copied = 0

        with open(source, 'rb') as src:
            with open(destination, 'wb') as dst:
                while True:
                    if self.is_cancelled():
                        break

                    chunk = src.read(chunk_size)
                    if not chunk:
                        break

                    dst.write(chunk)
                    bytes_copied += len(chunk)

                    if progress_callback:
                        progress_callback(bytes_copied)

        # Copy file metadata
        shutil.copystat(source, destination)
        return bytes_copied

    def _copy_dir_with_progress(
        self,
        source: str,
        destination: str,
        current_idx: int,
        total_files: int,
        bytes_offset: int,
        total_bytes: int,
        progress_callback: Optional[Callable[[OperationProgress], None]]
    ) -> int:
        """Copy a directory recursively with progress"""
        os.makedirs(destination, exist_ok=True)
        bytes_copied = 0

        for item in os.listdir(source):
            if self.is_cancelled():
                break

            src_item = os.path.join(source, item)
            dst_item = os.path.join(destination, item)

            if os.path.isfile(src_item):
                file_bytes = self._copy_file_with_progress(
                    src_item, dst_item,
                    lambda b: self._report_progress(
                        progress_callback, item,
                        current_idx, total_files,
                        bytes_offset + bytes_copied + b, total_bytes,
                        OperationType.COPY
                    )
                )
                bytes_copied += file_bytes
            else:
                dir_bytes = self._copy_dir_with_progress(
                    src_item, dst_item, current_idx, total_files,
                    bytes_offset + bytes_copied, total_bytes, progress_callback
                )
                bytes_copied += dir_bytes

        return bytes_copied

    def move_with_progress(
        self,
        sources: List[str],
        destination: str,
        progress_callback: Optional[Callable[[OperationProgress], None]] = None,
        complete_callback: Optional[Callable[[List[FileOperationResult]], None]] = None
    ):
        """Move files/folders with progress reporting (runs in thread)"""
        thread = threading.Thread(
            target=self._move_worker,
            args=(sources, destination, progress_callback, complete_callback),
            daemon=True
        )
        thread.start()
        return thread

    def _move_worker(
        self,
        sources: List[str],
        destination: str,
        progress_callback: Optional[Callable[[OperationProgress], None]],
        complete_callback: Optional[Callable[[List[FileOperationResult]], None]]
    ):
        """Worker thread for move operation"""
        self.reset()
        results = []

        # Check if same drive - can use fast rename
        dest_drive = os.path.splitdrive(destination)[0].upper()

        for idx, source in enumerate(sources):
            if self.is_cancelled():
                results.append(FileOperationResult(
                    success=False, source=source, destination=None,
                    error="Operation cancelled"
                ))
                continue

            try:
                source_path = Path(source)
                source_drive = os.path.splitdrive(source)[0].upper()
                dest_path = Path(destination) / source_path.name

                # Handle name conflicts
                dest_path = self._get_unique_path(dest_path)

                # Report progress
                self._report_progress(
                    progress_callback, source_path.name,
                    idx, len(sources), idx, len(sources),
                    OperationType.MOVE
                )

                if source_drive == dest_drive:
                    # Same drive - fast rename
                    shutil.move(source, str(dest_path))
                else:
                    # Different drives - copy then delete
                    if source_path.is_file():
                        shutil.copy2(source, str(dest_path))
                    else:
                        shutil.copytree(source, str(dest_path))

                    # Delete source after successful copy
                    if source_path.is_file():
                        os.remove(source)
                    else:
                        shutil.rmtree(source)

                results.append(FileOperationResult(
                    success=True, source=source, destination=str(dest_path)
                ))

            except Exception as e:
                results.append(FileOperationResult(
                    success=False, source=source, destination=None,
                    error=str(e)
                ))

        if complete_callback:
            complete_callback(results)

    def delete_with_progress(
        self,
        sources: List[str],
        use_recycle_bin: bool = True,
        progress_callback: Optional[Callable[[OperationProgress], None]] = None,
        complete_callback: Optional[Callable[[List[FileOperationResult]], None]] = None
    ):
        """Delete files/folders with progress reporting (runs in thread)"""
        thread = threading.Thread(
            target=self._delete_worker,
            args=(sources, use_recycle_bin, progress_callback, complete_callback),
            daemon=True
        )
        thread.start()
        return thread

    def _delete_worker(
        self,
        sources: List[str],
        use_recycle_bin: bool,
        progress_callback: Optional[Callable[[OperationProgress], None]],
        complete_callback: Optional[Callable[[List[FileOperationResult]], None]]
    ):
        """Worker thread for delete operation"""
        self.reset()
        results = []

        for idx, source in enumerate(sources):
            if self.is_cancelled():
                results.append(FileOperationResult(
                    success=False, source=source, destination=None,
                    error="Operation cancelled"
                ))
                continue

            try:
                source_path = Path(source)

                # Report progress
                self._report_progress(
                    progress_callback, source_path.name,
                    idx, len(sources), idx, len(sources),
                    OperationType.DELETE
                )

                if use_recycle_bin:
                    # Use Windows recycle bin via send2trash or shell
                    self._delete_to_recycle_bin(source)
                else:
                    # Permanent delete
                    if source_path.is_file():
                        os.remove(source)
                    else:
                        shutil.rmtree(source)

                results.append(FileOperationResult(
                    success=True, source=source, destination=None
                ))

            except Exception as e:
                results.append(FileOperationResult(
                    success=False, source=source, destination=None,
                    error=str(e)
                ))

        if complete_callback:
            complete_callback(results)

    def _delete_to_recycle_bin(self, path: str):
        """Delete file/folder to Windows recycle bin"""
        try:
            # Try using pywin32 if available
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            folder = shell.Namespace(0)  # Desktop namespace

            # Use SHFileOperation via ctypes for recycle bin
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", ctypes.c_uint),
                    ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_uint),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p),
                ]

            FO_DELETE = 0x0003
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT = 0x0004

            fileop = SHFILEOPSTRUCT()
            fileop.wFunc = FO_DELETE
            fileop.pFrom = path + '\0'
            fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
            if result != 0:
                raise OSError(f"SHFileOperation failed with code {result}")

        except ImportError:
            # Fallback: permanent delete
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)

    def _get_unique_path(self, path: Path) -> Path:
        """Get a unique path if file already exists"""
        if not path.exists():
            return path

        base = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1

        while True:
            new_name = f"{base} ({counter}){suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def _report_progress(
        self,
        callback: Optional[Callable[[OperationProgress], None]],
        current_file: str,
        current_idx: int,
        total_files: int,
        bytes_done: int,
        bytes_total: int,
        operation: OperationType
    ):
        """Report progress to callback"""
        if callback:
            percent = (bytes_done / bytes_total * 100) if bytes_total > 0 else 0
            callback(OperationProgress(
                current_file=current_file,
                current_index=current_idx,
                total_files=total_files,
                bytes_done=bytes_done,
                bytes_total=bytes_total,
                percent=percent,
                operation=operation
            ))


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_date(timestamp: float) -> str:
    """Format timestamp to readable date"""
    from datetime import datetime
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")
