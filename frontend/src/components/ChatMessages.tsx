import type { ChatMessage } from "./ChatWidget";

type Props = {
  messages: ChatMessage[];
};

export function ChatMessages({ messages }: Props) {
  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 bg-gray-50">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          <div
            className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm shadow-sm ${
              msg.role === "user"
                ? "bg-chat-primary text-white rounded-br-sm"
                : "bg-white text-chat-text border border-chat-border rounded-bl-sm"
            }`}
          >
            {msg.text}
          </div>
        </div>
      ))}
    </div>
  );
}
