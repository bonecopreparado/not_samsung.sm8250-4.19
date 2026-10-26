# r8q: reparar a combinacao Manager/daemon

O c78ae92e iniciou. Nao e necessario recompilar para este reparo de userspace.

## Diagnostico de 25/10, 20:50

O bugreport registra Manager SukiSU 4.2.1-r2/41084 e KernelSU=-1. O daemon se
identifica como KernelSU Next e registra "UAPI version mismatch: kernel=0,
ksud=6", pulando PostFsData, Services e BootCompleted. Os eventos de boot
dos modulos nao foram executados normalmente.

O app KernelSU Next foi desinstalado as 20:49:15, mas o daemon de 7.517.352
bytes permaneceu em /data/adb/ksud. As 20:49:28 o instalador registra SukiSU
4.2.1-r2/41084. Nesse trecho nao aparece uma instalacao 40545 seguida de
atualizacao automatica; nao se conclui por que o usuario viu outra versao voltar.
NoMount ainda e 2.2.0/605, protocolo 22; o driver deste kernel usa 20.

O APK incluido foi verificado pelo AndroidManifest.xml binario:
com.sukisu.ultra, versionName=v4.1.2, versionCode=40545. O SHA-256 corresponde
ao asset oficial. O nome do arquivo nao foi a unica evidencia usada.
Nenhum log bruto do usuario foi publicado.

## 1. Instalar o APK exato

Use o [link direto 4.1.2/40545](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/download/v4.1.2/SukiSU_v4.1.2_40545-release.apk)
ou SukiSU_v4.1.2_40545-release.apk incluido aqui. No PC foi fornecida uma
copia identica chamada INSTALE-SukiSU-4.1.2-40545.apk.

Se o Android recusar o downgrade, remova somente o aplicativo SukiSU Manager
pelas Configuracoes do Android e instale o APK exato. A funcao de desinstalar
o root dentro do Manager nao e esse procedimento: pode remover modulos e
restaurar boot. O helper nao desinstala apps nem modifica seus dados.

Abra e confira v4.1.2 / 40545. Nao aceite uma atualizacao para 4.2.1 enquanto
usar esta integracao. O app KernelSU Next ja foi removido nos logs; remover
o aplicativo sozinho nao restaura o daemon.

## 2. Reparar daemon/assets com backup

Extraia o pacote completo. E um ZIP de arquivos de userspace, nao um modulo
ou ZIP para flash. Em um terminal Android com root funcional:

```sh
su
cd /sdcard/Download/r8q-SukiSU-4.1.2-reparo-v2
sh r8q-sukisu-repair.sh --check
sh r8q-sukisu-repair.sh --repair
```

Adapte o cd a pasta do descompactador. O check so le metadados e hashes;
nao executa o daemon instalado.

O reparo v2 verifica a versao e o hash do APK realmente instalado antes de
qualquer staging/backup. Se ainda detectar 41084, para sem substituir daemon.
Tambem verifica os arquivos fornecidos, exige resposta 40545 do kernel por
meio do daemon verificado e salva backup de daemon/assets. Depois executa
o install oficial e confere o hash instalado. Falha de instalacao/hash aciona
rollback. Modulos e perfis nao sao apagados.

O comando de rollback com ID aparece no final. Staging, logs e backups sao
preservados. Nao ha reboot automatico, escrita de boot/dtbo ou troca de apps.

Parsing POSIX e quatro testes de versao/hash instalado passaram no host,
com PackageManager Android simulado. A execucao completa ainda precisa ser
validada no aparelho. Instalar so o APK nao comprova troca do daemon.

## 3. Alinhar NoMount e reiniciar

Depois de o Manager reconhecer o kernel e o reparo concluir, preserve a
configuracao do metamodulo e instale pelo Manager o
[NoMount 2.0.0 oficial](https://github.com/maxsteeel/nomount/releases/download/v2.0.0/NoMount-v2.0.0-release.zip).
Ele usa protocolo 20, correspondente ao driver. O 2.2.0 usa outro tamanho
de mensagem/protocolo e nao e um par compativel.

Reinicie manualmente apos alinhar os componentes para repetir os eventos
de boot com o daemon correto. Verifique ReZygisk e LSPosed de novo.
Descricao verde de modulo nao comprova execucao; o bugreport atual tem
zygisk_running=false. O funcionamento final depende desse teste.

## Origem e hashes

Binarios oficiais inalterados do [SukiSU 4.1.2](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/tag/v4.1.2).
Fonte upstream e licenca incluidos; helper e instrucoes sao locais.

- APK: b0d75e28ef40b5e143c598f34c8f579f7daa1dfdff9c03940ea7eb215dbbc917
- Daemon ARM64: edbb762c0b28e426930b04202cb46d857e84bc9171448567ed6beb768fb57a76

O relato demonstra mistura de componentes. Nao demonstra que o arquivo
40545 fornecido se converteu em 41084, nem exige falsificar suporte GKI.
