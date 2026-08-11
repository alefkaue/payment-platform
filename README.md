# Projeto Pagamentos MVP v4

MVP local de pagamentos com FastAPI + HTML/CSS/JS puro + repositório em memória.

## Fluxo
1. Criar quantas contas quiser com Nome, ID da Carteira e Saldo Inicial.
2. Entrar usando apenas o ID da Carteira (login propositalmente básico).
3. Visualizar o saldo da conta logada.
4. Transferir para outra carteira.
5. Ver as contas do sistema e seus saldos para demonstrar a entrada do dinheiro.
6. Ver o histórico de movimentações da conta logada.

## Executar backend
```powershell
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --reload
```

## Executar frontend
Em outro terminal:
```powershell
cd frontend
py -3.12 -m http.server 5500
```

Abrir: http://127.0.0.1:5500

API: http://127.0.0.1:8000/docs

Os dados são apagados ao reiniciar o backend, pois o repositório é em memória.

## Ganchos futuros
Os serviços possuem TODOs explícitos para:
- Liveness Detection
- Reconhecimento Facial
- MFA
- Azure Cosmos DB / Azure SQL Database
- Split Payment / CNPJ
