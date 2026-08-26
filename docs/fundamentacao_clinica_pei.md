# Fundamentação clínica das regras do PEI e da análise de dados

Este documento registra como os materiais fornecidos foram traduzidos em regras de software. Ele não substitui avaliação clínica individualizada, análise funcional ou supervisão profissional.

## Regras implementadas

| Regra no sistema | Fundamentação consultada |
|---|---|
| Objetivos devem descrever resposta observável, contexto, medida e critério quantitativo | Cooper, Heron & Heward (2014), p. 75 e p. 94; Bandura, *Principles of Behavior Modification*, p. 242 |
| A dimensão de medida deve corresponder ao comportamento: contagem/taxa, duração, latência, intervalo entre respostas, percentual ou tentativas até o critério | Cooper, Heron & Heward (2014), p. 99; *Training Manual for Behavior Technicians*, p. 26 |
| Médias não bastam: a leitura reúne nível, tendência e variabilidade | Cooper, Heron & Heward (2014), p. 181–182; *Handbook of Applied Behavior Analysis Interventions for Autism*, p. 427 |
| Um resultado alto não é automaticamente domínio; o sistema separa critério de desempenho, manutenção e generalização | *Handbook of Applied Behavior Analysis Interventions for Autism*, p. 239; *aba in home*, p. 93 |
| Comportamentos interferentes são descritos quantitativamente sem atribuição automática de função | Cooper, Heron & Heward (2014), p. 15 e p. 534; Wong et al., *Evidence-Based Practices*, p. 26 |
| Sugestões de resposta alternativa funcionalmente equivalente só aparecem condicionadas à avaliação funcional | Cooper, Heron & Heward (2014), p. 516; Wong et al., p. 69 |
| Integridade do procedimento e concordância entre observadores devem ser verificadas em diferentes condições | Cooper, Heron & Heward (2014), p. 136, p. 146 e p. 264; *Handbook*, p. 148 |
| A relevância do objetivo e a aceitabilidade dos procedimentos/resultados dependem de validade social | Cooper, Heron & Heward (2014), p. 281 |

## Salvaguardas de interpretação

- Ausência de registro é apresentada como dado ausente, não como ausência do comportamento.
- Contagens de sessões com durações ou oportunidades diferentes não são comparadas como se tivessem a mesma exposição; quando disponível, o sistema prioriza taxa.
- Médias ponderadas só são calculadas quando existe denominador real de tentativas.
- Sequências de critério contam datas distintas, evitando que duplicidades no mesmo dia sejam tratadas como sessões independentes.
- Hipóteses de função são rotuladas como provisórias e exigem dados de antecedentes, resposta e consequências.
- A IA deve distinguir observação, inferência e recomendação, citar a base recuperada e não selecionar tratamento automaticamente.

## Limitações atuais dos dados

O esquema atual de comportamentos interferentes contém principalmente comportamento, data, contagem, taxa e evolução textual. Ele ainda não possui campos estruturados para antecedente, topografia/definição operacional, consequência, duração da observação, contexto, intensidade, fidelidade do procedimento ou concordância entre observadores. Por isso, o sistema pode apoiar a descrição e a formulação de perguntas, mas não determinar função com segurança.

