# Correções de lógica para r8q

Base revisada: `codex/r8q-sukisu-susfs`, commit
`4ed469919069f25a5632c29f8e58f079de554207`.

## Problemas corrigidos

- **MGLRU:** a expulsão de páginas incrementava `WORKINGSET_REFAULT + type`.
  Esta árvore tem contadores agregados, sem pares anon/file: a expulsão de uma
  página file acabava aumentando `WORKINGSET_ACTIVATE`. O incremento de refault
  agora ocorre no refault real, antes de filtrar gerações antigas, usando o
  contador agregado. A política de eviction e o caminho sem MGLRU não mudam.
- **RCU:** `walk_mm()` chamava `cond_resched()` antes de sair da seção de leitura
  RCU aberta por `mem_cgroup_trylock_pages()`. A liberação agora precede a
  possibilidade de scheduling voluntário, inclusive quando o trylock de mmap
  falha. Isso corrige a ordenação; não comprova que todo aparelho sofria stalls.
- **cpufreq_limit:** os setters exigiam retorno 1 de `kstrtouint()`, cujo sucesso
  é 0. Escritas válidas alteravam o estado mas retornavam erro. O código agora
  propaga falhas do parser, rejeita divisor zero e evita usar o valor não
  inicializado de `hmp_boost_type` quando a conversão falha.
- **NoMount:** ADD/DEL validam o cursor e o tamanho antes da aritmética de
  ponteiros; GET_UIDS mantém o cursor como `u32`, evitando índices negativos.
  O parser opera sobre uma cópia privada do pedido, impedindo que uma alteração
  concorrente da página do usuário burle as verificações. Falha de alocação
  informa `-ENOMEM` no status da ABI e libera os recursos adquiridos.
  A entrada exige `CAP_SYS_ADMIN`; não foi demonstrada exploração sem root.

O NoMount recebe um segundo patch incremental. O primeiro patch e o pin do
submódulo permanecem iguais, permitindo atualizar também um checkout já
preparado pela revisão anterior. Os scripts oficiais de build aplicam ambos.

## Validação executada nesta revisão

- 24 verificações do driver de frequência passaram; a versão anterior passou
  em 6 e falhou nas demais, como esperado.
- 204 verificações de MGLRU/RCU passaram. Reintroduzir cada defeito
  separadamente fez o fixture falhar.
- O harness do parser NoMount passou: offsets inválidos, cursores com bit alto,
  paginação válida, alteração concorrente simulada e limpeza de recursos.
- A sequência de aplicação dos patches foi verificada com Git nativo em
  checkout limpo, checkout com apenas o primeiro patch, repetição e reversão.

Os testes C foram compilados com TinyCC 0.9.27 para Windows. Eles extraem as
funções reais e simulam serviços do kernel; não são testes de integração do
kernel. O harness NoMount foi executado sem sanitizers neste ambiente.
Não foi feita uma compilação ARM64 completa nem teste no aparelho nesta revisão.
O build relatado no PR anterior não valida estas alterações novas.

## Reproduzir no host Linux

Requisitos: Python 3, Git, Bash e compilador C; os testes NoMount usam GCC com
AddressSanitizer/UndefinedBehaviorSanitizer.

```sh
python3 tests/test_cpufreq_limit.py
python3 tests/test_r8q_mm.py --source-root . --verify-regressions
git submodule update --init NoMount
python3 -m unittest discover -s tests -p test_nomount.py -v
```

Os dois primeiros fixtures não precisam de submódulos. `CC` seleciona o
compilador do teste de frequência; `--cc` seleciona o do teste de memória.

## Validar no r8q

```sh
JOBS=12 UFS_AXI_MHZ=300 ./build-local.sh r8q ksu
```

Ainda são necessários build completo, boot, testes de root/módulos e pressão de
memória com observação de logs RCU/lockdep em uma configuração de diagnóstico.
Conferir também leitura/escrita válida e rejeição de entradas inválidas nos
atributos alterados de cpufreq_limit. Frequências, tensões, limites térmicos e
perfis UFS permanecem nos valores da branch base. Não há medição de ganho de
bateria, temperatura ou desempenho.
