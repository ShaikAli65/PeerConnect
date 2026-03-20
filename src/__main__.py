import multiprocessing
import os
import sys
import time
import traceback
from asyncio import CancelledError


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.configurations.appconfig import init_app_runtime
from src.bootup import init_app
from src.avails.useables import COLORS
from src.avails import const
from src.core import eventloop
from src.net import TCPProtocol
from src.core.async_runner import AnotherRunner


# TODO: Fix this: Error handling is inconsistent and leaky
# Some modules raise custom exceptions
# Some print
# Some swallow errors
# Some return None and hope


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


def initiate(init_app, app_runtime):
    try:
        with AnotherRunner(finalizing=app_runtime.finalizing, debug=const.debug and False) as runner:
            eventloop.set_eager_task_factory()
            runner.run(_async_initiate_helper(init_app, app_runtime.exit_stack))
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
    multiprocessing.freeze_support()
    app_runtime = init_app_runtime()
    const.PROTOCOL = TCPProtocol
    initiate(
        lambda: init_app(app_runtime),
        app_runtime,
    )
