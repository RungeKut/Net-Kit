---
id: 10-01
title: SSH в RouterOS из скрипта: пароль через SSH_ASKPASS, одна строка на вызов, полный путь у каждой команды
tags: [ssh, routeros, автоматизация, openssh]
applies_to: RouterOS 7.24.4, OpenSSH 10.3p1, Windows 10
status: проверено
verified: 2026-09-28 — работало на двух роутерах, десятки вызовов подряд
source: эксперимент
---

# Неинтерактивный SSH в RouterOS

## Что происходит

RouterOS по умолчанию просит пароль с терминала. В скрипте терминала нет,
и `ssh` либо висит, либо падает. Ключи настроить правильнее, но для этого
нужен доступ к роутеру — а набор нужен как раз тогда, когда что-то сломалось.

## Как правильно

OpenSSH 8.4+ умеет брать пароль у внешней программы, если запретить ему
спрашивать с терминала:

```sh
export SSH_ASKPASS="/путь/askpass.sh"
export SSH_ASKPASS_REQUIRE=force
export DISPLAY=:0
ssh -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o NumberOfPasswordPrompts=1 \
    -o ConnectTimeout=20 \
    user@192.0.2.1 "/system resource print" < /dev/null
```

`askpass.sh` печатает пароль в stdout и больше ничего.
`DISPLAY` нужен формально — без него механизм не включается.
`< /dev/null` обязателен: иначе ssh читает stdin скрипта.

Готовая обёртка — `netkit/ros.py`, класс `Router`.

## Три особенности синтаксиса RouterOS в таком режиме

**1. Префикс пути не сохраняется между строками.** Так — нельзя:

```
/ip firewall address-list
add list=INTERNAL address=10.0.0.0/8
add list=INTERNAL address=172.16.0.0/12
```

Ответ: `bad command name add (line 1 column 1)`. Каждой команде — полный
путь, разделитель — точка с запятой:

```
/ip firewall address-list add list=INTERNAL address=10.0.0.0/8; /ip firewall address-list add list=INTERNAL address=172.16.0.0/12
```

**2. `$` — начало переменной.** В регулярке он ломает разбор:

```
/ip firewall filter remove [find comment~"^GUEST.*$"]   # syntax error
```

Искать по точному совпадению комментария:

```
/ip firewall filter remove [find comment="GUEST block local subnet"]
```

**3. Кириллица в `:put` через ssh приходит испорченной.** Для сообщений
из скрипта использовать латиницу, русский текст выводить своей программой.

## Чем подтверждено

Две первые особенности получены ошибками `bad command name add` и
`syntax error (line 1 column 1)` при попытке выполнить многострочный блок
и regex с `$`. Третья — `:put "текст"` вернул пустые символы.
