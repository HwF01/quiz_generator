export function isQuizInFlight(status: string): boolean {
  return status === "generating" || status === "draft";
}

export function quizQuestionCountLabel(quiz: {
  status: string;
  question_count: number;
  blueprint?: { total_questions?: number } | null;
}): string {
  if (isQuizInFlight(quiz.status) && quiz.question_count <= 0) {
    const target = quiz.blueprint?.total_questions;
    return target ? `目标 ${target} 题` : "生成中";
  }
  return `${quiz.question_count} 题`;
}
