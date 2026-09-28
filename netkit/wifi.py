"""Переключение сетей Wi-Fi в Windows без прав администратора.

Профиль добавляется в пользовательскую область (``user=current``) —
повышения прав не требуется.

ГЛАВНАЯ ЛОВУШКА: ``netsh wlan show networks`` отдаёт устаревший кэш.
Сеть может быть в эфире и не быть в списке, а подключение к только что
покинутой сети падает с «сеть недоступна». Поэтому ``connect()``
повторяет попытки с паузами (knowledge/30_ГРАБЛИ/30-05).

Вторая ловушка рядом: у точки доступа RouterOS флаг ``running`` означает
«есть подключённый клиент», а не «идёт вещание». Пустой скан плюс
running=false выглядят убедительно и оба ничего не значат
(knowledge/30_ГРАБЛИ/30-04).

ПАРОЛЬ в файле профиля лежит открытым текстом — ``add_profile`` удаляет
файл сразу после добавления.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path

_PROFILE = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{ssid}</name>
  <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security>
    <authEncryption><authentication>WPA2PSK</authentication>
      <encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
    <sharedKey><keyType>passPhrase</keyType><protected>false</protected>
      <keyMaterial>{psk}</keyMaterial></sharedKey>
  </security></MSM>
</WLANProfile>
"""


def _netsh(*args, timeout=30):
    p = subprocess.run(["netsh", "wlan", *args], capture_output=True,
                       text=True, errors="replace", timeout=timeout,
                       stdin=subprocess.DEVNULL)
    return (p.stdout or "") + (p.stderr or "")


def networks():
    """SSID, видимые прямо сейчас. Список неполный — это кэш (30-05)."""
    out = _netsh("show", "networks")
    return [m.group(1).strip()
            for m in re.finditer(r"^SSID\s+\d+\s*:\s*(.+)$", out, re.M)
            if m.group(1).strip()]


def add_profile(ssid, psk):
    """Добавить профиль WPA2-PSK для текущего пользователя.

    ``connectionMode=manual`` — Windows не будет подключаться сама.
    Файл с паролем удаляется сразу после добавления.
    """
    esc = (psk.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    tmp = Path(tempfile.mkdtemp(prefix="netkit-wifi-")) / "p.xml"
    tmp.write_text(_PROFILE.format(ssid=ssid, psk=esc), encoding="utf-8")
    try:
        return _netsh("add", "profile", f"filename={tmp}", "user=current")
    finally:
        try:
            tmp.unlink()
            tmp.parent.rmdir()
        except OSError:
            pass


def address(if_index, prefix=None):
    """IPv4-адрес интерфейса, опционально с проверкой префикса. '' — нет."""
    script = (
        f"(Get-NetIPAddress -InterfaceIndex {if_index} -AddressFamily IPv4 "
        f"-ErrorAction SilentlyContinue | Where-Object "
        f"{{$_.IPAddress -notlike '169.254*'}}).IPAddress"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, errors="replace",
                       timeout=25, stdin=subprocess.DEVNULL)
    for line in (p.stdout or "").splitlines():
        ip = line.strip()
        if ip and (prefix is None or ip.startswith(prefix)):
            return ip
    return ""


def connect(ssid, iface, if_index, prefix=None, attempts=5, wait=12):
    """Подключиться и дождаться адреса. Возвращает адрес или ''.

    Повторяет попытки: первая часто падает «сеть недоступна» из-за
    устаревшего кэша сканирования (30-05). Между попытками запрашивается
    список сетей — это подталкивает пересканирование.
    """
    for _ in range(attempts):
        _netsh("connect", f"name={ssid}", f"interface={iface}")
        for _ in range(wait):
            ip = address(if_index, prefix)
            if ip:
                return ip
            time.sleep(1)
        _netsh("show", "networks")
        time.sleep(3)
    return ""


def disconnect(iface):
    """Отключиться от сети."""
    return _netsh("disconnect", f"interface={iface}")


def delete_profile(ssid):
    """Удалить профиль. Вызывать после работы — в нём пароль."""
    return _netsh("delete", "profile", f"name={ssid}")


def current(iface=None):
    """Что сейчас подключено: словарь с ключами ssid, bssid, state."""
    out = _netsh("show", "interfaces")
    res = {}
    for key, pat in (("ssid", r"^\s*SSID\s*:\s*(.+)$"),
                     ("bssid", r"^\s*BSSID\s*:\s*(.+)$")):
        m = re.search(pat, out, re.M)
        if m:
            res[key] = m.group(1).strip()
    return res
