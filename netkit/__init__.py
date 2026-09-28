"""Net-Kit — работа с сетями MikroTik скриптами.

Три модуля:

* ``ros``   — команды на роутере по SSH без интерактивного ввода пароля.
* ``probe`` — проверки связности с привязкой к адресу источника, чтобы
              трафик гарантированно ушёл через нужный интерфейс.
* ``wifi``  — переключение сетей Wi-Fi в Windows без прав администратора.

База знаний — ``knowledge/INDEX.md``. Карты конкретных сетей — ``local/``.
"""

from .ros import Router, RosError
from . import probe, wifi

__all__ = ["Router", "RosError", "probe", "wifi"]
