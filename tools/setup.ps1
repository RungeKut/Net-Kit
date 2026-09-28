# Установка Net-Kit. Прав администратора не требуется.
#
# Что делает:
#   1. junction ~/.claude/skills/net -> <корень>/skill
#   2. заводит локальный tools/stoplist.txt, если его нет
#   3. включает хук commit-msg через core.hooksPath
#   4. проверяет, что автор коммитов задан ДЛЯ КЛОНА (не --global)
#
# Запускать двойным кликом по Install-skill.bat.

$ErrorActionPreference = 'Stop'
$root  = Split-Path -Parent $PSScriptRoot
$skill = Join-Path $root 'skill'
$link  = Join-Path $HOME '.claude\skills\net'
$fail  = 0

Write-Host ""
Write-Host "Net-Kit: установка" -ForegroundColor Cyan
Write-Host "  корень: $root"

# --- 1. junction ------------------------------------------------------
$skillsDir = Split-Path -Parent $link
if (-not (Test-Path $skillsDir)) {
    New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
}
if (Test-Path $link) {
    $existing = (Get-Item $link).Target
    if ($existing -and ($existing -eq $skill)) {
        Write-Host "  скилл уже подключён" -ForegroundColor Green
    } else {
        Write-Host "  по пути $link уже что-то есть: $existing" -ForegroundColor Yellow
        Write-Host "  удалить вручную и запустить снова" -ForegroundColor Yellow
        $fail = 1
    }
} else {
    cmd /c mklink /J "`"$link`"" "`"$skill`"" | Out-Null
    if (Test-Path $link) {
        Write-Host "  скилл подключён: $link" -ForegroundColor Green
    } else {
        Write-Host "  не удалось создать junction" -ForegroundColor Red
        $fail = 1
    }
}

# --- 2. стоп-лист -----------------------------------------------------
$stop = Join-Path $root 'tools\stoplist.txt'
if (-not (Test-Path $stop)) {
    $header = @(
        '# Приметы площадок ЭТОЙ машины. Файл локальный, под git не попадает',
        '# (knowledge/40_СРЕДА/40-02): лежащий в репозитории стоп-лист сам',
        '# публиковал бы то, что должен скрывать.',
        '#',
        '# Одна строка — одно слово или фрагмент, регистр не важен.',
        '# Сюда: имена SSID, логины, имена людей и устройств, доменные имена.',
        '# Адреса и MAC ловятся отдельно, по образцу — их перечислять не нужно.'
    )
    Set-Content -Path $stop -Value $header -Encoding utf8
    Write-Host "  заведён tools\stoplist.txt — вписать в него приметы площадок" -ForegroundColor Yellow
} else {
    Write-Host "  стоп-лист на месте" -ForegroundColor Green
}

# --- 3. хук -----------------------------------------------------------
Push-Location $root
try {
    git config core.hooksPath tools/hooks
    Write-Host "  хук commit-msg включён" -ForegroundColor Green

    # --- 4. автор коммитов, именно для клона --------------------------
    $name  = (git config --local user.name)  2>$null
    $email = (git config --local user.email) 2>$null
    if (-not $name -or -not $email) {
        Write-Host ""
        Write-Host "  ВНИМАНИЕ: автор коммитов не задан для этого клона." -ForegroundColor Yellow
        Write-Host "  Иначе в публичную историю уйдут глобальные рабочие имя и адрес." -ForegroundColor Yellow
        Write-Host '    git config user.name  "..."' -ForegroundColor Yellow
        Write-Host '    git config user.email "..."' -ForegroundColor Yellow
    } else {
        Write-Host "  автор коммитов: $name <$email>" -ForegroundColor Green
    }
} finally {
    Pop-Location
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "Готово. Скилл доступен как /net" -ForegroundColor Cyan
} else {
    Write-Host "Установка завершена с замечаниями." -ForegroundColor Yellow
}
Write-Host ""
exit $fail
