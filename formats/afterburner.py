"""This module is responsible for handling MSI Afterburner capture files."""

from csv import reader

from core.logger import get_logger, log_exception

from formats.rivatuner import RivaTuner

logger = get_logger(__name__)


class Afterburner(RivaTuner):
    """Class for parsing FrameView log files."""

    HEADER_ALIASES: dict[str, dict[str, str]] = {
        "4.6.4": {
            "Elapsed Time": "Time",
            "Frametimes": "Frametime",
            "GPU Board Power": "Power",
            "GPU Frequency": "Core clock",
            "GPU Temperature": "GPU temperature",
            "GPU Utilization": "GPU usage",
            "GPU Voltage": "GPU voltage",
            "CPU Power": "CPU power",
            "CPU Frequency": "CPU clock",
            "CPU Temperature": "CPU temperature",
            "CPU Utilization": "CPU usage",
        },
    }

    def __init__(self, **kwargs) -> None:
        try:
            super().__init__(**kwargs)
            if not self.uses_saved_properties:
                self.properties["GPU"] = self.gpu_topology
        except Exception as e:
            log_exception(logger, e, "Failed to read MSI Afterburner file")

    @property
    def gpu_topology(self) -> str:
        """Read the second row of the capture file to obtain the GPU name."""
        gpu_name: str = "Unknown GPU"
        try:
            with open(self.path) as ab_file:
                file_data = list(reader(ab_file))
                second_row = file_data[1]
                gpu_name = second_row[2].strip()
        except Exception as e:
            log_exception(logger, e, "Could not read GPU name from file")
        finally:
            return gpu_name
