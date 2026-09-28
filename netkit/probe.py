"""Проверки связности С ПРИВЯЗКОЙ к адресу источника.

Зачем привязка. Проверка, идущая не тем путём, ничего не доказывает: на
машине с двумя интерфейсами трафик уходит туда, где метрика меньше, а
прав администратора для смены метрик может не быть.

Windows использует strong host model — сокет, привязанный к адресу
интерфейса, отправляет только через него. Это и выбирает путь, без
повышения прав (knowledge/20_ПРИЁМЫ/20-03).

ОГОВОРКА: привязка работает, пока цель достижима через этот интерфейс.
Подключённая сеть, покрывающая адрес назначения, перехватит трафик
независимо от намерений (knowledge/30_ГРАБЛИ/30-09). Поэтому результат
подтверждать со стороны роутера — счётчиками или conntrack.
"""

from __future__ import annotations

import re
import subprocess

_PS = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

# Консоль Windows отдаёт CP866, и кириллица в именах интерфейсов приходит
# испорченной. Переключаем вывод PowerShell на UTF-8 в самой команде.
_UTF8 = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "


def _run(args, timeout=40, encoding=None):
    """Запустить команду и вернуть весь её вывод одной строкой.

    encoding задаётся явно для вызовов PowerShell: они переключены на
    UTF-8 через _UTF8, а Python по умолчанию декодирует локальной
    кодировкой и портит кириллицу в именах интерфейсов. Нативным
    утилитам (ping, curl) кодировка не важна — из их вывода берутся
    только латиница и цифры.
    """
    p = subprocess.run(args, capture_output=True, timeout=timeout,
                       stdin=subprocess.DEVNULL)
    enc = encoding or "utf-8"
    out = (p.stdout or b"") + (p.stderr or b"")
    return out.decode(enc, errors="replace")


def ping(src, target, count=4, wait_ms=2500):
    """ICMP с привязкой. Возвращает число полученных ответов (int).

    0 сам по себе ничего не доказывает: цель может не существовать или
    не отвечать своим фаерволом. Нужен контрольный опыт
    (knowledge/20_ПРИЁМЫ/20-04).
    """
    out = _run(["ping", "-S", src, "-n", str(count), "-w", str(wait_ms),
                target], timeout=count * (wait_ms / 1000) + 25)
    # Считаем строки ответов по "TTL=" — она есть и в русском, и в
    # английском выводе. Разбор итоговой статистики регуляркой ненадёжен:
    # она цепляет строку со временем отклика и возвращает мусор.
    return len(re.findall(r"TTL\s*=", out, re.I))


def tcp(src, target, port, timeout_ms=5000):
    """TCP-подключение с привязкой. True — порт открыт.

    Делается через .NET TcpClient с локальным IPEndPoint: Test-NetConnection
    задавать источник не умеет.
    """
    script = (
        f"try {{ "
        f"$l = New-Object Net.IPEndPoint([Net.IPAddress]::Parse('{src}'),0); "
        f"$c = New-Object Net.Sockets.TcpClient($l); "
        f"$i = $c.BeginConnect('{target}',{port},$null,$null); "
        f"if ($i.AsyncWaitHandle.WaitOne({timeout_ms},$false) -and $c.Connected)"
        f" {{ $c.EndConnect($i); 'OPEN' }} else {{ 'SHUT' }}; $c.Close() }} "
        f"catch {{ 'SHUT' }}"
    )
    return "OPEN" in _run(_PS + [_UTF8 + script], timeout=timeout_ms / 1000 + 25,
                encoding="utf-8")


def dns(src, server, name="example.com", timeout_ms=5000):
    """DNS-запрос A-записи с привязкой. True — сервер ответил.

    nslookup привязку не умеет, поэтому запрос собирается вручную.
    Важен сам факт ответа, а не его содержимое.
    """
    labels = name.split(".")
    qname = "".join(
        f"+[byte[]]@({len(l)})+[Text.Encoding]::ASCII.GetBytes('{l}')"
        for l in labels
    )
    script = (
        f"try {{ "
        f"$u = New-Object Net.Sockets.UdpClient("
        f"New-Object Net.IPEndPoint([Net.IPAddress]::Parse('{src}'),0)); "
        f"$u.Client.ReceiveTimeout = {timeout_ms}; "
        f"$q = [byte[]]@(0x12,0x34,1,0,0,1,0,0,0,0,0,0){qname}+[byte[]]@(0,0,1,0,1); "
        f"[void]$u.Send($q,$q.Length,'{server}',53); "
        f"$e = New-Object Net.IPEndPoint([Net.IPAddress]::Any,0); "
        f"$r = $u.Receive([ref]$e); 'ANSWER'; $u.Close() }} catch {{ 'SILENT' }}"
    )
    return "ANSWER" in _run(_PS + [_UTF8 + script], timeout=timeout_ms / 1000 + 25,
                encoding="utf-8")


def http(src, url, timeout=20):
    """HTTP(S) с привязкой. Возвращает код ответа (int), 0 — не дошло.

    --noproxy '*' ОБЯЗАТЕЛЕН: без него curl молча уходит в http_proxy из
    окружения, обходит привязку и возвращает ложный успех
    (knowledge/30_ГРАБЛИ/30-06).
    """
    out = _run(["curl", "-s", "--noproxy", "*", "--interface", src,
                "-o", "/dev/null", "-w", "%{http_code}",
                "--max-time", str(timeout), url], timeout=timeout + 15)
    m = re.search(r"(\d{3})\s*$", out.strip())
    return int(m.group(1)) if m else 0


def route_to(target):
    """Через какой интерфейс машина реально отправит пакет.

    Проверять до измерения: если интерфейс не тот, измерение
    не состоится (knowledge/30_ГРАБЛИ/30-09).
    """
    out = _run(_PS + [_UTF8 +
        f"(Find-NetRoute -RemoteIPAddress {target} | Select-Object -First 1)."
        f"IPAddress"
    ], encoding="utf-8")
    return out.strip()


def addresses():
    """Список (адрес, имя интерфейса, индекс) без link-local."""
    out = _run(_PS + [_UTF8 +
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object {$_.IPAddress -notlike '169.254*'} | "
        "ForEach-Object { \"$($_.IPAddress)`t$($_.InterfaceAlias)`t"
        "$($_.InterfaceIndex)\" }"
    ], encoding="utf-8")
    rows = []
    for line in out.splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 3 and parts[0]:
            rows.append((parts[0], parts[1], int(parts[2])))
    return rows
