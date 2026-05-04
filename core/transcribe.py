"""Trascrizione audio/video con faster-whisper (CUDA)."""
from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel


class Transcriber:
    """Wrapper intorno a faster-whisper.

    Su RTX 4080 Super: model_size='medium' + compute_type='float16' è un ottimo
    default (veloce e accurato). Per massima qualità usa 'large-v3'.
    """

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "cuda",
        compute_type: str = "float16",
    ) -> None:
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(
        self,
        media_path: str | Path,
        language: str | None = None,
        vad_filter: bool = True,
        beam_size: int = 5,
    ) -> str:
        """Restituisce la trascrizione completa come singola stringa.

        faster-whisper accetta direttamente file video/audio grazie al
        decoder ffmpeg integrato (richiede ffmpeg installato nel sistema).
        """
        segments, _info = self.model.transcribe(
            str(media_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,  # taglia i silenzi, migliora velocità e qualità
        )
        parts = [seg.text.strip() for seg in segments]
        return " ".join(p for p in parts if p)
