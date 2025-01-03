import os
import platform
import subprocess
from abc import ABC, abstractmethod

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = False
    filedialog = False
tk = False
import src.avails.constants as const


class IDialogs(ABC):
    @classmethod
    @abstractmethod
    def open_file_dialog_window(cls) -> list[str]: ...

    @classmethod
    @abstractmethod
    def open_directory_dialog_window(cls) -> str: ...


class TkDialogs(IDialogs):
    recent_dir = const.PATH_DOWNLOAD
    __slots__ = ()

    @classmethod
    def open_file_dialog_window(cls):
        """
        Opens the system-like file picker dialog using Tkinter.
        """
        # root = tk.Tk()
        # root.withdraw()  # Hide the root window
        files = filedialog.askopenfilenames(initialdir=cls.recent_dir, title="Select files to send")
        if files:
            cls.recent_dir = os.path.dirname(files[0])
        return list(files)

    @classmethod
    def open_directory_dialog_window(cls):
        """
        Opens the directory picker dialog using Tkinter.
        """
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        directory = filedialog.askdirectory(initialdir=cls.recent_dir, title="Select directory to send")
        if directory:
            cls.recent_dir = directory
        return directory


class FileExplorerDialog(IDialogs):
    recent_dir = const.PATH_DOWNLOAD

    @classmethod
    def open_file_dialog_window(cls):
        """
        Uses a subprocess to invoke the system file picker. Platform-specific.
        """
        if platform.system() == "Windows":
            command = [
                "powershell", "-Command",
                "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') > $null;"
                "$fileBrowser = New-Object System.Windows.Forms.OpenFileDialog;"
                f"$fileBrowser.InitialDirectory = '{cls.recent_dir}';" +
                "$fileBrowser.Multiselect = $true;"
                "$fileBrowser.Filter = 'All files (*.*)|*.*';"
                "if ($fileBrowser.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {"
                "    $fileBrowser.FileNames -join '\n'"
                "}"
            ]
            result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
            files = result.stdout.strip().split("\n") if result.returncode == 0 else []
            if files:
                cls.recent_dir = os.path.dirname(files[0])
            return files

        elif const.IS_DARWIN:  # macOS
            command = ['osascript', '-e',
                       f'tell application "System Events" to choose file with multiple selections allowed']
            result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
            files = result.stdout.strip().split(", ") if result.returncode == 0 else []
        else:  # Linux
            # Requires zenity (or similar tool) installed
            command = ['zenity', '--file-selection', '--multiple', '--separator="\n"',
                       '--title="Select files"', '--filename=' + cls.recent_dir + '/']
            result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
            files = result.stdout.strip().split("\n") if result.returncode == 0 else []
        if files:
            cls.recent_dir = os.path.dirname(files[0])
        return files

    @classmethod
    def open_directory_dialog_window(cls):
        """
        Uses a subprocess to invoke the system directory picker. Platform-specific.
        """
        if const.IS_WINDOWS:
            command = ["powershell", "-Command",
                       f'[System.Reflection.Assembly]::LoadWithPartialName("System.windows.forms");'
                       f'$folderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog;'
                       f'$folderBrowser.SelectedPath = "{cls.recent_dir}";'
                       f'$folderBrowser.ShowDialog() | Out-Null;'
                       f'$folderBrowser.SelectedPath']
            result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
            directory = result.stdout.strip() if result.returncode == 0 else ""
        elif const.IS_DARWIN:  # macOS
            command = ['osascript', '-e',
                       f'tell application "System Events" to choose folder']
            result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
            directory = result.stdout.strip() if result.returncode == 0 else ""
        else:  # Linux
            # Requires zenity (or similar tool) installed
            command = ['zenity', '--file-selection', '--directory',
                       '--title="Select directory"', '--filename=' + cls.recent_dir + '/']
            result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
            directory = result.stdout.strip() if result.returncode == 0 else ""
        if directory:
            cls.recent_dir = directory
        return directory


def get_dialog_handler() -> IDialogs:
    if tk:
        return TkDialogs()
    return FileExplorerDialog()
