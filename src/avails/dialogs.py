import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog

import constants as const


class Dialog:
    recent_dir = const.PATH_DOWNLOAD

    @classmethod
    def open_file_dialog_window(cls):
        """
        Opens the system-like file picker dialog.
        """
        _ = QApplication([])
        dialog = QFileDialog()
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setWindowFlags(Qt.WindowStaysOnTopHint | dialog.windowFlags())
        files = dialog.getOpenFileNames(directory=cls.recent_dir,
                                        caption="Select files to send")[0]
        cls.recent_dir = os.path.dirname(files[0])
        return files

    @classmethod
    def open_directory_dialog_window(cls):
        _ = QApplication([])
        dialog = QFileDialog()
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setWindowFlags(Qt.WindowStaysOnTopHint | dialog.windowFlags())
        directory = dialog.getExistingDirectory(directory=cls.recent_dir, caption="Select directory to send")
        cls.recent_dir = directory
        return directory
