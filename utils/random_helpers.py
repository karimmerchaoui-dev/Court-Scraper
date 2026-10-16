import sys


def bell(n=1):
    """Ring the system bell n times."""
    for _ in range(n):
        if sys.platform == "win32":
            import winsound
            winsound.Beep(1000, 1000)  # frequency Hz, duration ms
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
