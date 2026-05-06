#!/usr/bin/env python3
"""Live audio capture + onset/energy detection for the art renderer.

Captures system audio from the BackgroundMusic virtual device:
  brew install background-music
  System Settings → Sound → Output → Background Music

Writes state to ~/.local/share/art/audio.json:
  {
    "is_active": true,         # actively detecting audio above noise floor
    "energy": 0.42,            # smoothed normalized RMS in [0, 1]
    "tempo": 128.0,            # running BPM estimate from inter-onset intervals
    "beat_ts": 1735689600.5,   # epoch s of most recent detected onset
    "audio_weight": 0.50,
    "min_breath_period_s": 30.0
  }

The renderer polls this file every frame; each new `beat_ts` triggers a
beat punch, `energy` scales spawn rate + cluster spread, `tempo` blends
into the breath period (clamped above min_breath_period_s).

Requires: pip install --user numpy sounddevice
"""

import fcntl
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

CONFIG_PATH = os.environ.get(
    "ART_AUDIO_CONFIG",
    os.path.expanduser("~/.dotfiles/scripts/audio-watcher.config.local"),
)
STATE_PATH = os.environ.get(
    "ART_AUDIO_STATE",
    os.path.expanduser("~/.local/share/art/audio.json"),
)
LOCK_PATH = os.path.expanduser("~/.local/share/art/audio-watcher.lock")

DEVICE_NAME_PATTERN = "background music"  # case-insensitive substring match
SAMPLE_RATE = 44100
BLOCK_SIZE = 1024
HOP_S = BLOCK_SIZE / SAMPLE_RATE  # ~23ms per analysis frame

# Onset detection params — tuned for music-like signals.
N_FFT = 1024
ONSET_THRESHOLD_K = 1.5      # peak must exceed mean + k*std of recent flux
FLUX_HISTORY_FRAMES = 43     # ~1s rolling adaptive threshold window
MIN_INTER_ONSET_S = 0.18     # debounce: 333 BPM ceiling
ENERGY_SMOOTH_ALPHA = 0.10   # exponential smoothing on RMS
PEAK_DECAY = 0.9995          # peak follower for normalizing energy
SILENCE_THRESHOLD = 0.005    # RMS below which audio considered inactive
WRITE_EVERY_S = 0.20         # idle state write cadence (5Hz). Beats trigger
                             # an immediate write so renderer beat latency
                             # stays bounded by its own per-frame poll.


def acquire_singleton_lock():
    Path(os.path.dirname(LOCK_PATH)).mkdir(parents=True, exist_ok=True)
    f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.stderr.write(
            f"audio-watcher: another instance holds {LOCK_PATH}, exiting\n"
        )
        sys.exit(0)
    f.seek(0); f.truncate()
    f.write(f"{os.getpid()}\n")
    f.flush()
    return f


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def find_device(pattern):
    """Match a substring on the input device name. Prefer the plain
    'Background Music' device over the 'UI Sounds' variant since the
    latter only carries macOS sound effects.
    """
    pat = pattern.lower()
    devices = sd.query_devices()
    plain = None
    fallback = None
    for i, d in enumerate(devices):
        if pat in d["name"].lower() and d["max_input_channels"] > 0:
            if "ui sound" not in d["name"].lower() and plain is None:
                plain = (i, d["name"])
            elif fallback is None:
                fallback = (i, d["name"])
    return plain or fallback or (None, None)


def atomic_write_json(path, data):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


class BeatTracker:
    """Spectral-flux onset detector with adaptive threshold + IOI debounce.
    Tempo is the median of the recent inter-onset intervals filtered to a
    plausible BPM range (40-240).
    """

    def __init__(self):
        self.prev_mag = None
        self.flux_history = []
        self.last_onset_ts = 0.0
        self.energy = 0.0
        self.peak = 0.01
        self.beat_ts = 0.0
        self.recent_iois = []
        self.last_rms = 0.0

    def step(self, samples):
        rms = float(np.sqrt(np.mean(samples * samples)))
        self.last_rms = rms
        self.peak = max(self.peak * PEAK_DECAY, rms)
        normalized = rms / max(self.peak, 1e-6)
        self.energy = (1 - ENERGY_SMOOTH_ALPHA) * self.energy + ENERGY_SMOOTH_ALPHA * normalized

        windowed = samples * np.hanning(len(samples))
        spectrum = np.abs(np.fft.rfft(windowed, N_FFT))
        if self.prev_mag is None or self.prev_mag.shape != spectrum.shape:
            self.prev_mag = spectrum
            return False

        diff = spectrum - self.prev_mag
        flux = float(np.sum(np.maximum(0.0, diff)))
        self.prev_mag = spectrum

        self.flux_history.append(flux)
        if len(self.flux_history) > FLUX_HISTORY_FRAMES:
            self.flux_history.pop(0)
        if len(self.flux_history) < FLUX_HISTORY_FRAMES // 2:
            return False

        mean = float(np.mean(self.flux_history))
        std = float(np.std(self.flux_history))
        threshold = mean + ONSET_THRESHOLD_K * std

        now = time.time()
        if (flux > threshold
                and now - self.last_onset_ts > MIN_INTER_ONSET_S
                and rms > SILENCE_THRESHOLD):
            ioi = (now - self.last_onset_ts) if self.last_onset_ts > 0 else 0.0
            self.last_onset_ts = now
            self.beat_ts = now
            if 0.25 < ioi < 1.5:
                self.recent_iois.append(ioi)
                if len(self.recent_iois) > 16:
                    self.recent_iois.pop(0)
            return True
        return False

    def estimated_tempo(self):
        if len(self.recent_iois) < 4:
            return 0.0
        return 60.0 / float(np.median(self.recent_iois))

    def is_active(self):
        return self.last_rms > SILENCE_THRESHOLD


def main():
    lock_fd = acquire_singleton_lock()  # noqa: F841
    config = load_config()
    audio_weight = float(config.get("audio_weight", 0.50))
    min_breath = float(config.get("min_breath_period_s", 30.0))

    device_idx, device_name = find_device(DEVICE_NAME_PATTERN)
    if device_idx is None:
        sys.stderr.write(
            "audio-watcher: 'Background Music' input device not found.\n"
            "  brew install background-music\n"
            "  → System Settings → Sound → Output → Background Music\n"
            "Available input devices:\n"
        )
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                sys.stderr.write(f"  [{i}] {d['name']}\n")
        sys.exit(1)

    sys.stderr.write(
        f"audio-watcher: capturing [{device_idx}] {device_name} "
        f"@ {SAMPLE_RATE}Hz audio_weight={audio_weight} → {STATE_PATH}\n"
    )

    tracker = BeatTracker()
    last_write_ts = [0.0]
    last_active = [None]

    def write_state():
        active = tracker.is_active()
        if active != last_active[0]:
            sys.stderr.write(
                f"audio-watcher: {'audio detected' if active else 'silent'}\n"
            )
            last_active[0] = active
        atomic_write_json(STATE_PATH, {
            "is_active": active,
            "energy": float(tracker.energy),
            "tempo": float(tracker.estimated_tempo()),
            "beat_ts": float(tracker.beat_ts),
            "audio_weight": audio_weight,
            "min_breath_period_s": min_breath,
        })
        last_write_ts[0] = time.time()

    def callback(indata, frames, time_info, status):
        if status:
            sys.stderr.write(f"audio-watcher: stream status: {status}\n")
        # Flatten channels to mono.
        if indata.ndim > 1 and indata.shape[1] > 1:
            samples = indata.mean(axis=1).astype(np.float32)
        else:
            samples = indata.reshape(-1).astype(np.float32)
        beat_fired = tracker.step(samples)

        # Always write on a beat (low-latency); else throttle.
        now = time.time()
        if beat_fired or now - last_write_ts[0] >= WRITE_EVERY_S:
            write_state()

    write_state()  # seed file so renderer doesn't see a missing path

    try:
        with sd.InputStream(
            device=device_idx,
            channels=1,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype="float32",
            callback=callback,
        ):
            while True:
                time.sleep(60)
    except KeyboardInterrupt:
        sys.stderr.write("\naudio-watcher: stopped\n")


if __name__ == "__main__":
    main()
