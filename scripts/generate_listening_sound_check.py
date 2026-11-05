import math
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "static" / "listening" / "sound-check.wav"
SAMPLE_RATE = 44_100
DURATION_SECONDS = 1
FREQUENCY_HZ = 880
AMPLITUDE = 0.2


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUTPUT), "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(SAMPLE_RATE)
        samples = (
            int(32767 * AMPLITUDE * math.sin(
                2 * math.pi * FREQUENCY_HZ * sample / SAMPLE_RATE
            ))
            for sample in range(SAMPLE_RATE * DURATION_SECONDS)
        )
        audio_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


if __name__ == "__main__":
    main()
