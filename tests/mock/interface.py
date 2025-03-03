from src.avails.connect import IPAddress
from src.conduit import webpage
from src.configurations import interfaces
from src.managers import profilemanager


def mock_interface_selector():
    async def mock_selector(_interfaces):

        for i, inter in _interfaces.items():
            if 'wi' in inter.friendly_name.lower():
                return i

        return i

    webpage.ask_for_interface_choice = mock_selector


def mock_interfaces(config):
    def get_interfaces() -> list[IPAddress]:
        return [profilemanager.get_current_profile().interface]

    if config.test_mode == "local":
        return

    interfaces.get_interfaces = get_interfaces
