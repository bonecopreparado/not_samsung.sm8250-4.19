# Compilar pelo Termux (r8q / S20 FE Snapdragon)

Este roteiro começa sem compilador instalado e usa Ubuntu ARM64 dentro do
Termux, via `proot-distro`. Não precisa de root para compilar. O ambiente Ubuntu
fornece as ferramentas GNU e as bibliotecas usadas pelos programas de build
do kernel. O download automático do Neutron feito pelos scripts é para Linux
x86_64; no celular, use o Clang ARM64 do Ubuntu com `TC_DIR=/usr`.

O roteiro ainda precisa de validação em um telefone real. Uma compilação que
termina sem erros também não comprova que o kernel inicia na sua ROM.

## 1. Preparar o Termux

Use uma versão atual do [Termux](https://github.com/termux/termux-app#installation),
instalada por um dos canais oficiais indicados pelo projeto. Mantenha o fonte
no armazenamento privado do Termux/Ubuntu; `/sdcard` e o armazenamento
compartilhado não preservam os links simbólicos e as permissões necessários.
Reserve espaço para Ubuntu, fonte, submódulos e os objetos do kernel; confira
`df -h` durante o processo. É recomendável começar com pelo menos 20 GB livres.

No **Termux**, execute:

```sh
pkg update
pkg upgrade
pkg install proot-distro
termux-wake-lock
proot-distro install ubuntu
proot-distro login ubuntu
```

Desative a otimização de bateria do Android para o Termux durante a compilação.
`termux-wake-lock` ajuda a manter a CPU acordada, mas o Android ainda pode encerrar
o processo quando faltar memória. Comece com dois jobs e reduza para um se isso
acontecer.

## 2. Instalar as ferramentas no Ubuntu

Os próximos comandos são executados **dentro do Ubuntu**, depois do login:

```sh
apt update
apt install -y build-essential bc bison flex libssl-dev libelf-dev \
    git ca-certificates curl jq zstd zip unzip python3 cpio rsync \
    coreutils findutils util-linux clang llvm lld \
    gcc-aarch64-linux-gnu gcc-arm-linux-gnueabi

uname -m
/usr/bin/clang --version
/usr/bin/ld.lld --version
```

No S20 FE Snapdragon, `uname -m` deve mostrar `aarch64`. Os compiladores
instalados com `apt` executam nessa arquitetura. Não extraia um Clang Linux
x86_64 no telefone: ele falha com `Exec format error`, mesmo dentro do Ubuntu.

## 3. Baixar a branch correta e compilar

Ainda dentro do Ubuntu:

```sh
cd ~
git clone --depth=1 --branch codex/sukisu-uapi6-termux \
    https://github.com/bonecopreparado/not_samsung.sm8250-4.19.git
cd not_samsung.sm8250-4.19

git branch --show-current
set -o pipefail
TC_DIR=/usr JOBS=2 UFS_AXI_MHZ=300 ./build-local.sh r8q ksu 2>&1 | tee build-r8q.log
```

A branch `codex/sukisu-uapi6-termux` contém esta atualização para teste no PR #4.
Depois de incorporada, ela também estará em `codex/r8q-sukisu-susfs`. A padrão
`staging` usa outro provedor de root. O script baixa os submódulos nos commits gravados, prepara
os patches locais, compila `Image.gz`, DTBs e `dtbo.img`, e monta o ZIP AnyKernel3.
`TC_DIR=/usr` seleciona as ferramentas do Ubuntu e evita baixar o Neutron.
O perfil UFS de 300 MHz é o padrão. Não é necessário ativar o perfil experimental
para testar a atualização do SukiSU.

Para usar a mesma entrada da CI e gerar `Image` sem compressão:

```sh
set -o pipefail
DEVICE=r8q TC_DIR=/usr JOBS=2 UFS_AXI_MHZ=300 ./build.sh 2>&1 | tee build-r8q.log
```

Escolha uma entrada por vez. Para repetir uma compilação, basta executar o
comando novamente; os objetos em `out/` são reaproveitados. Em sessões futuras,
entre novamente com `proot-distro login ubuntu` e volte à pasta do repositório.

## 4. Conferir e copiar o resultado

O sucesso termina com `Build complete:` e o caminho de um ZIP. O repositório
fica com o ZIP e os arquivos `.zip.config`, `.zip.build-info.txt` e `.zip.sha256`.
Os artefatos do kernel ficam em `out/arch/arm64/boot/`: `Image.gz` para
`build-local.sh` ou `Image` para `build.sh`, além de `dtb` e `dtbo.img`.
Use o nome exato impresso pelo build, por exemplo:

```sh
sha256sum -c NOME_DO_ARQUIVO.zip.sha256
```

O `.build-info.txt` registra o compilador, commit do fonte e dos submódulos,
e os hashes dos artefatos. Guarde esses arquivos junto com `build-r8q.log`.
Nenhum comando deste roteiro faz flash automaticamente.

Para copiar os resultados ao armazenamento compartilhado, saia do Ubuntu:

```sh
exit
termux-setup-storage
proot-distro login ubuntu --bind "$HOME/storage/downloads:/mnt/downloads"
```

Aceite a permissão de armazenamento solicitada pelo Android. Dentro do Ubuntu:

```sh
cd ~/not_samsung.sm8250-4.19
cp -- not-*.zip not-*.zip.config not-*.zip.build-info.txt not-*.zip.sha256 /mnt/downloads/
```

Esse comando copia todos os builds presentes; use os nomes exatos se quiser
copiar apenas um. Os arquivos ficam em Downloads. Depois de terminar, saia do
Ubuntu e rode `termux-wake-unlock` no Termux.

## Se falhar

- `Exec format error`: confira se está no Ubuntu ARM64 e usando `TC_DIR=/usr`.
  Um cache `tc/clang` de x86_64 não pode executar no telefone.
- `clang`/`llvm-*` ausente: repita a instalação de `clang llvm lld` dentro do
  Ubuntu; os scripts verificam as ferramentas antes de compilar.
- `Killed` ou saída 137: pode ser falta de memória. Tente `JOBS=1` e mantenha
  outros aplicativos fechados. O log do Android ajuda a confirmar a causa.
- Erro de fonte/compilação: envie `build-r8q.log`, o resultado de
  `git rev-parse HEAD` e de `/usr/bin/clang --version`. Não trate um ZIP antigo
  que já estava na pasta como resultado da tentativa que falhou.

O teste de inicialização, root e comunicação com o Manager só pode ser feito
no aparelho depois de instalar o kernel pelo procedimento apropriado à sua ROM.
