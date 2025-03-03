import getpass
import random

from src.core.public import Dock
from src.managers import ProfileManager, profilemanager


async def profile_getter(ip):
    p = await ProfileManager.add_profile(
        getpass.getuser(),
        {
            "USER": {
                "name": getpass.getuser() + str(ip),
                "id": random.getrandbits(255),
            },
            "SERVER": {
                "port": 45000,
                "ip": "0.0.0.0",
                "id": 0,
            },
            "INTERFACE": {
                "ip": ip,
                "scope_id": -1,
                "if_name": b'{TEST}',
                "friendly_name": "testing",
            } if ip else {}
        }
    )

    async def delete(*_):
        await ProfileManager.delete_profile(p.file_name)

    Dock.exit_stack.push_async_exit(delete)
    return p


async def mock_profile(config):
    if config.test_mode == 'host':
        ip = f"127.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(2, 255)}"
    else:
        ip = None
    await profilemanager.set_current_profile(await profile_getter(ip))
