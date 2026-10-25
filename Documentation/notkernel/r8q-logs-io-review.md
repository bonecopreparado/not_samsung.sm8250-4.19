# r8q: revisao dos logs e das propostas de desempenho

## Sessoes distintas nos arquivos recebidos

A captura mostra Manager SukiSU 4.2.1-r2/41084 e kernel `0e760a5f`.
`logcat(1).log`, `dmesg(1).log` e `recovery(1).log` pertencem ao OrangeFox,
com kernel proprio `39bd7e34`. O `last_kmsg(1).log` concatena sessoes antigas:

- A linha 11087 identifica o kernel Android `e6083422`.
- A linha 16111 registra bootCompleted, aproximadamente 21,7s apos o boot.
- A linha 18575 registra inicio de desligamento pelo userspace, aos 81,6s.
- Depois ha KillAllTasks/power-off e o firmware carrega o recovery.

Nao foram encontrados panic, Oops, BUG, fatal signal ou rescueparty nesse
conjunto. Isso confirma uma chegada ao Android do e608; nao comprova a ROM
exata, estabilidade prolongada ou que a captura seja dessa mesma sessao.
Fingerprint de produto pode ser alterado pela ROM/modulos e nao foi usado
como prova suficiente da ROM.

O driver e608 reconhece e autoriza o pacote do Manager nas linhas
15345--15347. Os novos arquivos nao mostram o ioctl 0x80104b02 nem o erro
de perfil vistos no bugreport anterior. Portanto nao se atribui esses
eventos antigos aos novos logs, nem se deduz a versao atual do daemon.

A integracao continua fixada na interface SukiSU 4.1.2/40545. O Manager
4.2.1 da captura continua sendo um companheiro incompatível. O APK/daemon
oficial 4.1.2 e o procedimento com backup estao descritos em
[compatibilidade de root](r8q-root-compat.md). Recompilar o kernel nao instala
outro APK nem substitui automaticamente o daemon em /data/adb.

## Correcoes pequenas e verificaveis

### Bloco: callback de timeout valido

O allocator inicializava `timeout_work` com callback NULL. Filas MQ trocam
o callback depois, mas filas bio-based de device-mapper nao passam por
essa inicializacao. `blk_sync_queue()` tenta cancelar o trabalho em ambos
os casos, chegando ao WARN_ON(!work->func) de __flush_work.

A pilha real aparece com apexd na linha 16290 e com kdmremove na 19331 do
last_kmsg. Foi restaurado o callback vazio usado pelo
[Linux 4.19.325](https://github.com/gregkh/linux/blob/v4.19.325/block/blk-core.c#L988).
O caminho MQ continua substituindo o callback por seu handler real.
O harness extrai allocator, timer, sincronizacao e inicializacao MQ reais:
14 verificacoes passaram, e recolocar NULL foi detectado.

O aviso SDFAT posterior segue a remocao do cartao SD durante desligamento.
Ele nao e evidencia de uma falha F2FS/UFS e nao foi tratado como tal.

### MGLRU: contar tentativas sem progresso

Foi removida a excecao que impedia kswapd_failures de crescer com MGLRU.
O reset por progresso real foi preservado. Isso restaura o limite de
tentativas para nos que nao conseguem liberar memoria; 148 verificacoes
passaram, e o bypass antigo foi detectado. As 204 verificacoes MM/RCU
existentes tambem passaram contra a fonte candidata.
Veja [evidencias e revisao de filesystems](r8q-mm-fs-audit.md).

### UFS: iniciar devfreq na frequencia ja selecionada

O controlador ja tinha clock registrado, mas o perfil inicial deixava
devfreq.previous_freq em zero. A primeira janela vazia ou de carga
intermediaria do simple_scaling preservava esse zero. O perfil passa a
usar clki->curr_freq, preservando a contabilidade de 300/333MHz e de clocks
baixos reais. Valor desconhecido zero e lista vazia nao viram um clock
inventado. Foram 62 verificacoes, incluindo falha de registro/limpeza;
remover a atribuicao ou fixar 300MHz provocou falha no teste.

O principio e o mesmo do [upstream 20ae4469](https://github.com/torvalds/linux/commit/20ae446921e78e4e0182cea7559d34d839550e66),
adaptado aos campos e ao fluxo desta arvore 4.19. O polling continua 60ms.
O perfil UFS333 existente muda AXI; o clock UniPro permanece 300MHz.

## Avaliacao das sugestoes fornecidas

| Proposta | Decisao nesta revisao |
| --- | --- |
| ADIOS3.3/Kyber como padrao | Sem origem inequivoca dos changelogs ou comparacao no aparelho. A build usa SSG; Kyber existe no codigo, desabilitado na configuracao. O default foi preservado. |
| GPU: intervalos e load bias | KGSL ja usa janela de chamada de 10ms. O msm_adreno_tz atualiza por eventos e ignora DEVFREQ_GOV_INTERVAL; nao foi retunado sem traces. |
| BW GPU 50->20ms | O devfreq_devbw generico nao e o parceiro GPU gpubw_mon. Alterar esse polling afetaria outros dispositivos e nao comprova beneficio a GPU. |
| MGLRU refault/kswapd/cache | Refault ja corrigido antes; contagem de falhas corrigida agora. Politica de protecao do cache nao foi alterada sem medidas. |
| F2FS NAT/checkpoint/extents | Diversas otimizacoes ja estao presentes; detalhes e commits no relatorio FS. Sem backport amplo de writeback nesta rodada. |
| Ext4/IOMAP/NOWAIT | A arvore ja tem backports. APIs novas exigem dependencias e testes de filesystem; nao foi feita troca ampla de DIO/IOMAP. |
| EROFS | Workers por CPU ja presentes. Foi identificado FIFO com prioridade zero, mas ativar RT mudaria o comportamento efetivo padrao; fica para revisao/medicao separada. |
| UFS20ms/333MHz | Contabilidade inicial corrigida. Intervalo de 60ms e tabelas de clocks preservados; 333MHz nao foi atribuido incorretamente ao UniPro. |
| DDR/memlat | Governadores e votos existentes preservados, sem aumento global de pisos sem evidencia de gargalo. |
| schedutil hold_freq | A heuristica existe upstream, com regras de idle/uclamp e contexto de versao. Nao foi copiada como garantia de melhora para este backport. |
| uclamp/FIE/pressao termica | Uclamp e pressao termica estao habilitados; a LUT Qualcomm ja foi corrigida na revisao anterior. Sem boost global de top-app ou reescrita de invariancia. |
| Limites termicos GPU | Preservados; nao ha medida que sustente elevar esses limites para este aparelho. |
| SurfaceFlinger/HWC | Componentes de userspace/HAL, fora das fontes deste repositorio de kernel. |

Referencias da arvore revisada: [KGSL](https://github.com/bonecopreparado/not_samsung.sm8250-4.19/blob/e608342226066a436627c09c170e2fd18608e237/drivers/gpu/msm/kgsl_pwrscale.c),
[governor Adreno](https://github.com/bonecopreparado/not_samsung.sm8250-4.19/blob/e608342226066a436627c09c170e2fd18608e237/drivers/devfreq/governor_msm_adreno_tz.c),
[selecao do scheduler de bloco](https://github.com/bonecopreparado/not_samsung.sm8250-4.19/blob/e608342226066a436627c09c170e2fd18608e237/block/elevator.c),
[schedutil upstream](https://github.com/torvalds/linux/blob/master/kernel/sched/cpufreq_schedutil.c).

Os changelogs foram usados como pistas, sem atribuir equivalencia a patches
cuja origem exata nao foi localizada. Os logs brutos nao foram publicados.
Os testes locais usam funcoes extraidas das fontes e shims de host, sem
hardware real. A nova build ARM64 e validacoes de carga/memoria/UFS no
aparelho ainda sao necessarias; nao ha medicao de ganho de FPS ou bateria.
