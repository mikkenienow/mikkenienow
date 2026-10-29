"""Teste de integração do player de verdade: toca uma música NESTE PC e confere, pelo próprio player, que ela anda.

  .venv/bin/python -m bench.player_check [--seconds 4] [--file caminho.mp3]

Usa a música de demonstração gerada em runs/music (ou --file). Confere: abre e toca, a posição avança, pausa congela
a posição, retoma, volume muda, parar zera. Não consegue ouvir o som: só o Windows confirma que decodificou e
avançou o relógio da faixa. Sai com código 1 se algo falhar.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lab.taxonomy import ROOT  # noqa: E402
from lab.tools.player import Library, Track, WindowsPlayer, make_demo_music  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--file", default=None)
    args = parser.parse_args()
    if not WindowsPlayer.available():
        raise SystemExit("sem powershell.exe/wslpath: este teste só roda no WSL2")
    demo = make_demo_music(ROOT / "runs" / "music")
    track = Track(Path(args.file), Path(args.file).stem) if args.file else Library([], ROOT / "runs" / "music").tracks()[0]
    print(f"faixa: {track.title}  ({track.path})  · demos geradas: {len(demo)}")
    player = WindowsPlayer(ROOT / "runs" / "player.ps1")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), detail))
        print(f"{'ok   ' if ok else 'FALHA'} {name}  {detail}", flush=True)

    try:
        start = time.time()
        info = player.play(track)
        check("abre e começa a tocar", info["duration_s"] > 1, f"duração {info['duration_s']} s, abriu em {time.time() - start:.1f} s")
        time.sleep(args.seconds)
        s1 = player.status()
        check("a posição avança", s1["playing"] and s1["position_s"] > args.seconds - 1.5, f"posição {s1['position_s']} s após {args.seconds} s")
        player.pause()
        p1 = player.status()["position_s"]
        time.sleep(1.5)
        p2 = player.status()
        check("pausa congela a posição", p2["paused"] and abs(p2["position_s"] - p1) < 0.3, f"{p1} → {p2['position_s']} s")
        player.resume()
        time.sleep(1.2)
        s3 = player.status()
        check("retoma e volta a andar", s3["playing"] and s3["position_s"] > p2["position_s"] + 0.8, f"{p2['position_s']} → {s3['position_s']} s")
        player.set_volume(3)
        player.set_volume(3)
        check("volume do player muda (lido do Windows)", player.status()["volume"] == 3, f"volume {player.status()['volume']} de 10")
        player.stop()
        check("parar encerra a faixa", player.status()["title"] is None)
    finally:
        player.close()
    ok = all(r[1] for r in results)
    print("TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
