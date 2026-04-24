import threading

from infrastructure.events import get_bus, reset_bus


def setup_function() -> None:
    reset_bus()


def test_get_bus_returns_same_instance():
    b1 = get_bus()
    b2 = get_bus()
    assert b1 is b2


def test_reset_bus_yields_new_instance():
    b1 = get_bus()
    reset_bus()
    b2 = get_bus()
    assert b1 is not b2


def test_concurrent_first_touch_single_instance():
    reset_bus()
    results: list[object] = []
    lock = threading.Lock()

    def touch() -> None:
        b = get_bus()
        with lock:
            results.append(b)

    threads = [threading.Thread(target=touch) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({id(b) for b in results}) == 1


def teardown_function() -> None:
    reset_bus()
