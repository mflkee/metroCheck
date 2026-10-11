import { splitMentionText } from "@/lib/mentions";

type MentionTextProps = {
  text: string;
};

/**
 * Message text with its `@mentions` picked out: a mention is what sends the notification, so it is
 * worth seeing, and the theme's blue marks it. Everything else is rendered exactly as before - the
 * wrapper is a plain `span`, so the surrounding paragraph keeps its own line breaks and wrapping.
 */
export function MentionText({ text }: MentionTextProps) {
  const parts = splitMentionText(text);

  return (
    <>
      {parts.map((part, index) =>
        part.type === "mention" ? (
          <span className="mention" key={`${part.value}-${index}`}>
            {part.value}
          </span>
        ) : (
          <span key={`text-${index}`}>{part.value}</span>
        ),
      )}
    </>
  );
}
