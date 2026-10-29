# Monitor de passagens GRU → PDX (ida)

Busca duas vezes por dia (12h e 20h, horário de Brasília) as opções de ida de Guarulhos para Portland em
23, 24 e 25/jan/2027 para 2 adultos, publica um painel no GitHub Pages e manda e-mail quando:

- o menor preço da ida cai pelo menos R$ 50 (configurável) em relação à rodada anterior;
- aparece pela primeira vez uma opção dentro do orçamento;
- a busca falha 2 rodadas seguidas.

## Como funciona

- `.github/workflows/monitor.yml`: agenda as rodadas e publica o painel.
- `monitor/fonte_apify.py`: busca os voos no robô "Google Flights API" da Apify. Para trocar de fonte, crie outro
  `monitor/fonte_<nome>.py` com a função `buscar_ida(cfg)` e mude `busca.fonte` no `config.toml`.
- `monitor/nota.py`: nota de "Melhor oferta" (pesos e penalidades no `config.toml`).
- `monitor/alertas.py`: e-mails pelo Gmail.
- `docs/`: o painel (`index.html`) e os dados que ele mostra (`dados.json`, `historico.json`).
- `data/rodadas/`: todas as opções encontradas em cada rodada.

## Parar o monitor

Edite `config.toml` e mude `ja_comprei = false` para `ja_comprei = true`. Ele também para sozinho depois de `data_fim`.

## Secrets necessários (Settings → Secrets and variables → Actions)

| Nome | O que é |
|---|---|
| `APIFY_TOKEN` | chave da API da Apify |
| `EMAIL_REMETENTE` | Gmail que envia os alertas |
| `EMAIL_SENHA_APP` | senha de app desse Gmail (16 letras) |
| `EMAIL_DESTINO` | e-mail que recebe os alertas |

## Testar no computador

```bash
python -m monitor.main --fonte exemplo
python -m http.server 8000 --directory docs
```
