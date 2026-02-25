export type ParsedSseBatch = {
  events: unknown[];
  rest: string;
};

function parseSseBlock(block: string): unknown | null {
  const lines = block.split(/\r?\n/);
  const dataLines = lines
    .map((line) => line.trimEnd())
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());

  if (dataLines.length === 0) {
    return null;
  }

  const payload = dataLines.join("\n");
  try {
    return JSON.parse(payload);
  } catch {
    return { type: "chunk", delta: payload };
  }
}

export function parseSseEvents(buffer: string): ParsedSseBatch {
  const events: unknown[] = [];
  let cursor = 0;

  while (true) {
    const sep = buffer.indexOf("\n\n", cursor);
    if (sep < 0) {
      break;
    }
    const block = buffer.slice(cursor, sep).trim();
    cursor = sep + 2;
    if (!block) {
      continue;
    }
    const parsed = parseSseBlock(block);
    if (parsed !== null) {
      events.push(parsed);
    }
  }

  return {
    events,
    rest: buffer.slice(cursor)
  };
}
