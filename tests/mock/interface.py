from src.avails.connect import IPAddress
from src.conduit import webpage
from src.configurations import interfaces
from src.managers import profilemanager


def mock_interface_selector():
    async def mock_selector(interfaces):

        for i, inter in interfaces.items():
            if 'wi' in inter.friendly_name.lower():
                return i

        print("not asking for", (i := next(iter(interfaces))))
        return i

    webpage.ask_for_interface_choice = mock_selector


def mock_interfaces():
    def get_interfaces() -> list[IPAddress]:
        return [profilemanager.get_current_profile().interface]

    interfaces.get_interfaces = get_interfaces
