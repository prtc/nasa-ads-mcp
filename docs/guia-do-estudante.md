# NASA ADS no Claude: guia para estudantes

*[Read in English](student-guide.md)*

Este guia prepara você para pesquisar no NASA Astrophysics Data System (ADS) a partir do Claude: encontrar artigos, ler resumos, conferir citações, exportar BibTeX e usar suas bibliotecas do ADS, tudo numa conversa. Leva uns 15 minutos, uma única vez.

Se você faz parte do grupo **Pleiad Astronomy**, alguns passos já estão prontos; eles estão marcados com 🌟.

## Do que você precisa

- Uma conta do Claude num plano pago. 🌟 Membros do Pleiad: usem a conta da organização Pleiad Astronomy.
- Uma conta gratuita no NASA ADS: [crie aqui](https://ui.adsabs.harvard.edu/user/account/register) se ainda não tiver.
- Uns 15 minutos e um terminal (no Windows, o PowerShell).

## Passo 1: Pegue seu token do ADS

O token é como o ADS sabe que os pedidos vêm de você. **Trate-o como uma senha**: não compartilhe, não cole numa conversa e não coloque num repositório.

1. Entre em [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu).
2. Abra [Account → Settings → API Token](https://ui.adsabs.harvard.edu/user/settings/token).
3. Gere um token (ou use o que já aparece ali) e copie. Você vai colá-lo no Passo 5.

## Passo 2: Instale o uv

O uv é uma ferramenta pequena que instala os pacotes Python do servidor (e o próprio Python, se precisar).

- **Linux e macOS:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Depois **abra um terminal novo** e confira com `uv --version`.

## Passo 3: Instale o Claude Code e faça login

- **Linux, macOS, WSL:**
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash
  ```
- **Windows (PowerShell):**
  ```powershell
  irm https://claude.ai/install.ps1 | iex
  ```

Abra um terminal novo, rode `claude` e faça login pelo navegador. 🌟 Membros do Pleiad: escolham a organização Pleiad Astronomy.

Prefere um aplicativo ao terminal? Veja [Claude Desktop](#usando-o-claude-desktop) mais abaixo.

## Passo 4: Obtenha o plugin

🌟 **Membros do Pleiad:** ele já vem instalado. Na primeira vez que você abrir o Claude Code, ele é baixado em segundo plano. Quando aparecer `Plugins changed. Run /reload-plugins to activate.`, rode `/reload-plugins` (ou simplesmente reinicie o Claude Code).

**Demais pessoas:** no terminal, rode:
```bash
claude plugin marketplace add prtc/nasa-ads-mcp
claude plugin install nasa-ads@nasa-ads-mcp
```

## Passo 5: Entregue seu token ao plugin

Use **uma** das opções.

**Opção A: as configurações do plugin (guardadas no cofre de credenciais do seu sistema).** Se o Claude Code pedir o "NASA ADS API token", cole-o. Se ele não pediu, rode `/plugin` dentro do Claude Code, abra a aba **Installed**, escolha **NASA ADS** e configure por lá.

**Opção B: um arquivo (sempre funciona, e é o mesmo que o pacote Python `ads` usa).** No Linux ou macOS:
```bash
mkdir -p ~/.ads
nano ~/.ads/dev_key
```
Cole o token, salve e saia (Ctrl+O, Enter, Ctrl+X). Depois deixe o arquivo privado:
```bash
chmod 600 ~/.ads/dev_key
```

## Passo 6: Confira se funciona

Abra uma sessão nova do Claude Code e rode `/mcp`. Deve aparecer `plugin:nasa-ads:nasa-ads` como conectado. A primeira vez demora alguns segundos a mais enquanto o uv instala as coisas.

Aí é só pedir, por exemplo:

- *Encontre os 10 artigos arbitrados mais citados sobre síntese de populações estelares desde 2015 e resuma as abordagens deles.*
- *Mostre o resumo de 2005A&A...443..735C.*
- *Exporte o BibTeX destes artigos para refs.bib: …*
- *O que tem na minha biblioteca do ADS "Referências da tese"?*

Você pode escrever em português: o Claude traduz a busca para o ADS, onde quase tudo está em inglês. O Claude pede sua permissão na primeira vez que usa cada ferramenta.

**Dicas de busca.** O Claude entende linguagem natural, mas a sintaxe de busca do ADS dá precisão, e você pode usá-la diretamente. Lembre que o ADS exige que *todas* as palavras batam: um título completo colado com uma palavra escrita de outro jeito ("microns" em vez de "μm") não encontra nada, então poucas palavras características funcionam melhor.

| Você escreve | Encontra |
| :-- | :-- |
| `first_author:"Coelho, P."` | artigos com esse primeiro autor |
| `year:2020-2025` | um intervalo de anos |
| `property:refereed` | só artigos arbitrados |
| `abs:"stellar populations"` | a expressão no título, resumo ou palavras-chave |
| `title:(synthetic stellar spectra)` | essas palavras no título, em qualquer ordem |
| `citations(bibcode:2005A&A...443..735C)` | artigos que citam esse artigo |
| `references(bibcode:2005A&A...443..735C)` | artigos que esse artigo cita |

## Usando bem

As ferramentas buscam registros reais do ADS, mas quem escreve os resumos é o Claude, e resumos podem estar errados.

- **Confira antes de citar.** Abra a página do ADS de todo artigo que for citar e leia pelo menos o resumo você mesmo.
- **Pegue o BibTeX pela ferramenta,** nunca digitado pelo Claude de memória. A ferramenta `export_bibtex` devolve exatamente o que o ADS exporta.
- **As métricas de autor comparam nomes, não pessoas.** Um nome comum pode trazer artigos de outras pessoas. As ferramentas de autor buscam na coleção de astronomia por padrão e dizem isso em todo resultado; informe seu ORCID iD para contar só os seus artigos.
- **As bibliotecas são as suas bibliotecas reais do ADS.** Criar uma ou adicionar artigos muda sua conta no ADS. O Claude pergunta antes.
- **Seu token é seu.** Tudo o que as ferramentas fazem acontece na sua conta do ADS e conta no seu limite diário do ADS.

## Usando o Claude Desktop

No macOS, no Windows ou no Linux (o aplicativo para Linux está em beta), você pode usar o servidor no chat do Claude Desktop:

1. Baixe o [`nasa-ads.mcpb`](https://github.com/prtc/nasa-ads-mcp/releases/latest/download/nasa-ads.mcpb).
2. Dê dois cliques nele (ou arraste para a janela do Claude Desktop, ou vá em **Settings → Extensions → Advanced settings → Install Extension…**).
3. Cole seu token do ADS quando pedir.

Se o Claude Desktop disser que não encontra o `uv`, faça o Passo 2 e reinicie o Claude Desktop.

## Se algo der errado

| Você vê | O que fazer |
| :-- | :-- |
| "No ADS API token found" | Faça o Passo 5 e abra uma sessão nova |
| "ADS rejected the API token (401)" | O token está errado ou foi gerado de novo: copie-o outra vez no ADS (Passo 1) e refaça o Passo 5 |
| "ADS rate limit reached" | O ADS limita os pedidos por dia; espere até o horário indicado ou peça menos resultados |
| `uv: command not found` | Abra um terminal novo depois de instalar o uv, ou refaça o Passo 2 |
| As ferramentas aparecem duplicadas | Você também tinha configurado o servidor à mão: rode `claude mcp remove nasa-ads` |
| `plugin:nasa-ads:nasa-ads` não conecta | Rode `claude --debug`, procure linhas que mencionem nasa-ads e peça ajuda |

**Ainda com problema?** Membros do Pleiad: falem com a Paula. Demais pessoas: abram uma issue em [github.com/prtc/nasa-ads-mcp/issues](https://github.com/prtc/nasa-ads-mcp/issues).
