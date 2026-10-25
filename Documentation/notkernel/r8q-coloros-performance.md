# r8q: instalador em ports ColorOS e perfis de desempenho

## Falha identificada

O log de 25/10/2026 termina em `Checking device... Unsupported device`.
O AnyKernel3 verifica quatro nomes Android e aceita apenas `r8q`; ele ainda
nao executou `anykernel.sh`, `split_boot`, `flash_generic dtbo` ou `flash_boot`.
Portanto essa tentativa nao demonstra um bootloop do novo kernel.

A captura do mantenedor confirma:

```text
ro.boot.em.model=SM-G780G
ro.boot.bootloader=G780GXXSGEYH1
ro.product.device=OP5D0DL1
ro.board.platform=kona
```

O alvo informado e ColorOS 16.1/16.0.10, port de OnePlus 13 para S20 FE/r8q.
O nome de produto do doador explica a rejeicao. O anuncio da ROM ja lista
FOD, NFC e possivel falha de SMS; corrigir o gate nao corrige esses componentes.

## Correcao do gate

`prepare-r8q-anykernel.py` preserva a verificacao original e acrescenta um
fallback exclusivo do pacote r8q, antes do abort. O fallback exige:

- Par de modelo/bootloader Samsung EUR: SM-G780G/G780G ou SM-G781B/G781B.
- Device tree Samsung R8Q/SM-G781B e compatible kona/SM8250.
- Plataforma kona, se a propriedade estiver disponivel, e a particao de boot
  esperada pelo proprio template r8q.

Os nomes genericos Oppo/OnePlus nao entram na allowlist. Exynos, variantes
regionais nao estabelecidas pelo alvo EUR e provas ausentes/contraditorias
sao rejeitados pelo fallback. Uma rejeicao imprime os IDs usados para
permitir diagnostico. O preparador exige o update-binary testado do pin
AnyKernel3 `88a81141d54934af9f8407be913c21aed5f51026`, preserva o gate
do.devicecheck=1 e rejeita um template desconhecido ou helper conflitante.
O build registra os hashes do overlay local no manifest.

Esta alteracao estabelece elegibilidade de instalacao. Boot, FOD, toque,
camera, NFC, SMS, carga e modulos ainda precisam de teste nessa ROM. O
comportamento existente de `android.is_aosp` foi preservado: ele controla
caminhos de FOD/display/toque, nao e um seletor geral de ABI ColorOS.

## Desempenho e overclock

O perfil padrao permanece `balanced`: os pisos por cluster existentes e
janela de input de 300ms. Para testar uma resposta ao toque mais agressiva:

```sh
R8Q_PERF_PROFILE=burst UFS_AXI_MHZ=300 JOBS=4 ./build-local.sh r8q ksu
```

`burst` pede o teto atual de cada politica de CPU por 80ms apos input. Toques
continuos renovam a janela; isso pode aumentar consumo/calor e nao garante
FPS sustentado. `policy->max` conserva os limites ativos de politica e
controle termico. Nao sao criados clocks/tensoes novos. O nome do ZIP e o
manifest distinguem o perfil; a configuracao final do burst e conferida
antes de compilar. Voltar a balanced restaura explicitamente o padrao.

A opcao existente `UFS_AXI_MHZ=333` continua separada e experimental. Ela
altera o clock AXI do UFS, nao e overclock de CPU/GPU nem garante ganho de
armazenamento. O notebook deixa 300MHz como ponto inicial para testar o port.

O driver Qualcomm le frequencias e tensoes de uma LUT de hardware e escreve
indices nela. A whitelist DT de CPU ja inclui ate 3091200kHz no prime, mas
isso nao cria uma linha ausente no hardware. O teto da GPU e selecionado
pelo speed bin: a tabela comum tem 840MHz no bin0 e tetos menores nos outros
bins. Nao ha base para prometer esses clocks em todo SM8250. Os tetos reais
devem ser lidos no aparelho, sem editar OPPs de outro bin ou protecoes.

Tambem foi corrigido `last_non_boost_freq` no driver Qualcomm: o seletor
agora ignora entradas invalidadas pelo filtro DT e calcula o maior clock
valido sem flag boost. Antes, uma entrada invalida podia virar o limite de
referencia usado pela informacao de pressao termica do scheduler. O caso
foi reproduzido no harness; nao foi demonstrado na LUT fisica deste tester.

## Validacao

- Sete testes do gate/preparador passaram com BusyBox no Windows, executando
  a funcao real do update-binary com entradas Android simuladas, incluindo
  os valores enviados pelo mantenedor e 13 cenarios de rejeicao.
- 24 verificacoes dos perfis e 13 da LUT passaram com TinyCC. Duas mutacoes
  do perfil e o loop antigo da LUT foram detectados.
- As 205 verificacoes de boost e 11 de duracao zero existentes passaram.
- O shell foi analisado e o Python/notebook teve sintaxe conferida.

As fontes novas ainda precisam de build ARM64 e testes no aparelho. A suite
de build Linux foi ampliada para conferir o overlay, os perfis e o retorno
ao padrao; sua execucao completa fica no Colab antes da build.

O ZIP reempacotado a partir de `0e760a5f` muda somente o instalador. Ele
mantem Image.gz, DTB e DTBO identicos ao pacote que ja compilou e nao inclui
as alteracoes novas de LUT/perfil, que exigem recompilacao.
