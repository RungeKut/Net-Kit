"""Команды на MikroTik RouterOS по SSH без интерактивного ввода пароля.

Пароль передаётся механизмом ``SSH_ASKPASS`` OpenSSH 8.4+: ssh запускает
внешнюю программу, которая печатает пароль. Нужны три переменные сразу —
``SSH_ASKPASS``, ``SSH_ASKPASS_REQUIRE=force`` и ``DISPLAY``; без
последней механизм не включается (knowledge/10_API/10-01).

Особенности синтаксиса RouterOS в неинтерактивном режиме, учтённые здесь:

* префикс пути НЕ сохраняется между строками — каждой команде нужен
  полный путь, несколько команд разделяются ``;``;
* ``$`` в регулярках ломает разбор — искать по точному комментарию;
* кириллица в ``:put`` приходит испорченной.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


class RosError(RuntimeError):
    """Команда не выполнилась: ssh вернул ошибку или не смог подключиться."""


_SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "NumberOfPasswordPrompts=1",
]


class Router:
    """Роутер, доступный по SSH.

    Пароль берётся, в порядке убывания приоритета, из ``password``,
    из файла ``pw_file`` или из переменной окружения ``NETKIT_PW``.

    Файл с паролем живёт не дольше работы: держать его в ``local/`` и
    удалять после (knowledge/40_СРЕДА/40-03). Правильнее — SSH-ключи,
    тогда ни пароль, ни этот механизм не нужны: вызов всё равно
    отработает, просто askpass не понадобится.
    """

    def __init__(self, host, user, password=None, pw_file=None, timeout=25):
        self.host = host
        self.user = user
        self.timeout = timeout
        self._pw = password
        if self._pw is None and pw_file:
            self._pw = Path(pw_file).read_text(encoding="utf-8").strip()
        if self._pw is None:
            self._pw = os.environ.get("NETKIT_PW")
        self._askpass_dir = None

    # --- внутреннее ---------------------------------------------------

    def _env(self):
        env = dict(os.environ)
        if not self._pw:
            return env
        if self._askpass_dir is None:
            d = Path(tempfile.mkdtemp(prefix="netkit-"))
            (d / "pw").write_text(self._pw + "\n", encoding="utf-8")
            script = d / "askpass.sh"
            script.write_text(
                '#!/bin/sh\ncat "$(dirname "$0")/pw"\n', encoding="utf-8"
            )
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            self._askpass_dir = d
        env["SSH_ASKPASS"] = str(self._askpass_dir / "askpass.sh")
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env.setdefault("DISPLAY", ":0")
        return env

    def close(self):
        """Удалить временный файл с паролем. Вызывать по окончании работы."""
        if self._askpass_dir:
            shutil.rmtree(self._askpass_dir, ignore_errors=True)
            self._askpass_dir = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- основное -----------------------------------------------------

    def cmd(self, command):
        """Выполнить команду RouterOS и вернуть вывод строкой.

        Несколько команд разделять ``;`` В ОДНОЙ строке — многострочный
        блок с общим префиксом пути не работает (10-01).
        """
        args = ["ssh", *_SSH_OPTS, "-o", f"ConnectTimeout={self.timeout}",
                f"{self.user}@{self.host}", command]
        p = subprocess.run(args, env=self._env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, errors="replace",
                           timeout=self.timeout + 20)
        out = (p.stdout or "") + (p.stderr or "")
        out = "\n".join(l for l in out.splitlines()
                        if not l.startswith("Warning: Permanently added"))
        if p.returncode != 0 and "denied" in out.lower():
            raise RosError(f"{self.host}: не пускает — {out.strip()[:200]}")
        return out.strip()

    def export(self, name="osmotr", dest=".", remove_remote=True):
        """Сделать /export, забрать файл к себе и удалить его с роутера.

        Осмотр начинается отсюда, а не с серии print: только в выгрузке
        видны /routing rule, arp=reply-only, шейперы и списки доступа
        Wi-Fi (knowledge/10_API/10-02).

        На младших платах свободно меньше мегабайта, поэтому файл с
        роутера по умолчанию удаляется.
        """
        self.cmd(f"/export file={name}")
        local = Path(dest) / f"{name}.rsc"
        local.parent.mkdir(parents=True, exist_ok=True)
        args = ["scp", *_SSH_OPTS, f"{self.user}@{self.host}:{name}.rsc",
                str(local)]
        p = subprocess.run(args, env=self._env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, errors="replace",
                           timeout=self.timeout + 40)
        if not local.exists():
            raise RosError(f"не удалось забрать выгрузку: {p.stderr[:200]}")
        if remove_remote:
            self.cmd(f'/file remove [find name="{name}.rsc"]')
        return local

    # --- измерения ----------------------------------------------------

    def reset_counters(self):
        """Обнулить счётчики правил. Ничего не ломает, разрешено без спроса."""
        self.cmd("/ip firewall filter reset-counters-all")

    def counters(self, chain=None, where=None):
        """Счётчики правил фаервола.

        ВАЖНО: разрешённый по умолчанию трафик не увеличивает ни один
        счётчик. «Все drop по нулям» значит «ничего не заблокировано»,
        а не «трафика не было». Различить можно только по conntrack
        (knowledge/10_API/10-03, 10-04).
        """
        q = "/ip firewall filter print stats"
        if chain:
            q += f" where chain={chain}"
        elif where:
            q += f" where {where}"
        return self.cmd(q)

    def connections(self, where=None):
        """Таблица отслеживания соединений.

        Запись создаётся в prerouting, ДО фильтра: она доказывает, что
        пакет дошёл до роутера, даже если потом был отброшен. Флаг S
        (SEEN-REPLY) отличает полученный ответ от тишины (10-04).
        """
        q = "/ip firewall connection print"
        if where:
            q += f" where {where}"
        return self.cmd(q)

    def version(self):
        """Строка «модель RouterOS версия» — то, что идёт в applies_to."""
        board = self.cmd(":put [/system resource get board-name]")
        ver = self.cmd(":put [/system resource get version]")
        return f"{board.strip()} RouterOS {ver.strip()}"
