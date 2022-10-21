"""This module is responsible for handling EVGA Precision X capture files."""

from formats.rivatuner import RivaTuner


class Precision(RivaTuner):
    """Class for parsing EVGA Precision X log files."""

    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "1.0.7": {
            "Elapsed Time": "Time",
            "Frametimes": "Frametime",
            "GPU Board Power": "Total Power",
            "GPU Frequency": "GPU Clock",
            "GPU Temperature": "GPU Temperature",
            "GPU Utilization": "GPU Usage",
            "GPU Voltage": "GPU Voltage",
        },
    }
