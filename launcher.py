import sys


def main():
    if "--setup-components" in sys.argv:
        from initial_setup import main as setup_main

        return setup_main(sys.argv[1:])

    if "--assistant" in sys.argv:
        import jarvis

        return

    from ui import main as hud_main

    hud_main()


if __name__ == "__main__":
    raise SystemExit(main())
