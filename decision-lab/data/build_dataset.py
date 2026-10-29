"""Gera data/test.jsonl e data/train.jsonl a partir das listas abaixo.

Cada item de teste: text, label (resposta de referência), accept (respostas aceitáveis; inclui label)
e tags (para fatiar métricas). O conjunto de treino é usado SOMENTE pelos baselines que precisam de
exemplos (TF-IDF, embeddings); as frases não se repetem no teste.

Tags:
  clear            caso claro
  hard             caso difícil (pegadinha semântica)
  ambiguous        mais de uma resposta é razoável (ver accept)
  short / long     entradas muito curtas / longas
  asr              erros típicos de transcrição
  no_wake          sem a palavra "Alexa"
  mentions_wake    cita "Alexa" mas não fala com ela
  near_wake        nome parecido com a wake word
  background       TV/rádio ao fundo
  to_human         pedido dirigido a uma pessoa
  english          entrada em inglês
  question / command / casual
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

# (text, label, tags, extra_accept)
TEST: list[tuple[str, str, str, tuple[str, ...]]] = [
    # ---------------- ignore ----------------
    ("Cara, você viu o jogo ontem?", "ignore", "clear casual question", ()),
    ("Amor, você lembrou de comprar pão?", "ignore", "clear casual question to_human", ()),
    ("Hoje o trânsito estava horrível na marginal", "ignore", "clear casual", ()),
    ("Mãe, cadê o carregador do meu celular?", "ignore", "clear question to_human", ()),
    ("Vou tomar banho e já volto", "ignore", "clear casual", ()),
    ("Esse filme é muito bom, você tem que assistir", "ignore", "clear casual", ()),
    ("Nossa, que calor hoje, hein", "ignore", "hard casual", ()),
    ("A Alexa da minha tia não entende nada que ela fala", "ignore", "hard mentions_wake casual", ()),
    ("Eu pedi pra Alexa tocar música ontem e ela tocou outra coisa", "ignore", "hard mentions_wake casual", ()),
    ("Você acha que a gente devia comprar uma Alexa nova pro quarto?", "ignore", "hard mentions_wake question", ()),
    ("E no próximo bloco, as principais notícias do dia", "ignore", "clear background", ()),
    ("Gol! Gol do Brasil! Que golaço!", "ignore", "clear background", ()),
    ("Compre agora e ganhe frete grátis em todo o site", "ignore", "clear background", ()),
    ("Liga pro seu irmão e pergunta se ele vem jantar", "ignore", "hard command to_human no_wake", ()),
    ("Apaga a luz quando sair, tá?", "ignore", "hard command to_human no_wake", ()),
    ("Desliga essa TV que ninguém tá vendo", "ignore", "ambiguous command no_wake", ("home_control",)),
    ("hmm", "ignore", "short", ()),
    ("tá", "ignore", "short", ()),
    ("ok", "ignore", "short", ()),
    ("sim", "ignore", "short", ()),
    ("Ahn?", "ignore", "short", ()),
    ("Quanto você pagou nesse tênis?", "ignore", "clear question to_human", ()),
    ("Qual é a capital da Austrália mesmo? Eu sempre esqueço", "ignore", "ambiguous question no_wake", ("knowledge",)),
    ("Alexandre, vem jantar!", "ignore", "hard near_wake to_human", ()),
    ("Alexia, você vai na festa sábado?", "ignore", "hard near_wake question to_human", ()),
    ("Então, ontem eu fui no mercado e encontrei a Joana, aquela que trabalhava comigo, e ela me contou "
     "que vai casar no ano que vem, acredita? E ainda disse que quer fazer a festa na praia.", "ignore", "long casual", ()),
    ("Olha, eu acho que a gente precisa conversar sobre as férias, porque se a gente for em julho fica "
     "muito caro, mas se for em setembro as crianças estão na escola e aí complica tudo.", "ignore", "long casual", ()),
    ("Ele disse que ia ligar a luz da garagem mas esqueceu", "ignore", "hard casual", ()),
    ("Ontem a luz da sala queimou de novo", "ignore", "hard casual", ()),
    ("O ar condicionado lá do escritório está péssimo", "ignore", "hard casual", ()),
    ("Que horas começa o jogo hoje, você sabe?", "ignore", "ambiguous question no_wake", ("knowledge",)),
    ("Puts, esqueci de tirar a roupa da máquina", "ignore", "clear casual", ()),
    ("Tá bom, tá bom, já vou", "ignore", "clear casual", ()),
    ("O índice de inflação ficou acima do esperado neste mês, informou o instituto", "ignore", "clear background", ()),
    ("Siri, que horas são?", "ignore", "hard question", ()),
    ("Ô Alexa... não, deixa pra lá", "ignore", "hard", ()),
    ("kkkkkk muito bom", "ignore", "short casual", ()),
    ("Você viu onde eu deixei a chave do carro?", "ignore", "clear question to_human", ()),
    ("A música que tocou no casamento era linda", "ignore", "hard casual", ()),
    ("Lembra de levar o lixo pra fora amanhã", "ignore", "ambiguous to_human no_wake", ("timer_alarm",)),
    ("cê viu o jogo onti", "ignore", "asr casual", ()),
    ("vo toma banho ja vorto", "ignore", "asr casual", ()),
    ("Alexa, a nova assistente da Amazon, chega com desconto nesta semana", "ignore", "hard background mentions_wake", ()),
    ("Pergunta pra Alexa se vai chover amanhã", "ignore", "hard to_human mentions_wake", ()),
    ("Pai, você pode aumentar o volume do rádio?", "ignore", "hard to_human question", ()),
    ("Não, não, a luz da cozinha tá ótima assim", "ignore", "hard casual", ()),
    ("Eu odeio quando o despertador toca às seis", "ignore", "hard casual", ()),
    ("Será que vai chover hoje?", "ignore", "ambiguous question no_wake", ("knowledge",)),
    ("Que dia é hoje? Ah, quinta.", "ignore", "hard casual", ()),
    ("Bom dia, gente!", "ignore", "clear casual short", ()),
    ("Obrigado, moço", "ignore", "clear casual short", ()),
    ("Esse vizinho com música alta de novo", "ignore", "hard casual", ()),
    ("Para com isso, menino!", "ignore", "hard to_human short", ()),
    ("A gente podia pedir uma pizza hoje, o que você acha?", "ignore", "clear casual question", ()),
    ("Me passa o sal, por favor", "ignore", "clear to_human command", ()),
    ("Nossa, a conta de luz veio um absurdo esse mês", "ignore", "hard casual", ()),
    ("Ela falou: Alexa, apaga a luz, e a luz não apagou, foi muito engraçado", "ignore", "hard mentions_wake long", ()),
    ("E aí, beleza? Tudo certo pro churrasco de domingo?", "ignore", "clear casual question", ()),

    # ---------------- home_control ----------------
    ("Alexa, acende a luz da sala", "home_control", "clear command", ()),
    ("Alexa, apaga todas as luzes", "home_control", "clear command", ()),
    ("Alexa, liga o ar condicionado no 22", "home_control", "clear command", ()),
    ("Alexa, desliga a TV", "home_control", "clear command", ()),
    ("Alexa, tranca a porta da frente", "home_control", "clear command", ()),
    ("Alexa, abre a cortina do quarto", "home_control", "clear command", ()),
    ("Alexa, diminui a luz do quarto pra 30 por cento", "home_control", "clear command", ()),
    ("Alexa, liga a cafeteira", "home_control", "clear command", ()),
    ("Alexa, a luz da cozinha tá acesa? Se tiver, apaga", "home_control", "hard question command", ()),
    ("Alexa, deixa a sala mais fria", "home_control", "hard command", ()),
    ("Alexa, tá muito escuro aqui", "home_control", "hard", ()),
    ("Alexa, liga o ventilador do escritório", "home_control", "clear command", ()),
    ("Alexa, muda a cor da luz da sala pra azul", "home_control", "clear command", ()),
    ("Alexa, ativa o modo cinema", "home_control", "clear command", ("media",)),
    ("Alexa, desliga tudo, tô saindo", "home_control", "clear command", ()),
    ("Alexa, luz", "home_control", "short command", ()),
    ("Alexa, apaga", "home_control", "short command ambiguous", ("media",)),
    ("acende a luz da sala", "home_control", "ambiguous command no_wake", ("ignore",)),
    ("alequissa a sende a lus da sala", "home_control", "asr command", ()),
    ("Alexa liga o ar condicionado vinte e dois grau", "home_control", "asr command", ()),
    ("a lexa apaga luiz do quarto", "home_control", "asr command", ()),
    ("alexa desliga a tevê da sala", "home_control", "asr command", ()),
    ("Alexa, eu vou dormir agora, então apaga a luz da sala, a da cozinha e deixa só a do corredor "
     "acesa, por favor, que as crianças têm medo do escuro", "home_control", "long command", ()),
    ("Alexa, por favor, você poderia ligar a luz da varanda?", "home_control", "clear question command", ()),
    ("Alexa, turn off the kitchen lights", "home_control", "clear command english", ()),
    ("Alexa, fecha o portão da garagem", "home_control", "clear command", ()),
    ("Alexa, aumenta a temperatura do aquecedor", "home_control", "clear command", ()),
    ("Alexa, liga a luz", "home_control", "clear command short", ()),
    ("Alexa, o ar tá muito forte, abaixa um pouco", "home_control", "hard command", ()),
    ("Apaga a luz do banheiro, Alexa", "home_control", "clear command", ()),
    ("Ei Alexa, liga a TV da sala", "home_control", "clear command", ()),
    ("Alexa, liga a máquina de lavar", "home_control", "clear command", ()),

    # ---------------- media ----------------
    ("Alexa, toca uma música do Djavan", "media", "clear command", ()),
    ("Alexa, aumenta o volume", "media", "clear command", ()),
    ("Alexa, pausa a música", "media", "clear command", ()),
    ("Alexa, próxima música", "media", "clear command short", ()),
    ("Alexa, toca o podcast de notícias", "media", "clear command", ()),
    ("Alexa, coloca a rádio CBN", "media", "clear command", ()),
    ("Alexa, toca algo relaxante pra dormir", "media", "clear command", ()),
    ("Alexa, volume 5", "media", "clear command short", ()),
    ("Alexa, para", "media", "short ambiguous command", ("timer_alarm",)),
    ("alexa toca musica do djavam", "media", "asr command", ()),
    ("Alexa, que música é essa?", "media", "ambiguous question", ("knowledge",)),
    ("Alexa, coloca aquela playlist de rock dos anos 80 na sala", "media", "clear command", ()),
    ("aumenta o som", "media", "ambiguous command no_wake short", ("ignore",)),
    ("Alexa, repete essa música", "media", "clear command", ()),
    ("Alexa, abaixa o volume que o bebê tá dormindo", "media", "clear command", ()),
    ("Alexa, play some jazz", "media", "clear command english", ()),
    ("alexa abaxa o volumi", "media", "asr command", ()),
    ("Alexa, toca o último episódio daquele podcast de história que eu estava ouvindo ontem antes "
     "de dormir, acho que era sobre o Império Romano", "media", "long command", ()),

    # ---------------- timer_alarm ----------------
    ("Alexa, bota um timer de 10 minutos", "timer_alarm", "clear command", ()),
    ("Alexa, me acorda às seis e meia amanhã", "timer_alarm", "clear command", ()),
    ("Alexa, me lembra de tomar o remédio às oito", "timer_alarm", "clear command", ()),
    ("Alexa, cancela o alarme", "timer_alarm", "clear command", ()),
    ("Alexa, quanto tempo falta no timer?", "timer_alarm", "clear question", ()),
    ("Alexa, coloca um alarme pra daqui a vinte minutos", "timer_alarm", "clear command", ()),
    ("Alexa, me lembra de ligar pro dentista amanhã de manhã", "timer_alarm", "clear command", ()),
    ("Alexa, timer de macarrão, oito minutos", "timer_alarm", "clear command", ()),
    ("alexa bota um taimer de cinco minuto", "timer_alarm", "asr command", ()),
    ("Alexa, adia o despertador por dez minutos", "timer_alarm", "clear command", ()),
    ("Alexa, amanhã eu tenho uma reunião importante às nove, então me lembra às oito e meia de "
     "pegar os documentos que estão em cima da mesa do escritório", "timer_alarm", "long command", ()),
    ("Alexa, soneca", "timer_alarm", "short command", ()),
    ("Alexa, quais alarmes eu tenho pra amanhã?", "timer_alarm", "clear question", ()),
    ("alexa me lenbra de rega as planta", "timer_alarm", "asr command", ()),
    ("Alexa, set a timer for five minutes", "timer_alarm", "clear command english", ()),

    # ---------------- knowledge ----------------
    ("Alexa, pesquisa pra mim quais são os melhores filmes de ficção científica", "knowledge", "clear command", ()),
    ("Alexa, qual a capital da Austrália?", "knowledge", "clear question", ()),
    ("Alexa, vai chover amanhã?", "knowledge", "clear question", ()),
    ("Alexa, quantos gramas tem uma xícara de farinha?", "knowledge", "clear question", ()),
    ("Alexa, quem ganhou a copa de 2002?", "knowledge", "clear question", ()),
    ("Alexa, o que significa resiliência?", "knowledge", "clear question", ()),
    ("Alexa, quanto é 15 por cento de 230?", "knowledge", "clear question", ()),
    ("Alexa, que horas são em Tóquio?", "knowledge", "clear question", ()),
    ("Alexa, como faz pra tirar mancha de vinho do sofá?", "knowledge", "clear question", ()),
    ("Alexa, qual a distância da Terra até a Lua?", "knowledge", "clear question", ()),
    ("Alexa, me fala uma curiosidade sobre polvos", "knowledge", "clear command", ()),
    ("Alexa, quem escreveu Dom Casmurro?", "knowledge", "clear question", ()),
    ("alexa qual a capitau da australia", "knowledge", "asr question", ()),
    ("alexa quem ganho a copa de dois mil e dois", "knowledge", "asr question", ()),
    ("Alexa, previsão do tempo", "knowledge", "short", ()),
    ("Alexa, who is the president of France?", "knowledge", "clear question english", ()),
    ("Alexa, o que tá passando no cinema hoje?", "knowledge", "clear question", ()),
    ("Alexa, a farmácia da esquina abre domingo?", "knowledge", "clear question", ()),
    ("Alexa, meu filho perguntou por que o céu é azul e eu não soube explicar direito, você pode me "
     "explicar de um jeito simples que uma criança de oito anos entenda?", "knowledge", "long question", ("complex",)),
    ("Que horas são, Alexa?", "knowledge", "clear question short", ("timer_alarm",)),
    ("Alexa, quantas calorias tem uma banana?", "knowledge", "clear question", ()),

    # ---------------- complex ----------------
    ("Alexa, planeja um cardápio vegetariano pra semana com a lista de compras", "complex", "clear command", ()),
    ("Alexa, escreve um email pro meu chefe pedindo férias em dezembro", "complex", "clear command", ()),
    ("Alexa, me ajuda a montar um roteiro de três dias em Lisboa", "complex", "clear command", ()),
    ("Alexa, compara os planos de celular da Vivo e da Claro e me diz qual compensa mais pra mim", "complex", "clear command", ("knowledge",)),
    ("Alexa, resume as notícias mais importantes de hoje e manda no meu celular", "complex", "clear command", ()),
    ("Alexa, cria uma história pra minha filha dormir com um dragão e uma princesa astronauta", "complex", "clear command", ()),
    ("Alexa, organiza minha agenda da semana sabendo que eu tenho academia segunda e quarta", "complex", "clear command", ()),
    ("Alexa, me ajuda a escrever um discurso de casamento pro meu irmão", "complex", "clear command", ()),
    ("Alexa, eu tenho frango, batata, cenoura e creme de leite em casa, me sugere uma receita e me "
     "explica o passo a passo com os tempos de cada etapa", "complex", "long command", ("knowledge",)),
    ("Alexa, traduz essa frase pro inglês e depois manda pro grupo da família", "complex", "clear command", ()),
    ("alexa escreve um imeio pro meu chefi pedindo ferias", "complex", "asr command", ()),
    ("Alexa, analisa meus gastos do mês e me diz onde eu posso economizar", "complex", "clear command", ()),
    ("Alexa, quando eu chegar em casa à noite, se estiver frio, liga o aquecedor e acende a luz da sala",
     "complex", "ambiguous command long", ("home_control",)),
    ("Alexa, faz um plano de estudos de inglês pra eu passar no TOEFL em seis meses", "complex", "clear command", ()),
    ("Alexa, write a short poem about rain", "complex", "clear command english", ()),
]

TRAIN: list[tuple[str, str]] = [
    # ignore
    ("Você vai querer café?", "ignore"), ("Onde você estacionou o carro?", "ignore"),
    ("Esse professor é muito chato", "ignore"), ("Amanhã eu passo aí na sua casa", "ignore"),
    ("Cuidado que o chão tá molhado", "ignore"), ("A Alexa lá do escritório é bem antiga", "ignore"),
    ("Acabou o leite de novo", "ignore"), ("Filho, desliga esse videogame e vai estudar", "ignore"),
    ("E agora, a previsão do tempo para o fim de semana", "ignore"), ("Você sabe se o João já chegou?", "ignore"),
    ("ãhn", "ignore"), ("beleza", "ignore"), ("Que saudade da praia", "ignore"),
    ("O Pedro falou que a luz do apartamento dele caiu ontem", "ignore"),
    # home_control
    ("Alexa, acende a luz do quarto", "home_control"), ("Alexa, desliga o ar", "home_control"),
    ("Alexa, abre a porta da garagem", "home_control"), ("Alexa, liga a luz da cozinha", "home_control"),
    ("Alexa, coloca o ar em 20 graus", "home_control"), ("Alexa, apaga a luz da varanda", "home_control"),
    ("Alexa, fecha as persianas", "home_control"), ("Alexa, liga a tomada da sala", "home_control"),
    ("Alexa, ativa o modo noite", "home_control"), ("Alexa, deixa a luz mais fraca", "home_control"),
    # media
    ("Alexa, toca Legião Urbana", "media"), ("Alexa, abaixa o volume", "media"),
    ("Alexa, continua a música", "media"), ("Alexa, pula essa faixa", "media"),
    ("Alexa, toca um samba", "media"), ("Alexa, coloca um podcast", "media"),
    ("Alexa, volume no máximo", "media"), ("Alexa, toca minha playlist favorita", "media"),
    ("Alexa, sintoniza a rádio Jovem Pan", "media"), ("Alexa, música ambiente", "media"),
    # timer_alarm
    ("Alexa, timer de cinco minutos", "timer_alarm"), ("Alexa, me acorda às sete", "timer_alarm"),
    ("Alexa, me lembra de pagar a conta amanhã", "timer_alarm"), ("Alexa, cancela o timer", "timer_alarm"),
    ("Alexa, alarme pras seis horas", "timer_alarm"), ("Alexa, me avisa daqui a meia hora", "timer_alarm"),
    ("Alexa, quanto falta pro alarme tocar?", "timer_alarm"), ("Alexa, cria um lembrete pra reunião", "timer_alarm"),
    ("Alexa, desliga o despertador", "timer_alarm"), ("Alexa, adia o alarme", "timer_alarm"),
    # knowledge
    ("Alexa, qual a altura do Everest?", "knowledge"), ("Alexa, como vai estar o tempo hoje?", "knowledge"),
    ("Alexa, quem descobriu o Brasil?", "knowledge"), ("Alexa, quanto é 12 vezes 8?", "knowledge"),
    ("Alexa, o que é fotossíntese?", "knowledge"), ("Alexa, quantos anos tem o Pelé?", "knowledge"),
    ("Alexa, qual a cotação do dólar?", "knowledge"), ("Alexa, pesquisa o horário do mercado", "knowledge"),
    ("Alexa, como se diz obrigado em japonês?", "knowledge"), ("Alexa, quem é o técnico da seleção?", "knowledge"),
    # complex
    ("Alexa, escreve uma mensagem de aniversário pra minha avó", "complex"),
    ("Alexa, monta um treino de academia pra mim", "complex"),
    ("Alexa, me ajuda a planejar a festa do meu filho", "complex"),
    ("Alexa, faz um resumo do livro que eu estou lendo", "complex"),
    ("Alexa, cria uma lista de tarefas pra mudança de casa", "complex"),
    ("Alexa, compara esses dois notebooks e me recomenda um", "complex"),
    ("Alexa, inventa uma piada sobre programadores", "complex"),
    ("Alexa, prepara um roteiro de viagem pro Nordeste", "complex"),
    ("Alexa, revisa esse texto e melhora a escrita", "complex"),
    ("Alexa, sugere um cardápio pro jantar com o que tem na geladeira", "complex"),
]


def main() -> None:
    labels = set(json.loads((HERE / "taxonomy.json").read_text())["options"])
    texts = set()
    with (HERE / "test.jsonl").open("w") as f:
        for i, (text, label, tags, extra) in enumerate(TEST):
            assert label in labels and all(e in labels for e in extra), text
            assert text not in texts, f"duplicado: {text}"
            texts.add(text)
            f.write(json.dumps({"id": f"t{i:03d}", "text": text, "label": label,
                                "accept": [label, *extra], "tags": tags.split()}, ensure_ascii=False) + "\n")
    with (HERE / "train.jsonl").open("w") as f:
        for text, label in TRAIN:
            assert label in labels and text not in texts, text
            f.write(json.dumps({"text": text, "label": label}, ensure_ascii=False) + "\n")
    print(f"test={len(TEST)} train={len(TRAIN)}")
    for label in sorted(labels):
        print(f"  {label:13s} test={sum(1 for t in TEST if t[1] == label):3d} train={sum(1 for t in TRAIN if t[1] == label)}")


if __name__ == "__main__":
    main()
