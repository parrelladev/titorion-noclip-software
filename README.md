# Titorion NoClip — Software do teclado (cópia offline)

Backup pessoal do configurador web do teclado **Titorion NoClip** (modelo K80),
extraído de `https://titorion.i-game.tech/#/pressKey` em **13/11/2026**.

O objetivo é não depender do site oficial: se a marca sair do ar, o software
continua funcionando a partir desta pasta.

> ⚠️ **Este repositório deve ficar privado.** O código é do fabricante
> (Titorion / i-game.tech) e está aqui só como backup de uso pessoal. Não é
> software livre e não deve ser redistribuído.

---

## Como usar

### Pré-requisitos

- **Windows** com **Python 3.7+** instalado
  ([python.org/downloads](https://www.python.org/downloads/), marque
  *"Add Python to PATH"* na instalação).
- **Google Chrome, Microsoft Edge ou Opera** como navegador padrão.
  Firefox e Safari **não** funcionam, porque não têm a API WebHID.
- Teclado conectado **por cabo USB**. O modo Bluetooth não aceita o configurador.

### Abrir

1. Dê dois cliques em **`ABRIR SITE.cmd`**.
2. Uma janela preta (o servidor) abre e, logo depois, o navegador abre o app.
3. Clique em **"Connect the new device"** e escolha o teclado na lista.
4. Quando terminar, feche a aba e a janela preta (ou aperte `Ctrl+C` nela).

> Não abra o `index.html` com dois cliques. Aberto direto do disco
> (`file://`), o navegador bloqueia os scripts e o app não carrega.

### Se o navegador padrão não for Chrome/Edge

Com a janela preta aberta, copie o endereço que ela mostra
(normalmente `http://localhost:8080/`) e cole no Chrome ou no Edge.

---

## O que funciona offline

Tudo o que é configuração do teclado funciona sem internet, porque o app
fala direto com o teclado pelo USB (WebHID), sem passar por servidor:

- remapeamento de teclas e camadas
- iluminação RGB e efeitos
- macros
- demais ajustes salvos no próprio teclado

## O que depende da internet / do fabricante

| Recurso | Situação |
|---|---|
| **Atualização de firmware** | O app busca o arquivo de firmware no servidor do fabricante (`apitest.i-game.tech`). Esta cópia guardou uma resposta antiga, "sem atualização disponível, versão 1.5". **Sem o servidor, não há como atualizar o firmware.** O teclado continua funcionando com o firmware atual. |
| Botão de suporte (ícone animado no canto) | Abre o site de atendimento do fabricante. Só funciona online. |
| Logos de outros modelos (MK812, KG27, MK010...) | Não foram baixados. Não afetam o K80. |
| Fonte *Source Han Sans* | Não foi baixada. Diferença apenas visual. |

---

## Cuidados

- **Use sempre a mesma porta.** Algumas preferências do app ficam guardadas
  no navegador, separadas por endereço. O servidor usa a porta **8080**; se ela
  estiver ocupada, ele pula para a 8081, 8082... e, nesse caso, o app pode
  parecer ter "esquecido" algo. As configurações gravadas no teclado não
  se perdem. Para forçar a porta, rode no terminal, dentro da pasta:

  ```bash
  py -3 __offline/servidor.py 8080
  ```

- **Não atualize o firmware por esta cópia** sem necessidade. Se uma
  atualização for interrompida, o teclado pode ficar sem funcionar.
- O servidor só aceita conexões do próprio computador (`127.0.0.1`).
  Nada fica exposto na rede.

---

## Estrutura da pasta

```
ABRIR SITE.cmd            Atalho: sobe o servidor e abre o app (o único arquivo que você precisa)
index.html                Página principal do app
assets/
  index-CUuVw08z.js       Todo o código do app (React + WebHID), 4,5 MB
  index-ANRmJtUQ.css      Estilos
K80_logo.png              Logo do modelo K80
K80_title_logo_2.png      Ícone da aba
12741.png                 Imagem do teclado (12741 = productId do K80)
_ext/                     Fontes que vinham do Google Fonts, baixadas
pluginWebUpdateNotice/    Aviso de "nova versão do site" (inofensivo offline)
__offline/
  servidor.py             Servidor local em Python (sem dependências)
  runtime.js              Redireciona URLs externas para os arquivos locais
  api-cache.js            Respostas de API gravadas na captura
  worker-runtime.js       Mesmo redirecionamento para web workers
  relatorio.json          Relatório da extração (o que veio e o que falhou)
design-system.html        Catálogo visual gerado pelo extrator (não é necessário para o app)
design-system/            Tokens de design (CSS/JSON) gerados pelo extrator
LEIA-ME.txt               Instruções originais do extrator
```

---

## Detalhes técnicos

- **App:** SPA em React empacotada com Vite, rotas por hash (`#/connect`,
  `#/pressKey`...).
- **Comunicação:** WebHID (`navigator.hid.requestDevice`). Por isso só
  funciona em navegadores baseados em Chromium e por cabo USB.
- **Backend do fabricante:** `https://apitest.i-game.tech/api/`, usado
  apenas em `device/upgrade` (verificação e download de firmware).
- **Extração:** feita com a extensão "Extrator de Sites Brave Cross".
  Falhas registradas em `__offline/relatorio.json`.

### Diagnóstico

Se algo não aparecer, abra o console do navegador (`F12`) e rode:

```js
__EXBC_OFFLINE__.stats        // quantas URLs foram redirecionadas para arquivos locais
__EXBC_OFFLINE__.resolve(url) // para onde uma URL está apontando
```

Um número alto em `misses` indica arquivos que não foram baixados na captura.

---

## Ideias para o futuro

- **Atalho em "modo app":** um `.cmd` que sobe o servidor escondido e abre
  `msedge --app=http://localhost:8080`, para o app abrir numa janela própria,
  sem barra de endereço.
- **Electron:** empacotar tudo num `.exe` que não precisa de Python. Exige
  tratar o evento `select-hid-device` e liberar a permissão de HID, ou o
  botão de conectar não funciona.
