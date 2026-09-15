# sales-metrics-api

![tests](https://github.com/Luis-eduardo-f/sales-metrics-api/actions/workflows/tests.yml/badge.svg)
![license](https://img.shields.io/github/license/Luis-eduardo-f/sales-metrics-api)
![python](https://img.shields.io/badge/python-3.11%2B-blue)

API de analytics em **Python + FastAPI + SQLAlchemy**, servindo métricas agregadas (receita ao longo do tempo, produtos mais vendidos, histórico de clientes) sobre um dataset sintético de vendas — o foco não é CRUD, e sim consultas analíticas rápidas, autenticadas e cacheadas sobre dados relacionais. O projeto roda localmente sem nenhuma infraestrutura externa (SQLite) e é "Postgres-ready" via `docker-compose`.

## Arquitetura

```
                         X-API-Key header
                               │
                               ▼
 ┌────────┐   HTTP    ┌───────────────┐   401 se ausente/inválida   ┌──────────────┐
 │ Cliente │ ───────▶ │  FastAPI app   │ ───────────────────────▶  │ auth.py       │
 │ (curl,  │           │  (routers/)   │                             │ (dependency)  │
 │ browser)│ ◀───────  └───────┬───────┘ ◀────────────────────────  └──────────────┘
 └────────┘   JSON             │ autorizado
                               ▼
                    ┌─────────────────────┐
                    │ GET /metrics/revenue │
                    └──────────┬───────────┘
                               ▼
                    ┌─────────────────────────┐      hit       ┌───────────────┐
                    │ cache-aside (cache.py)   │ ─────────────▶ │ devolve do     │
                    │ TTLCache in-process       │                │ cache (rápido) │
                    └──────────┬───────────────┘                └───────────────┘
                               │ miss
                               ▼
                    ┌─────────────────────────┐
                    │ SQLAlchemy ORM / Core     │
                    │ (models.py, queries)      │
                    └──────────┬───────────────┘
                               ▼
                 ┌────────────────────────────┐
                 │ PostgreSQL (docker-compose)  │
                 │        ou SQLite (local)      │
                 └──────────┬─────────────────┘
                               │
                               ▼
                    grava resultado no cache
                    (cache-aside) e responde
                               │
                               ▼
                        JSON (Pydantic)
```

Fluxo de uma requisição a `/metrics/*` ou `/customers/*`: o cliente envia o header `X-API-Key`
→ a dependency `require_api_key` valida contra `API_KEY` (401 se faltar ou for inválida) →
o router correspondente processa os query params (validados via Pydantic/FastAPI) → no caso de
`/metrics/revenue`, primeiro verifica o cache em processo (cache-aside); em caso de *miss*,
consulta o banco via SQLAlchemy, agrega o resultado, grava no cache e responde → a resposta é
serializada por um modelo Pydantic, garantindo um contrato estável e documentado no OpenAPI.

## Endpoints

| Método | Rota                              | Auth | Descrição                                                                 |
|--------|------------------------------------|:----:|-----------------------------------------------------------------------------|
| GET    | `/health`                          | não  | Liveness check, não toca o banco.                                          |
| GET    | `/metrics/revenue`                 | sim  | Receita agregada por dia ou mês (`group_by=day\|month`), com filtro de período e cache in-process. |
| GET    | `/metrics/top-products`            | sim  | Ranking de produtos por receita (`limit`, filtro de período).              |
| GET    | `/customers`                       | sim  | Listagem paginada de clientes (`page`, `page_size`, filtro por `country`). |
| GET    | `/customers/{customer_id}/summary` | sim  | Total de pedidos, gasto total e datas do primeiro/último pedido de um cliente. 404 se não existir. |

Documentação interativa (Swagger UI) em `/docs` e ReDoc em `/redoc` assim que a aplicação está
no ar — todos os parâmetros, modelos de resposta e códigos de erro estão descritos ali,
gerados automaticamente a partir dos schemas Pydantic e das docstrings de cada rota.

Rotas protegidas exigem o header `X-API-Key: <valor de API_KEY>`. Sem o header, ou com um
valor incorreto, a API responde `401 Unauthorized` com um corpo `{"detail": "..."}` explicando
o problema.

## Stack técnica

- **Framework**: FastAPI, com validação de query params via Pydantic (datas, enums, paginação
  com `ge`/`le`) e documentação OpenAPI gerada automaticamente.
- **ORM / banco**: SQLAlchemy 2.0 (estilo `Mapped`/`mapped_column`), com um `DATABASE_URL`
  configurável por variável de ambiente. O código evita deliberadamente qualquer recurso
  específico de dialeto (nada de `PRAGMA`, `strftime` do SQLite ou `date_trunc` do Postgres);
  o agrupamento por dia/mês em `/metrics/revenue` é feito em Python após uma única query
  portável, então a mesma base de código funciona sem alterações contra SQLite (padrão local)
  e PostgreSQL (via `docker-compose`).
- **Dados sintéticos**: `Faker` com seed fixa (`app/seed.py`), gerando ~150 clientes, ~40
  produtos, ~600 pedidos e ~1500 itens de pedido, referencialmente consistentes (pedidos
  sempre depois do cadastro do cliente, preços de item "congelados" no momento da compra).
- **Autenticação**: dependency FastAPI (`app/auth.py`) que valida o header `X-API-Key` contra
  a variável `API_KEY`, aplicada a nível de router em `/metrics/*` e `/customers/*`.
- **Cache**: cache-aside em processo com `cachetools.TTLCache` (`app/cache.py`), usado em
  `/metrics/revenue` — ver seção [Por que cachear uma API analítica?](#por-que-cachear-uma-api-analítica) abaixo.
- **Testes**: `pytest` + `TestClient` (httpx), com banco SQLite **em memória** isolado por
  sessão de teste (override da dependency `get_db`) e um dataset fixo calculado à mão, para
  poder afirmar números exatos nas asserções (não apenas "retornou 200").
- **Containerização**: `Dockerfile` para a API + `docker-compose.yml` com PostgreSQL, para um
  ambiente "parecido com produção" com um único comando.

## Modelo de dados

```
Customer (id, name, email, country, signup_date)
   └──< Order (id, customer_id, order_date, status)
              └──< OrderItem (id, order_id, product_id, quantity, unit_price)
                                              └──> Product (id, name, category, unit_price)
```

`OrderItem.unit_price` guarda o preço no momento da compra (não é recalculado a partir de
`Product.unit_price`), da mesma forma que sistemas de pedidos reais "congelam" o preço da
venda — assim o histórico de receita não muda se o preço atual de um produto mudar depois.

Pedidos com status `cancelled` são sempre excluídos das métricas de receita
(`/metrics/revenue`, `/metrics/top-products` e o `total_spend` do resumo de cliente); pedidos
`pending` contam como receita — essa regra de negócio está centralizada em
`OrderStatus.revenue_statuses()` em `app/models.py`.

## Por que cachear uma API analítica?

Consultas agregadas (somar `quantity * unit_price` de todos os itens de pedido em um período)
são exatamente o tipo de query que fica cara conforme a tabela de fatos cresce — e dashboards
analíticos costumam bater repetidamente na mesma combinação de parâmetros (ex.: vários
usuários com o mesmo widget "receita dos últimos 30 dias" atualizando a cada poucos segundos).
`GET /metrics/revenue` implementa **cache-aside**: antes de consultar o banco, verifica se já
existe uma resposta em cache para aquela combinação exata de `group_by`/`start_date`/
`end_date`; se sim, devolve o valor cacheado (campo `cached: true` na resposta); se não,
executa a query, agrega os dados, guarda o resultado no cache com um TTL curto e responde.

A implementação usa `cachetools.TTLCache` **em processo** (um dicionário com expiração e
tamanho máximo, sem dependências externas) — suficiente para uma API de um único processo e
mantém o projeto com zero infraestrutura extra para rodar localmente. Em produção, com múltiplas
réplicas da API atrás de um load balancer, o cache local por processo não seria compartilhado
entre réplicas; o caminho natural de evolução é trocar `app/cache.py` por uma implementação
com Redis (`SET chave valor EX <ttl>` / `GET chave`) — os call sites (`cache_get`/`cache_set`)
não mudariam, só a implementação por trás deles.

## Como rodar localmente (SQLite, zero setup)

Requer apenas Python 3.11+.

```bash
python -m venv venv
# Windows: venv\Scripts\activate | Linux/Mac: source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # ajuste API_KEY se quiser
python -m app.seed            # popula o SQLite local com dados sintéticos
uvicorn app.main:app --reload
```

A API sobe em `http://127.0.0.1:8000`. Docs interativos em `http://127.0.0.1:8000/docs`.

Exemplo de chamada autenticada:

```bash
curl -H "X-API-Key: changeme" "http://127.0.0.1:8000/metrics/revenue?group_by=month"
```

## Exemplo de uso

Saída real, capturada rodando a API localmente (SQLite, `python -m app.seed` seguido de
`uvicorn app.main:app`) e chamando os endpoints com `curl` — não é um exemplo inventado.

**`GET /health`** (não exige autenticação):

```bash
curl -s http://127.0.0.1:8000/health
```

```json
{
    "status": "ok"
}
```

**`GET /metrics/top-products?limit=3`**, autenticado com `X-API-Key: changeme` (valor padrão de
`API_KEY` em `.env.example`):

```bash
curl -s -H "X-API-Key: changeme" "http://127.0.0.1:8000/metrics/top-products?limit=3"
```

```json
{
    "start_date": null,
    "end_date": null,
    "limit": 3,
    "products": [
        {
            "product_id": 34,
            "name": "Cloned full-range attitude",
            "category": "Toys & Games",
            "revenue": 57087.63,
            "units_sold": 117
        },
        {
            "product_id": 21,
            "name": "Compatible secondary array",
            "category": "Sports & Outdoors",
            "revenue": 48478.91,
            "units_sold": 118
        },
        {
            "product_id": 31,
            "name": "Multi-layered executive info-mediaries",
            "category": "Toys & Games",
            "revenue": 47561.93,
            "units_sold": 121
        }
    ]
}
```

(Nomes de produto vêm do `Faker` com seed fixa em `app/seed.py`, por isso são strings
sintéticas sem sentido comercial — o que importa é a agregação de receita/unidades por trás.)

**Mesma chamada sem o header `X-API-Key`** (rota protegida, `401 Unauthorized`):

```bash
curl -s "http://127.0.0.1:8000/metrics/top-products?limit=3"
```

```json
{
    "detail": "Missing API key. Provide a valid 'X-API-Key' header."
}
```

## Como rodar com Docker (PostgreSQL)

```bash
docker-compose up --build
```

Isso sobe um Postgres (`db`) e a API (`api`), esperando o Postgres ficar saudável antes de
iniciar. A API roda `python -m app.seed` automaticamente antes do `uvicorn` (o script é
idempotente: se o banco já tiver dados, ele pula a geração). A API fica disponível em
`http://localhost:8000`. Para usar uma `API_KEY` diferente do padrão `changeme`, defina a
variável de ambiente antes de subir: `API_KEY=minha-chave docker-compose up --build`.

## Como rodar os testes

```bash
pytest -v
```

Os testes usam um banco **SQLite em memória**, isolado da sua base local (a dependency
`get_db` é sobrescrita em `tests/conftest.py`), populado uma vez por sessão de teste com um
dataset pequeno e conhecido (ver docstring de `_seed_fixture_data` em `tests/conftest.py`).
Cobrem: health check, correção numérica da agregação de receita (por dia e por mês, com
exclusão de pedidos cancelados), ordenação e limite do ranking de produtos, resumo de cliente
(caso encontrado, caso 404, cliente sem pedidos), paginação e filtro de clientes, e os três
cenários de autenticação (sem header, header inválido, header válido) em cada rota protegida.
Não é necessário Docker nem Postgres para rodar a suíte.

## Estrutura do projeto

```
sales-metrics-api/
├── app/
│   ├── main.py           # cria a app FastAPI, inclui routers, roda init_db() no startup
│   ├── config.py         # Settings (pydantic-settings) lidas de variáveis de ambiente / .env
│   ├── database.py       # engine, SessionLocal, Base, get_db (dependency), init_db
│   ├── models.py         # ORM: Customer, Product, Order, OrderItem, OrderStatus
│   ├── schemas.py        # modelos Pydantic de request/response
│   ├── auth.py           # dependency require_api_key (X-API-Key)
│   ├── cache.py          # cache-aside em processo (cachetools.TTLCache)
│   ├── seed.py           # gera dataset sintético com Faker (CLI: python -m app.seed)
│   └── routers/
│       ├── health.py     # GET /health
│       ├── metrics.py    # GET /metrics/revenue, GET /metrics/top-products
│       └── customers.py  # GET /customers, GET /customers/{id}/summary
├── tests/
│   ├── conftest.py       # TestClient + SQLite em memória + fixture dataset
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_metrics.py
│   └── test_customers.py
├── docker-compose.yml     # Postgres + API
├── Dockerfile
├── requirements.txt
├── .env.example
└── LICENSE
```

## Possíveis evoluções

- **Migrações**: hoje as tabelas são criadas via `Base.metadata.create_all()` no startup
  (adequado para um projeto de portfólio/demo). Um sistema em produção com schema evolutivo
  usaria [Alembic](https://alembic.sqlalchemy.org/) para migrações versionadas.
- **Cache distribuído**: ver [seção de cache](#por-que-cachear-uma-api-analítica) acima —
  trocar `TTLCache` por Redis quando houver múltiplas réplicas da API.
- **Autenticação**: `X-API-Key` é adequado para consumo interno/serviço-a-serviço; uma API
  pública normalmente evoluiria para OAuth2/JWT com escopos por cliente.

## Licença

MIT — veja [LICENSE](LICENSE).
