const INTERNAL_BLOCK_PATTERNS = [
  /<internal_reminder\b[^>]*>[\s\S]*?<\/internal_reminder>/gi,
  /<instruction\b[^>]*>[\s\S]*?<\/instruction>/gi,
  /<system-reminder\b[^>]*>[\s\S]*?<\/system-reminder>/gi,
  /<minimax:tool_call\b[^>]*>[\s\S]*?<\/minimax:tool_call>/gi,
];

const INTERNAL_TAG_PATTERNS = [
  /<\/?(?:internal_reminder|instruction|system-reminder)\b[^>]*>/gi,
  /<\/?minimax:tool_call\b[^>]*>/gi,
];

export function sanitizeChatText(value: string): string {
  let next = value;
  for (const pattern of INTERNAL_BLOCK_PATTERNS) {
    next = next.replace(pattern, " ");
  }
  for (const pattern of INTERNAL_TAG_PATTERNS) {
    next = next.replace(pattern, " ");
  }
  return next.replace(/\n{3,}/g, "\n\n").replace(/[ \t]{2,}/g, " ").trim();
}

export function sanitizeChatTexts(values: string[]): string[] {
  return values.map(sanitizeChatText).filter(Boolean);
}
