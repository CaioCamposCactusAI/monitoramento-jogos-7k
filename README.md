# Monitoramento de Jogos - 7K Bet

Robô automatizado para verificar se os jogos da plataforma 7K estão operacionais, capturando screenshots dos iframes como evidência.

## Pré-requisitos

- Python 3.10+
- Google Chrome instalado

## Instalação

```bash
pip install -r requirements.txt
playwright install chromium
```

## Configuração

1. Edite as credenciais em `config.py` (ou defina variáveis de ambiente `EMAIL` e `SENHA`):
```python
EMAIL = os.environ.get("EMAIL", "seu_email@exemplo.com")
SENHA = os.environ.get("SENHA", "sua_senha_aqui")
```

2. Configure os jogos a serem verificados no `input.json`:
```json
[
  {
    "nome_jogo": "Fortune Rabbit",
    "provedora": "PG Soft",
    "brand": "7k",
    "link": "https://7k.bet.br/games/pgsoft/fortune-rabbit"
  }
]
```

## Execução

```bash
python monitor.py
```

## Funcionamento

1. Abre o navegador e acessa a plataforma 7K
2. Realiza login automaticamente
3. Processa os jogos em lotes de 3 abas simultâneas
4. Aguarda 15 segundos para cada jogo carregar
5. Captura screenshot do iframe do jogo
6. Salva evidências na pasta `game_evidence/`
7. Gera relatório JSON com status de cada jogo

## Estrutura de saída

```
game_evidence/
├── Fortune_Rabbit_PG_Soft_20260320_120000.png
├── Aviator_Spribe_20260320_120000.png
├── ...
└── relatorio_20260320_120000.json
```

## Status possíveis

- **operacional**: Jogo carregou corretamente e iframe foi capturado
- **sem_iframe**: Página carregou mas o iframe do jogo não foi encontrado
- **erro**: Falha ao carregar o jogo (timeout, erro de rede, etc.)
