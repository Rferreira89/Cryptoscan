# CryptoScan — como publicar

O código já foi testado e compilado aqui (sem erros). Tem duas formas de o publicar, da mais rápida à mais "profissional".

## Opção A — a mais rápida (2 minutos, sem conta obrigatória)

1. Descarregue e descompacte `cryptoscan-dist.zip`.
2. Abra https://app.netlify.com/drop no browser.
3. Arraste a pasta `dist` (a que está dentro do zip) para essa página.
4. Em segundos recebe um link público (ex: `algo-aleatorio.netlify.app`) que já funciona, com dados reais da CoinGecko.
5. Opcional: crie uma conta grátis na Netlify para fixar o link e ligar um domínio próprio.

Não precisa de instalar nada nem usar a linha de comandos.

## Opção B — via GitHub + Vercel (para poder continuar a editar)

1. Descarregue e descompacte `cryptoscan-source.zip`.
2. Crie um repositório novo em https://github.com/new e envie estes ficheiros para lá (pelo GitHub Desktop, ou "upload files" no browser).
3. Em https://vercel.com, clique "Add New Project" → importe esse repositório.
4. A Vercel deteta automaticamente que é um projeto Vite e publica sozinha. Fica com um link `.vercel.app` e pode depois ligar um domínio seu.
5. Sempre que enviar alterações para o GitHub, a Vercel republica automaticamente.

## Nota sobre os dados

Este site liga-se diretamente à API pública da CoinGecko (sem chave necessária). Fora do Claude não há a restrição de rede que bloqueava os pedidos — por isso os dados aparecem normalmente aqui.

A API gratuita da CoinGecko tem um limite de poucos pedidos por minuto por IP. Para uso pessoal isto é suficiente; se muitas pessoas usarem o site ao mesmo tempo pode começar a mostrar "dados indisponíveis" temporariamente — nesse caso considere criar uma conta gratuita "Demo" na CoinGecko para um limite mais estável.
