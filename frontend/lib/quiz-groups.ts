export type QuizStub = { id: string; title: string; category: string };

export function uniqueQuizzes<T extends { quiz: QuizStub }>(rows: T[]): QuizStub[] {
  const seen = new Set<string>();
  const out: QuizStub[] = [];
  for (const row of rows) {
    if (seen.has(row.quiz.id)) continue;
    seen.add(row.quiz.id);
    out.push(row.quiz);
  }
  return out;
}

export function filterByQuiz<T extends { quiz: QuizStub }>(rows: T[], quizId: string | null): T[] {
  if (!quizId) return rows;
  return rows.filter((r) => r.quiz.id === quizId);
}

export function groupByQuiz<T extends { quiz: QuizStub }>(rows: T[]): { quiz: QuizStub; items: T[] }[] {
  const order: string[] = [];
  const map = new Map<string, { quiz: QuizStub; items: T[] }>();
  for (const row of rows) {
    const id = row.quiz.id;
    let g = map.get(id);
    if (!g) {
      g = { quiz: row.quiz, items: [] };
      map.set(id, g);
      order.push(id);
    }
    g.items.push(row);
  }
  return order.map((id) => map.get(id)!);
}
