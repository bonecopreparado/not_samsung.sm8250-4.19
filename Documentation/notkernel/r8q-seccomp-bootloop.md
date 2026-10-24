# r8q: seccomp ausente na build 4172302f

## Falha demonstrada

A configuração final fornecida com a build `4172302f` contém
`# CONFIG_SECCOMP is not set`. No mesmo commit, o caminho sem seccomp de
`include/linux/seccomp.h` devolve `-EINVAL` em `prctl_set_seccomp()`.

Os tombstones mais recentes do pacote enviado pelo mantenedor mostram
`media.codec`, `mediaextractor`, `mediaswcodec` e `samsung.software.media.c2`
abortando em `libminijail -> minijail_enter -> do_fatal_log`. Os bytes da pilha
do tombstone 20, PID 3362, contêm a mensagem de falha de
`prctl(seccomp_filter)` com `Invalid argument`.

Os PIDs 3289, 3362, 3346 e 3370 dos tombstones 19--22 também aparecem na
tentativa de boot de `4172302f` no `last_kmsg` desse pacote, imediatamente
antes do bootchecker solicitar a reinicialização. Isso vincula os crashes
recentes à build em análise. Os registros mais antigos do Dropbox citam
outro kernel, Shadow, e foram considerados separadamente.

## Correção

O fragmento de r8q passa a solicitar `CONFIG_SECCOMP=y` e
`CONFIG_SECCOMP_FILTER=y` para todas as variantes. A árvore ARM64 já oferece
`HAVE_ARCH_SECCOMP_FILTER` e a configuração de plataforma habilita `NET`,
dependências necessárias ao filtro nesta árvore. A mudança habilita o sandbox
esperado pelos processos Android.

O script compartilhado exige ambas as opções na `.config` final do r8q,
depois de `olddefconfig` e antes de compilar/empacotar. O teste de host
exercita a rejeição de configurações incompletas nas três variantes e mantém
o escopo da nova checagem restrito ao r8q.

## Limites da validação

Essa é uma incompatibilidade confirmada com os serviços nativos registrados.
Não há um tombstone direto do `system_server` no pacote; uma nova compilação
e teste no aparelho ainda são necessários para verificar se esta era a única
causa do bootloop.

O build completo conhecido de `4172302f` antecede esta correção e falhou no
teste de boot. A revisão com seccomp precisa de seu próprio build completo.
Os arquivos Python e o código Python dos fixtures foram verificados
sintaticamente; a suíte Bash de build não foi executada neste Windows. O
notebook atualizado inclui sua execução no Linux antes da compilação.

A incompatibilidade de ABI do daemon `ksud` observada nos logs anteriores
é uma questão separada; ativar seccomp não migra daemon, Manager ou perfis.

## Reproduzir

```sh
python3 -m unittest discover -s tests -p test_not_build.py -v
JOBS=4 UFS_AXI_MHZ=300 ./build-local.sh r8q ksu
grep -E '^CONFIG_SECCOMP(_FILTER)?=' out/.config
```

O último comando deve mostrar as duas opções com valor `y`.
