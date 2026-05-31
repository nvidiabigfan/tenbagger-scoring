"use client";

import { useRef, useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const STARTERS = [
  "공매도 비율이 높으면 어떤 의미인가요?",
  "최근 기관 순매수 동향을 분석해주세요",
  "P/C 비율 1.2는 어떻게 해석하나요?",
  "거래량 배수 3x는 의미 있는 수치인가요?",
];

export default function ChatTab({ ticker }: { ticker: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    if (!text.trim() || streaming) return;
    const userMsg: Message = { role: "user", content: text.trim() };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setStreaming(true);

    const assistantMsg: Message = { role: "assistant", content: "" };
    setMessages([...next, assistantMsg]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        setMessages([...next, { role: "assistant", content: `오류: ${err.error ?? res.statusText}` }]);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        setMessages([...next, { role: "assistant", content: acc }]);
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    } catch (e) {
      setMessages([...next, { role: "assistant", content: `오류: ${String(e)}` }]);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* 시스템 안내 */}
      <div className="bg-blue-50 rounded-xl p-3 text-xs text-blue-700 border border-blue-100">
        <span className="font-semibold">{ticker}</span>의 수급·SEC·컨센서스 데이터를 바탕으로 답변합니다.
        투자 권유가 아닌 데이터 해석 참고용입니다.
      </div>

      {/* 대화 내역 */}
      <div className="space-y-3 min-h-[120px]">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-400">빠른 질문</p>
            <div className="grid grid-cols-1 gap-2">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-xs px-3 py-2 rounded-lg border border-gray-100 bg-gray-50 hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700 text-gray-600 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-gray-100 text-gray-700 shadow-sm"
              }`}
            >
              {m.content}
              {m.role === "assistant" && streaming && i === messages.length - 1 && (
                <span className="inline-block w-1.5 h-4 bg-gray-400 rounded ml-0.5 animate-pulse align-middle" />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* 입력창 */}
      <div className="flex gap-2 pt-1 border-t border-gray-100">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
          placeholder={`${ticker} 수급에 대해 질문하세요...`}
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-blue-400 disabled:opacity-50"
          disabled={streaming}
        />
        <button
          onClick={() => send(input)}
          disabled={!input.trim() || streaming}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          전송
        </button>
      </div>

      {messages.length > 0 && (
        <button
          onClick={() => setMessages([])}
          className="text-xs text-gray-300 hover:text-gray-500 text-center"
        >
          대화 초기화
        </button>
      )}
    </div>
  );
}
