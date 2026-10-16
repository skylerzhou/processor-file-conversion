"""Runtime configuration from environment variables.

On Fargate the platform sets these as container overrides; on Lambda
handler.py copies them out of the event payload first (see handler.py).
"""
import os
from dataclasses import dataclass, field


def _split_channels(raw: str) -> list[str]:
    """'A1, B2' -> ['A1', 'B2']; '' -> []. Spaces inside a name are kept."""
    return [c.strip() for c in raw.split(",") if c.strip()]


@dataclass
class Config:
    input_dir: str = "/data/input"
    output_dir: str = "/data/output"
    # Set to force the converted file's name. Empty = "<recording folder>.<ext>".
    output_filename: str = ""
    # Convert only these channels (comma-separated). Empty = all channels.
    # Comes from the plot request so a 100-channel recording isn't decoded
    # end to end to draw one trace.
    channels: list[str] = field(default_factory=list)
    # Command prefix that launches the MEF2 streamer; the folder to read is
    # appended at run time.
    java_cmd: str = "/opt/java/openjdk/bin/java -jar /processor/mefstreamer.jar"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            input_dir=os.getenv("INPUT_DIR", cls.input_dir),
            output_dir=os.getenv("OUTPUT_DIR", cls.output_dir),
            output_filename=os.getenv("OUTPUT_FILENAME", ""),
            channels=_split_channels(os.getenv("CHANNELS", "") or os.getenv("MEF_CHANNELS", "")),
            java_cmd=os.getenv("JAVA_CMD", cls.java_cmd),
        )
