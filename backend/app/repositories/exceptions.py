class SaldoInsuficienteError(Exception):
    """Levantada pelo repositório (não pelo service) quando o saldo é checado
    e debitado dentro da MESMA operação atômica -- ver `executar_transferencia`
    em memoria_repository.py e postgres_repository.py. Isso é o que fecha a
    condição de corrida: antes, o service lia o saldo, decidia, e só depois
    mandava o repositório escrever -- duas transferências simultâneas podiam
    ler o mesmo saldo "antigo" e as duas passarem. Agora checar e escrever é
    uma coisa só, protegida por lock (memória) ou SELECT ... FOR UPDATE
    (Postgres)."""
