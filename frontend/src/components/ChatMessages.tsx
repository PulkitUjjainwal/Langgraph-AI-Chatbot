import type { ChatMessage } from "./ChatWidget";

type Props = {
  messages: ChatMessage[];
};

export function ChatMessages({ messages }: Props) {
  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-gray-100 px-4 py-3 text-sm text-chat-text">
            {msg.text}
          </div>
        </div>
      ))}
    </div>
  );
}
