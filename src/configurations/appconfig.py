from dataclasses import dataclass

from src.managers import ProfileManager


@dataclass
class Versions:
    Global: str
    RemotePeer: str
    FileObject: str
    DirectoryObject: str
    WireProto: str


@dataclass
class AppConfig:
    ip_version: int
    protocol: str
    this_port: int
    req_port: int
    page_port: int
    page_serve_port: int
    version: Versions
    profiles: list[ProfileManager]
    selected_profile: ProfileManager
