#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Хук commit-msg: не пропустить данные площадки в текст коммита.

Проверяет то же, что check_docs.py, но по сообщению коммита: стоп-слова,
IP вне документационных диапазонов, MAC-адреса.

Не ловит описание, по которому площадка узнаётся без адресов, — за этим
git diff глазами (knowledge/40_СРЕДА/40-02).

Обойти на один коммит: git commit --no-verify
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_IP = re.compile(
    r"^(192\.0\.2\.|198\.51\.100\.|203\.0\.113\."
    r"|10\.0\.0\.0|172\.16\.0\.0|192\.168\.0\.0|169\.254\.0\.0|100\.64\.0\.0"
    r"|127\.0\.0\.1|0\.0\.0\.0|8\.8\.8\.8|1\.1\.1\.1)"
)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


def main(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    bad = []

    stop = ROOT / "tools" / "stoplist.txt"
    if stop.exists():
        low = body.lower()
        for w in stop.read_text(encoding="utf-8").splitlines():
            w = w.strip().lower()
            if w and not w.startswith("#") and w in low:
                bad.append(f"стоп-слово «{w}»")

    for ip in set(IP_RE.findall(body)):
        if not ALLOWED_IP.match(ip):
            bad.append(f"адрес {ip}")
    for mac in set(MAC_RE.findall(body)):
        bad.append(f"MAC {mac}")

    if bad:
        print("commit-msg: в сообщении данные площадки:", file=sys.stderr)
        for b in bad:
            print("  -", b, file=sys.stderr)
        print("Репозиторий публичный. Переписать сообщение "
              "или git commit --no-verify.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
