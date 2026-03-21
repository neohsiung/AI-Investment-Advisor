import os
import tempfile
import httpx
import asyncio
from typing import List, Optional
from pydub import AudioSegment
from src.utils.logger import setup_logger
from src.services.settings_service import SettingsService

class TranscriptionService:
    """
    Transcription Service for processing large audio files via Groq Whisper.
    音檔轉錄服務，支援大檔案切片與 Groq Whisper 整合。
    """
    def __init__(self, user_id: str = "system", settings_service: Optional[SettingsService] = None):
        self.logger = setup_logger("TranscriptionService")
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=user_id)
        self.groq_url = "https://api.groq.com/openai/v1/audio/transcriptions"
        
    def _get_api_key(self) -> str:
        settings = self.settings_service.get_all_settings()
        return settings.get("source_groq_api_key") or settings.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")

    async def transcribe_url(self, audio_url: str, language: str = "en") -> str:
        """
        Downloads and transcribes an audio file from a URL, handling large files by chunking.
        從 URL 下載並轉錄音檔，自動處理大檔案切片。
        """
        api_key = self._get_api_key()
        if not api_key:
            self.logger.error("GROQ_API_KEY not found in settings or environment")
            return "Error: API Key missing"

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "original_audio.mp3")
            
            # 1. Download File
            self.logger.info(f"Downloading audio from {audio_url}")
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.get(audio_url, follow_redirects=True)
                resp.raise_for_status()
                with open(file_path, "wb") as f:
                    f.write(resp.content)
            
            # 2. Check Size and Chunk if needed
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            self.logger.info(f"File size: {file_size_mb:.2f} MB")
            
            chunks = []
            if file_size_mb > 24:
                self.logger.info("File exceeds 25MB, starting chunking...")
                audio = AudioSegment.from_file(file_path)
                milli_per_chunk = 15 * 60 * 1000 # 15 minutes roughly < 20MB for most MP3s
                for i in range(0, len(audio), milli_per_chunk):
                    chunk = audio[i:i + milli_per_chunk]
                    chunk_path = os.path.join(tmp_dir, f"chunk_{i}.mp3")
                    chunk.export(chunk_path, format="mp3", bitrate="64k") # Lower bitrate to save size
                    chunks.append(chunk_path)
            else:
                chunks = [file_path]

            # 3. Transcribe Chunks
            transcripts = []
            for idx, chunk_path in enumerate(chunks):
                self.logger.info(f"Transcribing chunk {idx+1}/{len(chunks)}...")
                chunk_text = await self._call_groq_whisper(chunk_path, api_key, language)
                if chunk_text:
                    transcripts.append(chunk_text)
                
            return " ".join(transcripts)

    async def _call_groq_whisper(self, file_path: str, api_key: str, language: str) -> str:
        """Calls Groq Whisper API for a single file chunk."""
        headers = {"Authorization": f"Bearer {api_key}"}
        
        async with httpx.AsyncClient(timeout=120) as client:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "audio/mpeg")}
                data = {
                    "model": "whisper-large-v3",
                    "language": language,
                    "response_format": "json"
                }
                resp = await client.post(self.groq_url, headers=headers, files=files, data=data)
                
                if resp.status_code != 200:
                    self.logger.error(f"Groq API Error: {resp.status_code} - {resp.text}")
                    return ""
                
                return resp.json().get("text", "")
