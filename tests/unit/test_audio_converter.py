from __future__ import annotations

from pathlib import Path

import pytest

from app.services.audio_converter import AudioConversionError, AudioConverter


class TestAudioConverter:
    def test_convert_to_mp3_missing_input_raises_error(self) -> None:
        converter = AudioConverter()
        fake_input = Path("/tmp/nonexistent.ogg")
        fake_output = Path("/tmp/out")

        with pytest.raises(AudioConversionError):
            converter.convert_to_mp3(fake_input, fake_output)

    def test_validate_output_empty_path_returns_false(self) -> None:
        converter = AudioConverter()
        result = converter._validate_output(Path("/tmp/nonexistent.mp3"))
        assert result is False

    def test_validate_output_zero_size_file_returns_false(self, tmp_path: Path) -> None:
        converter = AudioConverter()
        empty_file = tmp_path / "empty.mp3"
        empty_file.write_text("")
        result = converter._validate_output(empty_file)
        assert result is False
