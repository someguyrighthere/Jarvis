import sys


def main():
    if "--assistant" in sys.argv:
        import jarvis

        return

    from ui import main as hud_main

    hud_main()


if __name__ == "__main__":
    main()
