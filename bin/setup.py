import ctypes
import io
import os
import sys
import time
import traceback
import urllib.request
import winreg
import zipfile


def is_admin():
    """Check if the script is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


APP_NAME = os.environ.get("APP_NAME", "PeerConnect")
ZIP_FILE_NAME = f"{APP_NAME}.zip"

GITHUB_REPO_DOWNLOAD_URL = (
    f"https://github.com/ShaikAli65/{APP_NAME}/releases/latest/download/{ZIP_FILE_NAME}"
)


def format_size(size_bytes):
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def download_zip(url):
    """Download ZIP file with progress display"""
    print(f"Downloading ZIP file from: {url}")
    try:
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            start_time = time.time()
            chunk_size = 16 * 1024  # 16KB
            data = []

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                data.append(chunk)
                downloaded += len(chunk)

                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                percent = (downloaded / total_size) * 100 if total_size > 0 else 0

                # Progress bar
                if total_size > 0:
                    bar_length = 40
                    filled = int(bar_length * downloaded // total_size)
                    bar = '█' * filled + '-' * (bar_length - filled)
                    sys.stdout.write(
                        f"\r[{bar}] {percent:.1f}% "
                        f"{format_size(downloaded)}/{format_size(total_size)} "
                        f"({format_size(speed)}/s)"
                    )
                else:
                    sys.stdout.write(f"\rDownloaded {format_size(downloaded)}")

                sys.stdout.flush()

            print("\nDownload completed successfully.")
            return b''.join(data)

    except Exception as e:
        raise Exception(f"Error downloading ZIP file: {e}")


def extract_zip(zip_content, target_directory):
    """Extract ZIP file with progress display"""
    print(f"\nExtracting files to: {target_directory}")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
            members = zip_ref.namelist()
            total_files = len(members)
            max_name_length = max(len(name) for name in members) if members else 0

            for i, member in enumerate(members, 1):
                zip_ref.extract(member, target_directory)
                display_name = member if len(member) <= 30 else f"...{member[-27:]}"
                sys.stdout.write(
                    f"\rExtracting [{i}/{total_files}] "
                    f"{display_name.ljust(30)} "
                    f"({i / total_files * 100:.1f}%)"
                )
                sys.stdout.flush()

            print("\nExtraction completed successfully.")

    except Exception as e:
        raise Exception(f"Error extracting ZIP file: {e}")


def register_application(app_name, app_path, version="1.0", publisher="PeerConnect"):
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\\" + app_name
    try:
        with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, app_name)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, publisher)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, app_path)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f"{app_path}\\uninstall.exe")
            print("Application registered successfully.")
    except Exception as e:
        print(f"Failed to register application: {e}")


def add_to_path(app_dir):
    """Add application directory to the Windows PATH environment variable."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Environment",
                            0, winreg.KEY_ALL_ACCESS) as key:
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""

            if app_dir not in current_path.split(';'):
                new_path = f"{current_path};{app_dir}" if current_path else app_dir
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                print(f"Added {app_dir} to PATH")

                # Notify system about the environment variable change
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x1A
                SMTO_ABORTIFHUNG = 0x0002
                result = ctypes.c_long()
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment',
                    SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
            else:
                print(f"{app_dir} is already in the PATH variable.")
    except PermissionError:
        print("Permission denied: Unable to access the registry. "
              "Try running this script as an Administrator.")
    except Exception as e:
        print(f"An error occurred: {e}")


def create_data_folder():
    """Create a 'data' folder in the user's local AppData directory."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise Exception("LOCALAPPDATA environment variable not found.")

    data_folder = os.path.join(local_appdata, APP_NAME)
    if not os.path.exists(data_folder):
        os.makedirs(data_folder)
        print(f"Created data folder: {data_folder}")
    else:
        print(f"Data folder already exists: {data_folder}")
    return data_folder


def add_to_search_reg(exe_name, exe_path, install_dir):
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\{}".format(exe_name)
    try:
        # Create or update the registry key
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
            # Set the default value to the full path of the executable
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, exe_path)
            # Optional: Add the directory to the PATH when the app runs
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, install_dir)
        print(f"Added registry entry for {exe_name}.")
    except Exception as e:
        print(f"Failed to update registry: {str(e)}")


def main():
    if not is_admin():
        print("Requesting administrator privileges...")
        # Relaunch the script with admin rights
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()

    zip_content = download_zip(GITHUB_REPO_DOWNLOAD_URL)

    program_files = os.environ.get("ProgramFiles")
    if not program_files:
        raise Exception("ProgramFiles environment variable not found.")

    app_install_dir = os.path.join(program_files)
    if not os.path.exists(app_install_dir):
        os.makedirs(app_install_dir)
        print(f"Created installation directory: {app_install_dir}")
    else:
        print(f"Installation directory already exists: {app_install_dir}")

    extract_zip(zip_content, app_install_dir)
    app_dir = fr"{app_install_dir}\{APP_NAME}"

    register_application(APP_NAME, app_dir)
    add_to_path(app_dir)
    add_to_search_reg(APP_NAME, os.path.join(app_dir, f'{APP_NAME}.exe'), app_dir)
    create_data_folder()

    print("Setup completed successfully.")


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
    input("press enter to exit")
