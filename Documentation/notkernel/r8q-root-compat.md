# r8q 4.19: alinhar Manager e daemon SukiSU

O kernel `97f30708` deu boot. A captura e o bugreport mostram Manager
4.2.1-r2, `KernelSU: -1`, modo de visualizacao e um daemon de 5.126.856 bytes.
Essa combinacao nao corresponde ao SukiSU 4.1.2 integrado nesta arvore.
O kernel espera GET_INFO `0x80004b02`; os logs registram pedidos
`0x80104b02`, que sao rejeitados. Isso impede uma sessao normal de gerenciamento.

Este pacote usa somente o Manager e o daemon ARM64 oficiais **v4.1.2 / 40545**,
com SHA-256 conferido. Nao grava boot/dtbo, nao troca o kernel, nao apaga perfis
e nao remove/desativa modulos. Nao e um modulo instalavel nem ZIP para flash.
Extraia o conteudo; o script e executado em um terminal Android com root.

## Primeiro: corrigir o Manager

Instale `SukiSU_v4.1.2_40545-release.apk`. Se o Android rejeitar o downgrade,
remova **somente o aplicativo Manager** pelas Configuracoes do Android e
instale esse APK. Nao use a funcao "Uninstall" do root no aplicativo: a rotina
upstream pode remover modulos e restaurar boot.

Abra o Manager 4.1.2 e confira se reconhece o kernel. O proprio Manager so
atualiza o daemon automaticamente quando ja reconhece a interface e o app como
Manager. Apenas instalar o APK nao comprova que o daemon foi substituido.

## Diagnosticar e reparar daemon/assets

Copie a pasta extraida para Download no celular. Em um terminal com root:

```sh
su
cd /sdcard/Download/r8q-SukiSU-4.1.2-reparo
sh r8q-sukisu-repair.sh --check
```

O modo `--check` apenas le metadados e hashes. Para aplicar o reparo:

```sh
sh r8q-sukisu-repair.sh --repair
```

O reparo exige Android iniciado, modelo de bootloader r8q, kernel 4.19 e
resposta de versao **40545** consultada com o daemon verificado. Em seguida
salva backup do daemon e dos assets de `ksu/bin`, executa o `install` oficial
e confere o hash instalado. Falha de instalacao/hash aciona rollback. Os backups
e o staging ficam preservados; nao ha limpeza automatica dos dados de root.

Reinicie manualmente depois de o Manager reconhecer o kernel. Se necessario,
o comando de rollback com o identificador do backup e exibido pelo script.
O auxiliar precisa de root ja funcional; ele nao cria root a partir de um app
sem permissao, e sua execucao no aparelho ainda precisa ser validada.

## LSPosed e modulos

O bugreport ja tem ReZygisk 1.0.0/552 e LSPosed 2.2.1/7933. A descricao verde
de um modulo pode estar persistida; `zygisk_running=false` e a ausencia de
processos zygiskd/lspd no snapshot indicam que nao basta considerar o modulo
"habilitado". Primeiro alinhe Manager/daemon; depois verifique novamente o
estado do provedor Zygisk e o erro completo da instalacao do modulo.

Use **um provedor Zygisk por vez** e uma implementacao LSPosed compativel com
Android 16. O projeto JingMatrix foi renomeado para Vector e sua documentacao
declara suporte Android 8.1--17 Beta. Isso nao significa que seja necessario
trocar a implementacao LSPosed ja instalada para corrigir o problema de root.
Nao instalamos nem redistribuimos modulos de terceiros neste pacote.

O bugreport tambem mostra **NoMount 2.2.0/605**, que usa protocolo **22**,
enquanto o driver desta arvore declara **20**. As notas oficiais do 2.2.0
confirmam mudanca no tamanho das mensagens e exigem atualizar driver e
metamodulo juntos. Esse par e incompativel, independentemente do Manager.

Para este kernel, depois de corrigir Manager/daemon, instale pelo Manager o
[NoMount v2.0.0 oficial](https://github.com/maxsteeel/nomount/releases/tag/v2.0.0),
que usa protocolo **20**, e reinicie. Preserve a configuracao do metamodulo
antes da troca. Nao tente carregar os LKMs GKI do 2.2.0 neste kernel 4.19 nem
mudar apenas a string de versao do driver. O helper nao troca modulos.
A troca de metamodulo e o funcionamento final do LSPosed ainda exigem teste
no aparelho; o bugreport nao inclui o erro completo de cada instalacao.

## Fontes e hashes

- [Release oficial 4.1.2](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases/tag/v4.1.2)
- APK SHA-256: `b0d75e28ef40b5e143c598f34c8f579f7daa1dfdff9c03940ea7eb215dbbc917`
- Daemon ARM64 SHA-256: `edbb762c0b28e426930b04202cb46d857e84bc9171448567ed6beb768fb57a76`
- [Interface do kernel fixado](https://github.com/SukiSU-Ultra/SukiSU-Ultra/blob/624727d1077f5afea894f066bcb8ca70079cf802/kernel/include/uapi/supercall.h#L184)
- [Instalacao oficial do daemon/assets](https://github.com/SukiSU-Ultra/SukiSU-Ultra/blob/v4.1.2/userspace/ksud/src/utils.rs#L189)
- [Vector e requisitos de Zygisk](https://github.com/JingMatrix/Vector/blob/v2.2/README.md)
- [Requisitos do ZygiskNext](https://github.com/Dr-TSNG/ZygiskNext/blob/master/README.md)
- [Mudanca de protocolo no NoMount 2.2.0](https://github.com/maxsteeel/nomount/releases/tag/v2.2.0)

O ZygiskNext atual proibe redistribuicao; use o release oficial se decidir
utiliza-lo. Este reparo nao falsifica GKI, nao adiciona uma ABI de outro
SukiSU ao kernel e nao declara LSPosed corrigido sem novo teste no aparelho.
