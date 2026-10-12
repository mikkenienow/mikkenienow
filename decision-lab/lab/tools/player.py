"""Música no PC: biblioteca de arquivos de áudio e um player que toca de verdade pelo Windows.

O laboratório roda dentro do WSL2; o som sai pelo Windows. O WindowsPlayer mantém um processo
`powershell.exe` vivo com um System.Windows.Media.MediaPlayer (já presente no Windows, nada a instalar) e conversa
com ele por linhas JSON. Só tocam arquivos de áudio achados pela Biblioteca nas pastas configuradas; o caminho
nunca vem do texto do usuário. NullPlayer é o mesmo contrato sem som (testes e avaliação).
"""

from __future__ import annotations

import base64
import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".wma", ".aac", ".flac"}
STOPWORDS = {"de", "do", "da", "dos", "das", "uma", "um", "o", "a", "os", "as", "e", "no", "na", "pra", "para", "por",
             "musica", "musicas", "som", "cancao", "faixa", "toca", "tocar", "toque", "ai", "mim", "me", "que", "com"}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _norm(text)) if len(t) >= 2 and t not in STOPWORDS]


@dataclass(frozen=True)
class Track:
    path: Path
    title: str
    folder: str = ""
    demo: bool = False

    @property
    def haystack(self) -> set[str]:
        return set(tokens(f"{self.folder} {self.title}"))


class Library:
    """Arquivos de áudio das pastas configuradas (+ as músicas de demonstração geradas pelo laboratório)."""

    def __init__(self, dirs: list[str | Path], demo_dir: str | Path | None = None, max_files: int = 5000,
                 ttl: float = 30.0) -> None:
        self.dirs = [Path(d) for d in dirs]
        self.demo_dir = Path(demo_dir) if demo_dir else None
        self.max_files, self.ttl = max_files, ttl
        self._cache: list[Track] = []
        self._at = 0.0

    def _scan(self, root: Path, demo: bool) -> list[Track]:
        found: list[Track] = []
        if not root.is_dir():
            return found
        for folder, _, files in os.walk(root, followlinks=False):
            depth = len(Path(folder).relative_to(root).parts)
            if depth > 4:
                continue
            for name in sorted(files):
                path = Path(folder) / name
                if path.suffix.lower() in AUDIO_EXT:
                    rel = Path(folder).relative_to(root)
                    found.append(Track(path, re.sub(r"[_]+", " ", path.stem).strip(), "" if demo else str(rel).replace("\\", "/") if str(rel) != "." else "", demo))
                if len(found) >= self.max_files:
                    return found
        return found

    def tracks(self) -> list[Track]:
        if time.time() - self._at > self.ttl:
            found: list[Track] = []
            for root in self.dirs:
                found += self._scan(root, demo=False)
            if self.demo_dir:
                found += self._scan(self.demo_dir, demo=True)
            self._cache, self._at = found, time.time()
        return self._cache

    def user_tracks(self) -> list[Track]:
        return [t for t in self.tracks() if not t.demo]

    def find(self, query: str) -> list[Track]:
        """Faixas cujo nome/pasta contém TODAS as palavras da busca; senão, ao menos 2/3 delas (e no mínimo uma)."""
        want = set(tokens(query))
        if not want:
            return []
        scored = []
        for track in self.tracks():
            hit = len(want & track.haystack)
            if hit and hit / len(want) >= (1.0 if len(want) <= 2 else 2 / 3):
                scored.append((hit / len(want), not track.demo, track))
        scored.sort(key=lambda s: (-s[0], not s[1], s[2].title))
        return [t for _, _, t in scored]

    def random(self, rng: random.Random | None = None) -> Track | None:
        pool = self.user_tracks() or self.tracks()
        return (rng or random).choice(pool) if pool else None

    def titles(self, n: int = 5) -> list[str]:
        pool = self.user_tracks() or self.tracks()
        return [t.title for t in pool[:n]]

    def count(self) -> int:
        return len(self.tracks())


# ----------------------------------------------------------------------------- sem som (testes, avaliação)
class NullLibrary:
    """Aceita qualquer busca como se existisse a faixa: serve para testar o fluxo sem arquivos."""

    demo_dir = None

    def find(self, query: str) -> list[Track]:
        return [Track(Path("/simulado") / f"{query}.mp3", query)] if tokens(query) else []

    def random(self, rng: random.Random | None = None) -> Track | None:
        return Track(Path("/simulado/aleatoria.mp3"), "música aleatória (simulada)")

    def titles(self, n: int = 5) -> list[str]:
        return []

    def count(self) -> int:
        return 0

    def tracks(self) -> list[Track]:
        return []


class NullPlayer:
    real = False

    def __init__(self) -> None:
        self.volume, self.current, self.paused = 6, None, False

    def play(self, track: Track) -> dict[str, Any]:
        self.current, self.paused = track, False
        return {"title": track.title, "duration_s": 0.0, "volume": self.volume, "real": False}

    def pause(self) -> dict[str, Any]:
        was = self.current is not None and not self.paused
        self.paused = True
        return {"was_playing": was, "real": False}

    def resume(self) -> dict[str, Any]:
        ok = self.current is not None and self.paused
        self.paused = False
        return {"resumed": ok, "title": self.current.title if self.current else None, "real": False}

    def set_volume(self, level: int) -> dict[str, Any]:
        self.volume = max(0, min(10, level))
        return {"volume": self.volume, "real": False}

    def status(self) -> dict[str, Any]:
        return {"playing": self.current is not None and not self.paused, "paused": self.paused,
                "title": self.current.title if self.current else None, "volume": self.volume, "real": False}

    def stop(self) -> None:
        self.current = None

    close = stop


# ----------------------------------------------------------------------------- Windows
PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName PresentationCore
$p = New-Object System.Windows.Media.MediaPlayer
function Reply($o) { [Console]::Out.WriteLine(($o | ConvertTo-Json -Compress)); [Console]::Out.Flush() }
function Duration() { if ($p.NaturalDuration.HasTimeSpan) { return $p.NaturalDuration.TimeSpan.TotalSeconds } else { return 0 } }
Reply @{ event = 'ready' }
$quit = $false
while (-not $quit) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }
  try {
    $c = $line | ConvertFrom-Json
    switch ($c.cmd) {
      'open' {
        $path = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($c.path))
        $p.Open((New-Object System.Uri($path, [System.UriKind]::Absolute)))
        $p.Volume = [double]$c.volume
        $p.Play()
        $t = 0
        while (-not $p.NaturalDuration.HasTimeSpan -and $t -lt 50) { Start-Sleep -Milliseconds 100; $t++ }
        if ($p.NaturalDuration.HasTimeSpan) { Reply @{ ok = $true; duration = (Duration) } }
        else { Reply @{ ok = $false; error = 'o Windows nao conseguiu abrir o arquivo de audio' } }
      }
      'pause'  { $p.Pause(); Reply @{ ok = $true } }
      'resume' { $p.Play(); Reply @{ ok = $true } }
      'stop'   { $p.Stop(); $p.Close(); Reply @{ ok = $true } }
      'volume' { $p.Volume = [double]$c.volume; Reply @{ ok = $true } }
      'status' { Reply @{ ok = $true; position = $p.Position.TotalSeconds; duration = (Duration); volume = $p.Volume } }
      'quit'   { $quit = $true }
      default  { Reply @{ ok = $false; error = 'comando desconhecido' } }
    }
  } catch { Reply @{ ok = $false; error = $_.Exception.Message } }
}
"""


class PlayerError(RuntimeError):
    pass


class WindowsPlayer:
    real = True

    def __init__(self, script: str | Path, powershell: str = POWERSHELL) -> None:
        self.script, self.powershell = Path(script), powershell
        self.proc: subprocess.Popen[str] | None = None
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.lock = threading.RLock()
        self.volume = 6
        self.current: dict[str, Any] | None = None
        self.paused = False

    @staticmethod
    def available(powershell: str = POWERSHELL) -> bool:
        return Path(powershell).exists() and shutil.which("wslpath") is not None

    @staticmethod
    def _winpath(path: Path) -> str:
        out = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=True)
        return out.stdout.strip()

    def _start(self) -> None:
        self.script.parent.mkdir(parents=True, exist_ok=True)
        self.script.write_text(PS_SCRIPT, encoding="utf-8-sig")  # BOM: o PowerShell 5.1 lê UTF-8 só com ele
        self.proc = subprocess.Popen(
            [self.powershell, "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass", "-File",
             self._winpath(self.script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1)
        lines: queue.Queue[str | None] = queue.Queue()
        self.lines = lines

        def read(proc: subprocess.Popen[str], q: queue.Queue[str | None]) -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                q.put(line)
            q.put(None)

        threading.Thread(target=read, args=(self.proc, lines), daemon=True).start()
        try:
            if lines.get(timeout=20) is None:
                raise PlayerError("o PowerShell fechou ao iniciar o player")
        except queue.Empty as error:
            raise PlayerError("o player do Windows não iniciou em 20 s") from error

    def _call(self, command: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            assert self.proc is not None and self.proc.stdin is not None
            try:
                self.proc.stdin.write(json.dumps(command) + "\n")
                self.proc.stdin.flush()
                line = self.lines.get(timeout=timeout)
            except (queue.Empty, BrokenPipeError, OSError) as error:
                raise PlayerError("o player do Windows não respondeu") from error
            if line is None:
                raise PlayerError("o player do Windows fechou")
            return json.loads(line.lstrip("﻿"))

    def play(self, track: Track) -> dict[str, Any]:
        reply = self._call({"cmd": "open", "volume": self.volume / 10,
                            "path": base64.b64encode(self._winpath(track.path).encode("utf-8")).decode("ascii")})
        if not reply.get("ok"):
            raise PlayerError(reply.get("error") or "falha ao abrir o arquivo")
        self.current = {"title": track.title, "path": str(track.path), "duration": float(reply.get("duration") or 0)}
        self.paused = False
        return {"title": track.title, "duration_s": round(self.current["duration"], 1), "volume": self.volume, "real": True}

    def pause(self) -> dict[str, Any]:
        was = self.current is not None and not self.paused
        if was:
            self._call({"cmd": "pause"})
            self.paused = True
        return {"was_playing": was, "real": True}

    def resume(self) -> dict[str, Any]:
        ok = self.current is not None and self.paused
        if ok:
            self._call({"cmd": "resume"})
            self.paused = False
        return {"resumed": ok, "title": self.current["title"] if self.current else None, "real": True}

    def set_volume(self, level: int) -> dict[str, Any]:
        self.volume = max(0, min(10, int(level)))
        if self.current is not None:
            self._call({"cmd": "volume", "volume": self.volume / 10})
        return {"volume": self.volume, "real": True}

    def status(self) -> dict[str, Any]:
        if self.current is None:
            return {"playing": False, "paused": False, "title": None, "volume": self.volume, "real": True}
        reply = self._call({"cmd": "status"})
        position, duration = float(reply.get("position") or 0), float(reply.get("duration") or self.current["duration"])
        ended = duration > 0 and position >= duration - 0.3
        volume = round(float(reply.get("volume", self.volume / 10)) * 10)  # o que o Windows reporta, em 0–10
        return {"playing": not self.paused and not ended, "paused": self.paused, "ended": ended,
                "title": self.current["title"], "position_s": round(position, 1), "duration_s": round(duration, 1),
                "volume": volume, "real": True}

    def stop(self) -> None:
        if self.current is not None and self.proc and self.proc.poll() is None:
            try:
                self._call({"cmd": "stop"})
            except PlayerError:
                pass
        self.current, self.paused = None, False

    def close(self) -> None:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    assert self.proc.stdin is not None
                    self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                    self.proc.stdin.flush()
                    self.proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    self.proc.kill()
            self.proc = None


# ----------------------------------------------------------------------------- músicas de demonstração
# Melodias de domínio público, sintetizadas aqui: garantem que "toca uma música" sempre toque algo mesmo sem arquivos.
_N = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DEMOS: dict[str, tuple[int, str]] = {  # título -> (bpm, "nota:duração ...", duração em tempos)
    "Ode à Alegria (demo)": (132, "E4:1 E4:1 F4:1 G4:1 G4:1 F4:1 E4:1 D4:1 C4:1 C4:1 D4:1 E4:1 E4:1.5 D4:.5 D4:2 "
                                  "E4:1 E4:1 F4:1 G4:1 G4:1 F4:1 E4:1 D4:1 C4:1 C4:1 D4:1 E4:1 D4:1.5 C4:.5 C4:2"),
    "Frère Jacques (demo)": (120, "C4:1 D4:1 E4:1 C4:1 C4:1 D4:1 E4:1 C4:1 E4:1 F4:1 G4:2 E4:1 F4:1 G4:2 "
                                  "G4:.5 A4:.5 G4:.5 F4:.5 E4:1 C4:1 G4:.5 A4:.5 G4:.5 F4:.5 E4:1 C4:1 C4:1 G3:1 C4:2 C4:1 G3:1 C4:2"),
    "Parabéns pra você (demo)": (110, "G4:.75 G4:.25 A4:1 G4:1 C5:1 B4:2 G4:.75 G4:.25 A4:1 G4:1 D5:1 C5:2 "
                                      "G4:.75 G4:.25 G5:1 E5:1 C5:1 B4:1 A4:1 F5:.75 F5:.25 E5:1 C5:1 D5:1 C5:2"),
}


def _freq(note: str) -> float:
    name, octave = note[0], int(note[1:])
    return 440.0 * 2 ** ((_N[name] + 12 * (octave + 1) - 69) / 12)


def make_demo_music(folder: str | Path) -> list[Path]:
    """Gera os WAV de demonstração que ainda não existem (mono, 22,05 kHz). Idempotente."""
    import numpy as np

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rate, out = 22050, []
    for title, (bpm, score) in DEMOS.items():
        path = folder / f"{title}.wav"
        out.append(path)
        if path.exists():
            continue
        beat, chunks = 60.0 / bpm, []
        for item in score.split():
            note, length = item.split(":")
            n = int(rate * beat * float(length))
            t = np.arange(n) / rate
            f = _freq(note)
            wave_ = np.sin(2 * math.pi * f * t) + 0.35 * np.sin(2 * math.pi * 2 * f * t) + 0.12 * np.sin(2 * math.pi * 3 * f * t)
            envelope = np.minimum(1.0, t / 0.015) * np.exp(-2.2 * t / max(beat * float(length), 0.05))
            envelope[-int(rate * 0.02):] *= np.linspace(1, 0, int(rate * 0.02))  # sem estalo entre notas
            chunks.append(wave_ * envelope)
            chunks.append(np.zeros(int(rate * 0.025)))
        audio = np.concatenate(chunks + [np.zeros(rate // 3)])
        audio = np.concatenate([audio, audio])  # a melodia duas vezes: ~20–40 s
        pcm = (audio / max(1e-9, np.abs(audio).max()) * 0.6 * 32767).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm.tobytes())
    return out
