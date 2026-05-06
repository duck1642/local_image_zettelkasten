import threading


ONLINE_STOP_AFTER_CURRENT = threading.Event()
LOCAL_STOP_AFTER_CURRENT = threading.Event()


def clear_stop_flags():
    ONLINE_STOP_AFTER_CURRENT.clear()
    LOCAL_STOP_AFTER_CURRENT.clear()

