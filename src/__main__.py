import logging
import multiprocessing
import os
import sys
import time
import traceback
from asyncio import CancelledError

from src.avails.useables import COLORS

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.core.app import App, AppType
from src.avails import const
from src.conduit import pagehandle
from src.configurations import bootup, configure
from src.core import acceptor, eventloop, requests
from src.net import connectivity
from src.core.async_runner import AnotherRunner
from src.managers import logmanager, message, profilemanager

_logger = logging.getLogger()


# TODO: Fix this: Error handling is inconsistent and leaky
# Some modules raise custom exceptions
# Some print
# Some swallow errors
# Some return None and hope

async def init_app(app: AppType):
    exit_stack = app.exit_stack
    _logger.info("setting paths")
    configure.set_paths()
    _logger.info("initiating logging")
    await logmanager.initiate(exit_stack)

    config_map = await configure.load_configs(exit_stack)
    app.current_config = config_map
    _logger.info(f"loaded configurations, {config_map=}")

    _logger.info("loading profiles")
    await profilemanager.load_profiles_to_program(config_map)

    _logger.info("launching webpage")
    await bootup.launch_web_page()

    _logger.info("load interfaces")
    app.interfaces = await bootup.load_interfaces()

    _logger.info("initiating page handle")
    await pagehandle.initiate_page_handle(exit_stack)
    _logger.info("boot_up initiating")
    await bootup.set_ip_config(app)

    _logger.info("configuring this peer object")
    bootup.configure_this_remote_peer(app)

    _logger.info("printing configurations")
    configure.print_app(app.read_only())

    _logger.info("initiating comms")
    app.connections.dispatcher = await acceptor.initiate_acceptor(
        app.exit_stack,
        app.finalizing,
        app.addr_tuple,
        app.current_profile,
        app.this_remote_peer,
    )

    _logger.info("starting message connections")
    app.messages.dispatcher = await message.initiate(
        app.finalizing,
        app.this_peer_id,
        app.connections.dispatcher,
        app.exit_stack,
    )

    _logger.info("initiating requests")
    await requests.initiate(app)

    _logger.info("initiating connectivity checker")
    await connectivity.initiate(
        app.exit_stack,
        app.requests.dispatcher,
        app.requests.transport,
        app.this_peer_id,
    )


cancellation_started = 0.0


async def _async_initiate_helper(init_app, exit_stack):

    error = None
    async with exit_stack:
        try:
            await init_app()
        except CancelledError as ce:
            error = ce
            # no point of passing cancelled error related to main task into exit_stack
            # (which will be mostly related to keyboard interrupts)

            global cancellation_started
            cancellation_started = time.perf_counter()
        except BaseException as be:
            if const.debug:
                print(COLORS.RED, "CRITICAL EXCEPTION NOT EXPECTING", COLORS.RESET)
                traceback.print_exc()
            error = be

    if error is not None:
        raise error


def initiate(init_app, exit_stack, finalizing):
    try:
        with AnotherRunner(finalizing=finalizing, debug=const.debug and False) as runner:
            eventloop.set_eager_task_factory()
            runner.run(_async_initiate_helper(init_app, exit_stack))
    except BaseException as be:
        if const.debug:
            print_str = f"{'-' * 80}\n" \
                        f"## PRINTING TRACEBACK, {const.debug=}\n" \
                        f"{'-' * 80}\n" \
                        f"clean exit completed within {time.perf_counter() - cancellation_started:.6f}s\n"
            be.add_note(print_str)
            raise be

        sys.exit(-1)


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    multiprocessing.freeze_support()
    initiate(lambda: init_app(App), App.exit_stack, App.finalizing)
