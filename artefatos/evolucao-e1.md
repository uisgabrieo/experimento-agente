## 1. Acréscimo do campo boolean noturno

Acrescente ao cadastro de turnos o campo noturno, booleano, opcional, com valor padrão false.

Turnos com noturno = true têm suas horas contabilizadas com adicional de vinte por cento no campo horas_periodo retornado por GET /profissionais/{id}/escala.

O adicional não altera o cálculo de horas_extras nem o limite semanal definido em INV3, que continuam considerando a duração real dos plantões.

Acrescente o filtro GET /turnos?noturno=, combinável com os filtros existentes. Não altere nenhum outro comportamento.
