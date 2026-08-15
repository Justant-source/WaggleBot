import wave
import json
import sys
import argparse
from pathlib import Path
import numpy as np

def load_wav(filepath):
    """Load WAV file and return audio data, sample rate."""
    with wave.open(filepath, 'rb') as f:
        n_channels = f.getnchannels()
        sample_width = f.getsampwidth()
        framerate = f.getframerate()
        n_frames = f.getnframes()
        frames = f.readframes(n_frames)

    audio_data = np.frombuffer(frames, dtype=np.int16)
    if n_channels > 1:
        audio_data = audio_data.reshape(-1, n_channels)
        audio_data = audio_data[:, 0]  # Take first channel

    audio_data = audio_data.astype(np.float32) / 32768.0
    return audio_data, framerate

def compute_duration(audio, sr):
    """Compute duration in seconds."""
    return len(audio) / sr

def compute_silence(audio, sr):
    """
    Detect silence using energy-based method.
    - 10ms hop, 25ms window
    - Threshold: 95th percentile - 40dB
    - Only count silences >= 120ms
    - Exclude first/last 0.3-0.4s
    """
    hop_ms, window_ms = 10, 25
    hop_samples = int(sr * hop_ms / 1000)
    window_samples = int(sr * window_ms / 1000)

    # Exclude edges (0.35s each side)
    edge_samples = int(sr * 0.35)
    audio_trimmed = audio[edge_samples:-edge_samples]

    # Compute energy in sliding windows
    energies = []
    for i in range(0, len(audio_trimmed) - window_samples + 1, hop_samples):
        window = audio_trimmed[i:i + window_samples]
        energy_db = 10 * np.log10(np.mean(window ** 2) + 1e-10)
        energies.append(energy_db)

    energies = np.array(energies)
    threshold = np.percentile(energies, 95) - 40

    # Find silence frames
    silence_frames = energies < threshold

    # Group consecutive silence frames and filter by duration
    silence_regions = []
    i = 0
    while i < len(silence_frames):
        if silence_frames[i]:
            start = i
            while i < len(silence_frames) and silence_frames[i]:
                i += 1
            duration_ms = (i - start) * hop_ms
            if duration_ms >= 120:
                duration_sec = duration_ms / 1000.0
                silence_regions.append(duration_sec)
        else:
            i += 1

    # Compute metrics
    total_silence = sum(silence_regions) if silence_regions else 0
    silence_ratio = (total_silence / compute_duration(audio, sr)) * 100 if compute_duration(audio, sr) > 0 else 0
    silence_median = np.median(silence_regions) if silence_regions else 0
    silence_max = max(silence_regions) if silence_regions else 0

    return {
        'silence_ratio_pct': round(silence_ratio, 2),
        'silence_count': len(silence_regions),
        'silence_median_sec': round(float(silence_median), 3),
        'silence_max_sec': round(float(silence_max), 3)
    }

def compute_dynamics(audio, sr):
    """
    Compute crest factor and loudness range.
    - 0.4s window, 50% overlap
    - Crest factor from RMS
    - LRA approx: 95th - 10th percentile of loudness (exclude < -50dB)
    """
    window_samples = int(sr * 0.4)
    hop_samples = window_samples // 2

    loudness_values = []
    for i in range(0, len(audio) - window_samples + 1, hop_samples):
        window = audio[i:i + window_samples]
        rms = np.sqrt(np.mean(window ** 2))
        loudness_db = 10 * np.log10(rms ** 2 + 1e-10)
        if loudness_db > -50:
            loudness_values.append(loudness_db)

    loudness_values = np.array(loudness_values)

    if len(loudness_values) > 0:
        lra = np.percentile(loudness_values, 95) - np.percentile(loudness_values, 10)
        crest_factor = 20 * np.log10(np.max(np.abs(audio)) / (np.sqrt(np.mean(audio ** 2)) + 1e-10) + 1e-10)
    else:
        lra = 0
        crest_factor = 0

    return {
        'crest_factor_db': round(float(crest_factor), 2),
        'loudness_range_db': round(float(lra), 2)
    }

def compute_stft(audio, window_size=1024, hop_size=256):
    """
    Compute STFT using numpy FFT.
    Returns: frequency bins, magnitude spectrogram
    """
    window = np.hanning(window_size)
    n_frames = (len(audio) - window_size) // hop_size + 1
    spectrogram = []

    for i in range(n_frames):
        frame = audio[i * hop_size:i * hop_size + window_size]
        if len(frame) < window_size:
            frame = np.pad(frame, (0, window_size - len(frame)))
        windowed = frame * window
        fft_result = np.fft.rfft(windowed)
        magnitude = np.abs(fft_result)
        spectrogram.append(magnitude)

    return np.array(spectrogram).T  # (freq_bins, time_frames)

def compute_transient(audio, sr):
    """
    Detect transient sharpness using STFT spectral flux.
    - 1024 window, 256 hop
    - 99th percentile / median of flux (onset_sharpness)
    - Same for 4-8kHz (hf_transient)
    """
    window_size = 1024
    hop_size = 256

    magnitude_spec = compute_stft(audio, window_size, hop_size)

    # Spectral flux (difference between consecutive frames)
    flux = np.sqrt(np.sum(np.diff(magnitude_spec, axis=1) ** 2, axis=0))

    if len(flux) == 0:
        onset_sharpness = 0
        hf_transient = 0
    else:
        # Overall transient
        median_flux = np.median(flux) if np.median(flux) > 0 else 1e-10
        onset_sharpness = np.percentile(flux, 99) / median_flux

        # 4-8kHz band
        freq_bins = np.fft.rfftfreq(window_size, 1 / sr)
        idx_4k = np.argmin(np.abs(freq_bins - 4000))
        idx_8k = np.argmin(np.abs(freq_bins - 8000))
        flux_hf = np.sqrt(np.sum(np.diff(magnitude_spec[idx_4k:idx_8k, :], axis=1) ** 2, axis=0))

        median_flux_hf = np.median(flux_hf) if np.median(flux_hf) > 0 else 1e-10
        hf_transient = np.percentile(flux_hf, 99) / median_flux_hf

    return {
        'onset_sharpness': round(float(onset_sharpness), 2),
        'hf_transient': round(float(hf_transient), 2)
    }

def compute_spectrum(audio, sr):
    """
    Compute spectrum metrics on voiced segments.
    - -60dB rolloff frequency (kHz)
    - 5 bands: 0-1k, 4-8k, 8-12k, 12-16k, 16k+
    """
    # Simple voiced detection (high RMS frames)
    window_samples = int(sr * 0.05)
    hop_samples = window_samples // 2

    voiced_frames = []
    for i in range(0, len(audio) - window_samples + 1, hop_samples):
        window = audio[i:i + window_samples]
        rms = np.sqrt(np.mean(window ** 2))
        if rms > 0.02:  # Voiced threshold
            voiced_frames.extend(window)

    if len(voiced_frames) == 0:
        voiced_frames = audio

    voiced_audio = np.array(voiced_frames)

    # FFT and magnitude spectrum
    fft_result = np.fft.rfft(voiced_audio)
    magnitude = np.abs(fft_result)
    freqs = np.fft.rfftfreq(len(voiced_audio), 1 / sr)

    # Convert to dB
    magnitude_db = 20 * np.log10(magnitude + 1e-10)
    max_db = np.max(magnitude_db)

    # Find -60dB rolloff frequency
    rolloff_threshold = max_db - 60
    rolloff_idx = np.where(magnitude_db >= rolloff_threshold)[0]
    rolloff_freq_khz = freqs[rolloff_idx[-1]] / 1000 if len(rolloff_idx) > 0 else 0

    # Compute band energy (dB)
    bands = {
        '0-1k': (0, 1000),
        '4-8k': (4000, 8000),
        '8-12k': (8000, 12000),
        '12-16k': (12000, 16000),
        '16k+': (16000, sr // 2)
    }

    band_energy = {}
    for band_name, (f_min, f_max) in bands.items():
        mask = (freqs >= f_min) & (freqs < f_max)
        if np.any(mask):
            band_mag = magnitude_db[mask]
            band_energy[f'band_{band_name}_db'] = round(float(np.mean(band_mag)), 2)
        else:
            band_energy[f'band_{band_name}_db'] = -np.inf

    return {
        'rolloff_freq_khz': round(float(rolloff_freq_khz), 2),
        **band_energy
    }

def main():
    parser = argparse.ArgumentParser(description='Measure TTS audio metrics')
    parser.add_argument('wav_path', help='Path to WAV file')
    parser.add_argument('--reference', help='Path to reference WAV file for comparison')
    args = parser.parse_args()

    try:
        # Load target audio
        audio, sr = load_wav(args.wav_path)

        # Compute all metrics
        result = {
            'file': str(args.wav_path),
            'duration_sec': round(compute_duration(audio, sr), 3),
            'silence': compute_silence(audio, sr),
            'dynamics': compute_dynamics(audio, sr),
            'transient': compute_transient(audio, sr),
            'spectrum': compute_spectrum(audio, sr)
        }

        # If reference provided, compute diff
        if args.reference:
            ref_audio, ref_sr = load_wav(args.reference)
            ref_result = {
                'silence': compute_silence(ref_audio, ref_sr),
                'dynamics': compute_dynamics(ref_audio, ref_sr),
                'transient': compute_transient(ref_audio, ref_sr),
                'spectrum': compute_spectrum(ref_audio, ref_sr),
                'duration_sec': compute_duration(ref_audio, ref_sr)
            }

            # Add diffs organized by category
            diffs = {
                'silence': {},
                'dynamics': {},
                'transient': {},
                'spectrum': {},
                'duration_sec_diff': round(
                    result['duration_sec'] - ref_result['duration_sec'], 3
                )
            }

            for key in result['silence']:
                diffs['silence'][f'{key}_diff'] = round(
                    result['silence'][key] - ref_result['silence'][key], 2
                ) if isinstance(result['silence'][key], (int, float)) else None

            for key in result['dynamics']:
                diffs['dynamics'][f'{key}_diff'] = round(
                    result['dynamics'][key] - ref_result['dynamics'][key], 2
                )

            for key in result['transient']:
                diffs['transient'][f'{key}_diff'] = round(
                    result['transient'][key] - ref_result['transient'][key], 2
                )

            for key in result['spectrum']:
                diffs['spectrum'][f'{key}_diff'] = round(
                    result['spectrum'][key] - ref_result['spectrum'][key], 2
                )

            result['diffs'] = diffs

        print(json.dumps(result, indent=2))

    except Exception as e:
        error_result = {
            'error': str(e),
            'file': args.wav_path
        }
        print(json.dumps(error_result, indent=2), file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
