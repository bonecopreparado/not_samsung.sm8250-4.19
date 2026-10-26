#!/system/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Userland repair for the pinned SukiSU 4.1.2 / NotKernel 4.19 integration.
# Default mode only reports state. --repair changes daemon/assets after backup.
set -u

DAEMON_SHA=edbb762c0b28e426930b04202cb46d857e84bc9171448567ed6beb768fb57a76
APK_SHA=b0d75e28ef40b5e143c598f34c8f579f7daa1dfdff9c03940ea7eb215dbbc917
APK_NAME=SukiSU_v4.1.2_40545-release.apk
EXPECTED_KERNEL_VERSION=40545
EXPECTED_MANAGER_VERSION=40545
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
MODE=${1:---check}
DAEMON=/data/adb/ksud
BIN=/data/adb/ksu/bin
BACKUP_BASE=/data/adb/r8q-sukisu-backups
BACKUP=
LOCK=/data/adb/.r8q-sukisu-repair-lock

fail() { echo "ERRO: $*" >&2; exit 1; }
hash_file() { sha256sum "$1" | awk '{print $1}'; }
check_installed_manager() {
    local version installed_apk
    version=$(dumpsys package com.sukisu.ultra 2>/dev/null |
        awk '$1 ~ /^versionCode=/ {split($1, v, "="); print v[2]; exit}')
    [ "$version" = "$EXPECTED_MANAGER_VERSION" ] ||
        fail "Manager instalado: ${version:-ausente}; esperado 40545. Instale o APK 4.1.2 exato. Nenhum daemon foi substituido."
    installed_apk=$(pm path com.sukisu.ultra 2>/dev/null | sed -n 's/^package://p' | head -n 1)
    [ -f "$installed_apk" ] || fail "Nao foi possivel conferir o APK efetivamente instalado."
    [ "$(hash_file "$installed_apk")" = "$APK_SHA" ] ||
        fail "O APK instalado nao corresponde ao release oficial 4.1.2 verificado. Nenhum daemon foi substituido."
    echo "Manager instalado conferido: v4.1.2 / 40545, SHA-256 correto."
}
acquire_lock() {
    mkdir "$LOCK" 2>/dev/null || fail "Outro reparo pode estar ativo; verifique $LOCK antes de tentar novamente."
    trap 'rmdir "$LOCK" 2>/dev/null || true' 0
    trap 'exit 130' 2
    trap 'exit 143' 15
}

report() {
    echo "Kernel: $(uname -r)"
    echo "Modelo do bootloader: $(getprop ro.boot.em.model 2>/dev/null)"
    echo "SELinux: $(getenforce 2>/dev/null)"
    echo "Manager instalado:"
    dumpsys package com.sukisu.ultra 2>/dev/null | grep -E 'versionCode=|versionName=' | head -n 4
    echo "Daemon e link:"
    ls -lZ "$DAEMON" "$BIN/ksud" 2>/dev/null || true
    if [ -r "$DAEMON" ] && command -v sha256sum >/dev/null 2>&1; then
        CURRENT_SHA=$(hash_file "$DAEMON")
        echo "SHA-256 atual: $CURRENT_SHA"
        if [ "$CURRENT_SHA" = "$DAEMON_SHA" ]; then
            echo "Daemon corresponde ao release oficial 4.1.2."
        else
            echo "Daemon diferente do release 4.1.2 esperado por esta integracao."
        fi
    fi
    echo "NoMount instalado (esta arvore usa protocolo 20 / modulo 2.0.0):"
    if [ -r /data/adb/modules/nomount/module.prop ]; then
        grep -E '^version=|^versionCode=' /data/adb/modules/nomount/module.prop
    fi
    echo "Este script nao executa o daemon instalado no modo --check."
}

restore_backup() {
    [ -d "$BACKUP" ] && [ -f "$BACKUP/backup-complete" ] || return 1
    SAVE="$BACKUP/after-rollback-$(date +%Y%m%d-%H%M%S)-$$"
    mkdir "$SAVE" || return 1
    if [ -e "$DAEMON" ] || [ -L "$DAEMON" ]; then
        mv "$DAEMON" "$SAVE/ksud" || return 1
    fi
    if [ -e "$BIN" ] || [ -L "$BIN" ]; then
        mv "$BIN" "$SAVE/bin" || return 1
    fi
    if [ -f "$BACKUP/had-daemon" ]; then
        cp -a "$BACKUP/ksud" "$DAEMON" || return 1
        if [ -s "$BACKUP/daemon-context" ]; then
            OLD_CONTEXT=$(cat "$BACKUP/daemon-context")
            chcon "$OLD_CONTEXT" "$DAEMON" || return 1
        fi
    fi
    if [ -f "$BACKUP/had-bin" ]; then
        cp -a "$BACKUP/bin" "$BIN" || return 1
    fi
    echo "Backup restaurado; arquivos posteriores preservados em $SAVE"
}

case "$MODE" in
    --check) report; exit 0 ;;
    --repair) ;;
    --rollback)
        [ "$(id -u)" = 0 ] || fail "Execute como root."
        ID=${2:-}
        case "$ID" in ''|*[!0-9-]*) fail "Use o identificador de backup exibido pelo reparo." ;; esac
        BACKUP="$BACKUP_BASE/$ID"
        [ ! -L "$BACKUP_BASE" ] && [ ! -L "$BACKUP" ] || fail "Backup com link simbolico nao aceito."
        for DIR in /data/adb /data/adb/ksu "$BIN"; do
            [ ! -L "$DIR" ] || fail "Diretorio com link simbolico inesperado: $DIR"
        done
        acquire_lock
        restore_backup || fail "Falha ao restaurar backup; preserve os arquivos para diagnostico."
        exit 0
        ;;
    *) fail "Uso: sh r8q-sukisu-repair.sh [--check|--repair|--rollback ID]" ;;
esac

[ "$(id -u)" = 0 ] || fail "Execute em um terminal com root, usando su."
[ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] || fail "Use este reparo no Android ja iniciado, nao no recovery."
case "$(uname -r)" in 4.19.*) ;; *) fail "Este reparo e para a integracao 4.19 do r8q." ;; esac
case "$(getprop ro.boot.em.model 2>/dev/null)" in
    SM-G780G|SM-G781*) ;;
    *) fail "Modelo do bootloader nao corresponde ao r8q suportado."
esac
for DIR in /data/adb /data/adb/ksu "$BIN" "$BACKUP_BASE"; do
    [ ! -L "$DIR" ] || fail "Diretorio com link simbolico inesperado: $DIR"
done
[ ! -L "$DAEMON" ] || fail "O daemon principal nao pode ser um link simbolico."
for CMD in sha256sum awk cp chmod chcon mv mkdir rmdir date touch cat sed tr readlink head pm dumpsys; do
    command -v "$CMD" >/dev/null 2>&1 || fail "Comando ausente: $CMD"
done
check_installed_manager
SOURCE="$SCRIPT_DIR/ksud-aarch64-linux-android"
[ -f "$SOURCE" ] || fail "Extraia o pacote completo junto com o script."
[ "$(hash_file "$SOURCE")" = "$DAEMON_SHA" ] || fail "SHA-256 do daemon nao confere."
[ -f "$SCRIPT_DIR/$APK_NAME" ] || fail "O APK 4.1.2 deve estar no mesmo pacote."
[ "$(hash_file "$SCRIPT_DIR/$APK_NAME")" = "$APK_SHA" ] || fail "SHA-256 do APK nao confere."
if [ -e "$BIN/ksud" ] || [ -L "$BIN/ksud" ]; then
    [ -L "$BIN/ksud" ] && [ "$(readlink "$BIN/ksud")" = "$DAEMON" ] ||
        fail "Link auxiliar ksud inesperado; revise manualmente."
fi

acquire_lock

STAMP="$(date +%Y%m%d-%H%M%S)-$$"
STAGE="/data/local/tmp/r8q-sukisu-4.1.2-$STAMP"
[ ! -e "$STAGE" ] || fail "Diretorio temporario ja existe."
mkdir "$STAGE" || fail "Nao foi possivel criar staging."
chmod 700 "$STAGE" || fail "Nao foi possivel proteger staging."
cp "$SOURCE" "$STAGE/ksud" && chmod 755 "$STAGE/ksud" || fail "Falha ao preparar daemon verificado."
chcon u:object_r:adb_data_file:s0 "$STAGE/ksud" || fail "Falha no contexto SELinux do staging."
VERSION_OUTPUT=$("$STAGE/ksud" debug version 2>&1) || fail "O daemon verificado nao consultou o kernel."
printf '%s\n' "$VERSION_OUTPUT"
KERNEL_VERSION=$(printf '%s\n' "$VERSION_OUTPUT" | sed -n 's/^Kernel Version: //p' | tr -d '\r')
[ "$KERNEL_VERSION" = "$EXPECTED_KERNEL_VERSION" ] ||
    fail "A interface do kernel nao retornou 40545. Nenhum daemon foi substituido."

BACKUP="$BACKUP_BASE/$STAMP"
[ ! -e "$BACKUP" ] || fail "Backup ja existe."
mkdir -p "$BACKUP" || fail "Nao foi possivel criar backup."
chmod 700 "$BACKUP_BASE" "$BACKUP" || fail "Nao foi possivel proteger backup."
if [ -e "$DAEMON" ]; then
    [ -f "$DAEMON" ] || fail "Daemon atual nao e arquivo regular."
    cp -a "$DAEMON" "$BACKUP/ksud" || fail "Falha no backup do daemon."
    ls -Zd "$DAEMON" | awk '{for (i=1;i<=NF;i++) if ($i ~ /^u:object_r:/) {print $i; exit}}' > "$BACKUP/daemon-context"
    touch "$BACKUP/had-daemon" || fail "Falha no marcador do backup."
fi
if [ -d "$BIN" ]; then
    cp -a "$BIN" "$BACKUP/bin" || fail "Falha no backup dos assets."
    touch "$BACKUP/had-bin" || fail "Falha no marcador do backup."
fi
report > "$BACKUP/before.txt" 2>&1
touch "$BACKUP/backup-complete" || fail "Backup incompleto."
echo "Backup completo: $BACKUP"
echo "Instalando daemon/assets oficiais 4.1.2..."
if ! "$STAGE/ksud" install > "$BACKUP/install.log" 2>&1; then
    cat "$BACKUP/install.log"
    restore_backup || fail "Instalacao falhou e rollback incompleto. Backup: $BACKUP"
    fail "Instalacao falhou; estado anterior restaurado."
fi
if [ "$(hash_file "$DAEMON")" != "$DAEMON_SHA" ]; then
    restore_backup || fail "Hash inesperado e rollback incompleto. Backup: $BACKUP"
    fail "Hash inesperado; estado anterior restaurado."
fi
report > "$BACKUP/after.txt" 2>&1
echo "Daemon/assets 4.1.2 instalados. Modulos e perfis foram preservados."
echo "Instale o APK 4.1.2 fornecido e confira reconhecimento do kernel no Manager."
echo "Reinicie manualmente para repetir os eventos de boot com o daemon correto."
echo "Rollback, se necessario: sh $0 --rollback $STAMP"
echo "Staging e backup foram preservados para diagnostico."
