# Documento como coleta acadêmica — 14/10/2026

## Mudança solicitada

O documento continua no fluxo de cadastro, mas deixa de autenticar a identidade no modo acadêmico. A configuração `DOCUMENTO_VERIFICAR_IDENTIDADE=0` desativa OCR para conferir dados pessoais e comparação do rosto do documento com a prova de vida. Documentos de exemplo podem ser reutilizados por outras equipes sem a restrição de unicidade documental. CPF/e-mail e rosto cadastrado continuam sujeitos às regras próprias de unicidade.

O arquivo ainda passa pelas validações de tipo, tamanho, conteúdo e decodificação. Frente/verso permanecem exigidos conforme o tipo. O caso registra `coleta_academica`, `identidade=nao_verificada` e `rosto=nao_comparado`, com status `em_analise`; não é marcado como identidade aprovada. O comportamento existente registra metadados/hash, não armazena a imagem original.

Prova de vida, anti-spoofing, reconhecimento facial, DPoP, login e regras financeiras permanecem ativos. Documentos societários PJ não foram alterados.

## Configuração e implantação

O padrão do backend é `DOCUMENTO_VERIFICAR_IDENTIDADE=1`, preservando a verificação completa. Em produção, desativá-la exige `DEMONSTRACAO_PUBLICA=1`. Os templates Students definem zero somente quando `demonstracaoPublica=true`.

**Somente código e GitHub: a Azure não foi atualizada**, conforme a instrução final. A aplicação atualmente publicada ainda pode executar a verificação documental antiga. Uma futura implantação da nova imagem e configuração será necessária para ativar este comportamento no site.

## Validação

Testes de regressão cobrem coleta sem OCR/comparação facial e recusa de arquivo inválido. As validações existentes de configuração e documentos também são executadas. Não foi criado cadastro real nem alterada infraestrutura para testar esta mudança.

Resultado: testes selecionados passaram, com um teste ignorado; os dois templates Bicep foram compilados localmente. A configuração bloqueia a desativação da identidade documental em produção fora da demonstração acadêmica.
