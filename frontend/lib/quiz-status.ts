export function isQuizInFlight(status: string): boolean {
  return status === "generating" || status === "draft";
}

export function isFailedQuiz(status: string): boolean {
  return status === "failed";
}

export function isListedForPractice(quiz: { status: string }): boolean {
  return !isFailedQuiz(quiz.status);
}

export function isQuizWaitingForQuestions(quiz: {
  status: string;
  question_count?: number;
  questions?: unknown[];
}): boolean {
  if (!isQuizInFlight(quiz.status)) return false;
  if (quiz.questions) return quiz.questions.length === 0;
  return (quiz.question_count ?? 0) <= 0;
}

export function quizQuestionCountLabel(quiz: {
  status: string;
  question_count: number;
  blueprint?: { total_questions?: number } | null;
}): string {
  if (isQuizWaitingForQuestions(quiz)) {
    const target = quiz.blueprint?.total_questions;
    return target ? `目标 ${target} 题` : "生成中";
  }
  return `${quiz.question_count} 题`;
}
