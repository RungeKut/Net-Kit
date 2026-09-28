#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка целостности набора перед коммитом.

Что проверяется (knowledge/00_ПРАВИЛА.md, раздел 9):

1. каждый файл knowledge/ есть в INDEX.md и наоборот;
2. шапки: id уникален, у «проверено» есть verified и applies_to;
3. данные площадок не попали никуда, кроме local/:
   слова из стоп-листа, IP вне документационных диапазонов,
   MAC-адреса, строки, похожие на ключи;
4. local/ не попал под git;
5. стоп-лист есть на машине и НЕ под git.

Чего проверка НЕ ловит: описание, по которому площадка узнаётся без
единого адреса. За этим — git diff глазами.

Запуск:  python tools/check_docs.py
Код возврата 0 — чисто, 1 — есть замечания.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KN = ROOT / "knowledge"

# Диапазоны, которые разрешено писать в примерах: документационные
# (RFC 5737), плюс явно обобщённые приватные сети целиком.
ALLOWED_IP = re.compile(
    r"^(192\.0\.2\.|198\.51\.100\.|203\.0\.113\."
    r"|10\.0\.0\.0|172\.16\.0\.0|192\.168\.0\.0|169\.254\.0\.0|100\.64\.0\.0"
    r"|127\.0\.0\.1|0\.0\.0\.0|255\.255|8\.8\.8\.8|1\.1\.1\.1)"
)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
KEY_RE = re.compile(r"\b[A-Za-z0-9+/]{38,}={0,2}\b")

problems: list[str] = []


def say(msg):
    problems.append(msg)


def scanned_files():
    """Все текстовые файлы набора, кроме local/, .git/ и служебных."""
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", "local/", "tools/stoplist")):
            continue
        if p.suffix.lower() in {".md", ".py", ".ps1", ".bat", ".sh", ".txt"}:
            yield p, rel


# --- 1. индекс ---------------------------------------------------------

def check_index():
    index = KN / "INDEX.md"
    if not index.exists():
        say("нет knowledge/INDEX.md")
        return
    text = index.read_text(encoding="utf-8")
    on_disk = {p.relative_to(KN).as_posix()
               for p in KN.rglob("*.md")
               if p.name not in {"INDEX.md", "00_ПРАВИЛА.md"}}
    linked = set(re.findall(r"\]\((\d\d_[^)]+\.md)\)", text))
    linked.discard("00_ПРАВИЛА.md")
    for miss in sorted(on_disk - linked):
        say(f"файл не упомянут в INDEX.md: knowledge/{miss}")
    for dead in sorted(linked - on_disk):
        say(f"в INDEX.md ссылка на несуществующий файл: {dead}")


# --- 2. шапки ----------------------------------------------------------

def check_headers():
    seen = {}
    for p in KN.rglob("*.md"):
        if p.name == "INDEX.md":
            continue
        text = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            say(f"нет шапки: {p.relative_to(ROOT)}")
            continue
        head = m.group(1)
        fields = dict(re.findall(r"^(\w+):\s*(.+)$", head, re.M))
        rid = fields.get("id", "").strip('"\' ')
        if not rid:
            say(f"нет id: {p.relative_to(ROOT)}")
        elif rid in seen:
            say(f"id {rid} повторяется: {p.name} и {seen[rid]}")
        else:
            seen[rid] = p.name
        if not fields.get("title"):
            say(f"нет title: {p.relative_to(ROOT)}")
        status = fields.get("status", "")
        if "проверено" in status and "не проверено" not in status:
            if not fields.get("verified"):
                say(f"статус «проверено» без verified: {p.relative_to(ROOT)}")
            if p.name != "00_ПРАВИЛА.md" and not fields.get("applies_to"):
                say(f"статус «проверено» без applies_to: {p.relative_to(ROOT)}")


# --- 3. данные площадок ------------------------------------------------

def check_leaks():
    stop = ROOT / "tools" / "stoplist.txt"
    words = []
    if stop.exists():
        words = [w.strip().lower() for w in
                 stop.read_text(encoding="utf-8").splitlines()
                 if w.strip() and not w.startswith("#")]
    else:
        say("нет tools/stoplist.txt — завести его (см. 40_СРЕДА/40-02)")

    for p, rel in scanned_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        for w in words:
            if w in low:
                say(f"стоп-слово «{w}» в {rel}")
        for ip in set(IP_RE.findall(text)):
            if not ALLOWED_IP.match(ip):
                say(f"адрес вне документационных диапазонов: {ip} в {rel}")
        for mac in set(MAC_RE.findall(text)):
            say(f"MAC-адрес: {mac} в {rel}")
        if rel.endswith(".md"):
            for key in set(KEY_RE.findall(text)):
                say(f"строка похожа на ключ: {key[:16]}… в {rel}")


# --- 4-5. git ----------------------------------------------------------

def git(*args):
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args],
                           capture_output=True, text=True, timeout=30)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def check_git():
    tracked = git("ls-files").splitlines()
    for f in tracked:
        if f.startswith("local/") and f not in (
                "local/README.md", "local/ПЛОЩАДКА-образец.md"):
            say(f"файл площадки под git: {f}")
    if "tools/stoplist.txt" in tracked:
        say("tools/stoplist.txt под git — он должен быть только локальным")


def main():
    check_index()
    check_headers()
    check_leaks()
    check_git()
    if problems:
        print(f"Замечаний: {len(problems)}\n")
        for p in problems:
            print(" -", p)
        return 1
    print("Проверка пройдена: индекс, шапки, данные площадок, git — чисто.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
