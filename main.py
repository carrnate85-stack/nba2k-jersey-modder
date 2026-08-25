import sys


if __name__ == "__main__":
    if "--legacy" in sys.argv:
        from nba2k_jersey_modder.app import main
    else:
        from nba2k_jersey_modder.modern.app import main
    raise SystemExit(main())
