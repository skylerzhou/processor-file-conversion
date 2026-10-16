"""A stand-in for mefstreamer.jar used by the gate tests.

Emits the frame protocol the real jar does (see processor/converters/mef2/
mef_streamer.py) for two short channels, then exits. Behaviour is steered by
env vars so one script covers the success and failure cases:

  FAKE_STREAMER_EXIT     exit code after the frames (default 0)
  FAKE_STREAMER_FRAMES   "0" to exit without writing any frame
  FAKE_STREAMER_NOTE     path; if set, MEF_CHANNELS and argv[1] are written
                         there so a test can see what the jar was told
"""
import json
import os
import struct
import sys

CHANNEL_META, SEGMENT_START, SAMPLES_INT32, SEGMENT_END, END = 1, 2, 3, 4, 5
RATE_HZ = 100.0
START_US = 1_700_000_000_000_000
N = 50


def frame(kind: int, payload: bytes = b"") -> bytes:
    return bytes([kind]) + struct.pack("<I", len(payload)) + payload


def main() -> None:
    note = os.environ.get("FAKE_STREAMER_NOTE")
    if note:
        with open(note, "w") as f:
            json.dump({"MEF_CHANNELS": os.environ.get("MEF_CHANNELS", ""),
                       "input_dir": sys.argv[1] if len(sys.argv) > 1 else ""}, f)

    out = sys.stdout.buffer
    if os.environ.get("FAKE_STREAMER_FRAMES", "1") != "0":
        for i, name in enumerate(("A1", "B2")):
            meta = {"name": name, "type": "EEG", "description": "test", "unit": "counts",
                    "voltage_conversion_factor": 0.5, "rate_hz": RATE_HZ}
            out.write(frame(CHANNEL_META, json.dumps(meta).encode()))
            out.write(frame(SEGMENT_START, struct.pack("<qd", START_US, RATE_HZ)))
            samples = struct.pack(f"<{N}i", *[(i + 1) * k for k in range(N)])
            out.write(frame(SAMPLES_INT32, samples))
            end_us = START_US + int((N - 1) * 1_000_000 / RATE_HZ)
            out.write(frame(SEGMENT_END, struct.pack("<qq", end_us, N)))
        out.write(frame(END))
    out.flush()
    sys.exit(int(os.environ.get("FAKE_STREAMER_EXIT", "0")))


if __name__ == "__main__":
    main()
