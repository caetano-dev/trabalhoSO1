1. Objetivo

Projetar um jogo em modo texto (ASCII) totalmente distribuído sobre processos e threads locais. O tabuleiro de $40\times20$, as barreiras, as baterias e os metadados dos robôs ficam em memória compartilhada. Cada robô (processo) lê/escreve diretamente nesse segmento, usando mecanismos de sincronização para evitar corrupção, corridas e deadlocks. Quando dois robôs se encontram, eles mesmos resolvem o duelo dentro de uma região crítica protegida.

2. Estrutura mínima

| Elemento | Implementação obrigatória |
| :------- | :------------------------ |
| Processos | $\ge4$ robôs independentes (um é o "robô do jogador", criado com atributos aleatórios). |
| Threads por robô | sense_act (decide ação) + housekeeping (atualiza energia, escreve log, opera locks). |
| Memória compartilhada | 1 segmento com: GRID[40][20] (char, #, 去, ou ID do robô), robots[] (ID, F, E, V, posição, status), flags auxiliares (init_done, vencedor, etc.). |
| Locks | grid_mutex - acesso/alteração de células; robots_mutex - alteração de atributos; battery_mutex_k - um mutex por bateria ou campo de "dono" na célula (ordem de aquisição deve ser documentada). |

3. Atributos e mecânica

| Atributo | Intervalo inicial | Observações |
| :------- | :---------------- | :---------- |
| Força (F) | $1-10$ | Define poder de ataque. |
| Energia (E) | $10-100$ | Movimentar consome 1 E; coletar +20 E (máx. 100). |
| Velocidade (V) | $1-5$ | Nº de células que o robô pode tentar mover por turno. |

Duelos corpo a corpo (robôs em células adjacentes N/S/L/O):

$Poder=2F+E$

Robô com maior Poder vence; perdedor marca status = morto e libera célula. Empate - ambos destruídos.

A negociação do duelo deve ocorrer dentro de grid_mutex, sem gerente.

4. Ciclo de vida do robô

1. Lock de inicialização:

Primeiro processo a obter init_mutex gera barreiras fixas, posiciona baterias e preenche robots[].

2. Loop principal (sense_act):

1. Tira snapshot local do grid (sem lock).
2. Decide a ação.
3. Adquire locks necessários na ordem documentada.
4. Executa ação (mover, coletar, duelar).
5. Libera locks.

3. housekeeping: de tempos em tempos reduz energia, grava log e checa condição de vitória (robôs vivos $==1$).

5. Componente de visualização (obrigatório)

Deve existir ao menos um "viewer" passivo, responsável apenas por renderizar o GRID em tempo real sem modificar o estado compartilhado.

Implementação livre:

Processo dedicado (executável viewer que mapeia o segmento em modo só leitura) ou
Thread extra no robô do jogador.

Funcionalidades mínimas:

1. A cada 50-200 ms faz um snapshot do GRID (cópia local ou pthread_rwlock_rdlock).
2. Exibe o tabuleiro em ASCII (ANSI ou ncurses).
3. Termina automaticamente quando game_over for sinalizado no segmento.
4. O jogador consegue controlar 1 robô caracterizado por 🤖 (teclas W/A/S/D ou setas) e ver o log de ações.

6. Deadlock (obrigatório) 

Provoquem um deadlock real, p. ex. dois robôs que:

1. Robô A trava battery_mutex → tenta grid_mutex.
2. Robô B trava grid_mutex → tenta battery_mutex.

O trabalho deve:

Demonstrar o deadlock em execução (logs).
Implementar prevenção, detecção ou recuperação (à escolha do grupo) e explicar no relatório.