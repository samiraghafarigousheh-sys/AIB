"""Run the EN 15316-4-2 heat-pump example for Bolzano, Italy."""

from heat_pump_15316_4_2_example import parse_args, run_example


if __name__ == "__main__":
    run_example(parse_args(default_scenario="bolzano"))
