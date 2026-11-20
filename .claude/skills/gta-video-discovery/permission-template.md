# Modelos de pedido de permissão

Use o idioma do post (o do texto do autor). Substitua `<…>`. Cada mensagem tem **menos de 280 caracteres**, então cabe numa resposta ao post (contas sem X Premium) ou numa DM.

Escolha **resposta** quando a DM do autor estiver fechada; **DM** quando estiver aberta (mais educado e privado).

## Português

**DM**
```
Oi <@autor>! Curti muito esse clipe de GTA: <link do post>. Posso usar num compilado no meu canal do YouTube (<nome do canal>)? Vou dar crédito com seu @ no vídeo e o link na descrição. Valeu!
```

**Resposta ao post**
```
Que clipe! Posso usar num compilado de GTA no YouTube (<nome do canal>)? Dou crédito com seu @ no vídeo e o link na descrição 🙏
```

## English

**DM**
```
Hey <@author>! Loved this GTA clip: <post link>. Can I feature it in a compilation on my YouTube channel (<channel name>)? You'll get credit with your @ on screen and a link in the description. Thanks!
```

**Reply**
```
Great clip! Can I feature it in a GTA compilation on YouTube (<channel name>)? Credit with your @ on screen + link in the description 🙏
```

## Español

**DM**
```
¡Hola <@autor>! Me encantó este clip de GTA: <enlace>. ¿Puedo usarlo en un compilado en mi canal de YouTube (<nombre del canal>)? Te doy crédito con tu @ en el video y el enlace en la descripción. ¡Gracias!
```

## Registro das respostas
| Resposta do autor | `rights` no `discovery.json` |
|---|---|
| Mensagem enviada, sem resposta | `permission_requested` |
| "Sim" / "pode usar" | `permission_granted` (guarde o print ou link da resposta) |
| "Não" ou pediu para remover | Tire o vídeo do compilado (`approved: false`) |
