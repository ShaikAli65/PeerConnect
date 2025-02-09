from src.configurations import interfaces
from src.managers.statemanager import State
from test import start_test


def test_interfaces():
    l = interfaces.get_interfaces()
    assert len(l) > 0
    print("found interfaces:")
    for i in l:
        print(i)


if __name__ == "__main__":
    start_test([State("testing interfaces", test_interfaces)])
