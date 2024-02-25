import multiprocessing

from core import *

threads: dict[threading.Event, threading.Thread] = {}

stop_flag = threading.Event()


def add_thread(control_flag: threading.Event, _target_thread):
    if control_flag:
        threads[control_flag] = _target_thread
    else:
        threads.update({control_flag: _target_thread})


def concurent_thread_control():
    global stop_flag
    while not stop_flag.is_set():
        for control_flag, _target_thread in threads.items():
            if (not control_flag.is_set()) and _target_thread.is_alive():
                threads.pop(control_flag)

        time.sleep(0.1)

    return True


with multiprocessing.Pool(processes=1) as pool:
    pool.apply_async(concurent_thread_control)


def end_all_threads():
    global stop_flag
    stop_flag.set()
    for control_flag, _target_thread in threads.items():
        control_flag.set()
        _target_thread.join()
    return True
