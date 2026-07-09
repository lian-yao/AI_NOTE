import { useState, useCallback } from "react"
import { BookOpen, ChevronDown, ChevronUp, Loader2, SendHorizontal, Bot, Trash2, UserRound } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import toast from "react-hot-toast"
import { askGlobalQuestion, type ChatSource } from "@/services/chat"
import { useChatStore } from "@/store/chatStore"
function formatSourceTime(seconds?: number) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "";
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function getSourceTitle(source: ChatSource, index: number) {
  const sectionTitle = source.section_title?.trim();
  if (sectionTitle) return sectionTitle;
  return source.source_type === "transcript" ? `字幕片段 ${index + 1}` : `笔记片段 ${index + 1}`;
}

function getSourceTimeRange(source: ChatSource) {
  const start = formatSourceTime(source.start_time);
  const end = formatSourceTime(source.end_time);
  if (start && end && start !== end) return `${start} - ${end}`;
  return start || end;
}

function SourceText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const content = text.trim() || "没有返回引用文本";
  const shouldClamp = content.length > 160 || content.includes("\n");
  return (
    <div>
      <p className={`whitespace-pre-wrap break-words text-xs leading-5 text-neutral-300 ${shouldClamp && !expanded ? "max-h-[3.75rem] overflow-hidden" : ""}`}>
        {content}
      </p>
      {shouldClamp && (
        <button type="button" onClick={() => setExpanded(!expanded)} className="mt-1 text-xs text-neutral-500 transition-colors hover:text-neutral-300">
          {expanded ? "收起原文" : "展开原文"}
        </button>
      )}
    </div>
  );
}

function SourceReferences({ sources }: { sources: ChatSource[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-3 border-t border-neutral-800/80 pt-2">
      <button type="button" onClick={() => setExpanded(!expanded)} className="flex items-center gap-1.5 text-xs text-neutral-500 transition-colors hover:text-neutral-300">
        <BookOpen className="h-3 w-3" />
        <span>引用来源 ({sources.length})</span>
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => {
            const timeRange = getSourceTimeRange(s);
            return (
              <div key={i} className="rounded-md border border-neutral-800/80 px-2.5 py-2">
                <div className="mb-1.5 flex min-w-0 items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-medium text-neutral-300">{i + 1}. {getSourceTitle(s, i)}</span>
                  {timeRange && <span className="shrink-0 text-[11px] text-neutral-500">{timeRange}</span>}
                </div>
                <SourceText text={s.text || ""} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


function cleanAnswer(content: string) {
  const markerIndex = content.search(/\n{0,2}---\s*\n\s*(?:\*\*)?\s*引用来源\s*(?:\*\*)?\s*[：:]/);
  let cleaned = markerIndex >= 0 ? content.slice(0, markerIndex).trimEnd() : content;
  return cleaned
    .replace(/^正在分析问题\.\.\.\n?/, '')
    .replace(/\n正在检索相关笔记\.\.\.\n?/, '')
    .replace(/\n正在生成回答\.\.\.\n?\n?/, '');
}

export default function GlobalQA() {
  const rawMessages = useChatStore(state => state.chatHistory?.["__global_qa__"])
  const messages = Array.isArray(rawMessages) ? rawMessages.filter(m => m.role === "user" || m.role === "assistant") : []
  const addMessage = useChatStore(state => state.addMessage)
  const clearChat = useChatStore(state => state.clearChat)
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSend = useCallback(async () => {
    const question = input.trim()
    if (!question || loading) return

    addMessage("__global_qa__", { role: "user", content: question })
    setInput("")
    setLoading(true)

    try {
      const res = await askGlobalQuestion({ question })
      addMessage("__global_qa__", { role: "assistant", content: cleanAnswer(res.answer), sources: res.sources })
    } catch {
      toast.error("全局问答请求失败")
    } finally {
      setLoading(false)
    }
  }, [input, loading])

  return (
    <div className="flex h-full flex-col bg-[#0E0E0E]">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-neutral-800 bg-[#101010] px-4">
        <Bot className="h-5 w-5 text-primary" />
        <span className="text-sm font-medium text-neutral-200">全局问答</span>
        <span className="text-xs text-neutral-500">跨所有笔记搜索</span>
        <div className="ml-auto">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => clearChat("__global_qa__")}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
              title="清空对话"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto bg-[#111111] p-4">
        {messages.length === 0 && !loading ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-neutral-400">
            <div>
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-neutral-800 bg-[#1D1D1F]">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <p className="font-medium text-neutral-200">对所有笔记提问</p>
              <p className="mt-1 text-xs text-neutral-500">例如：这些视频的核心观点是什么？</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg, i) => (
              <div>
                <div key={i} className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "assistant" && (
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-neutral-700 bg-[#222225]">
                    <Bot className="h-4 w-4 text-neutral-200" />
                  </div>
                )}
                <div
                  className={`min-w-0 text-sm ${
                    msg.role === "user"
                      ? "bg-primary max-w-[78%] rounded-lg px-3 py-2 text-white"
                      : "prose prose-invert max-w-none flex-1 py-1 text-neutral-200"
                  }`}
                >
                  {msg.role === "user" ? (
                    <p className="break-words whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-white">
                    <UserRound className="h-4 w-4" />
                  </div>
                )}
              </div>
                {Array.isArray(msg.sources) && <div className="pl-9"><SourceReferences sources={msg.sources} /></div>}
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-sm text-neutral-400">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                思考中...
              </div>
            )}
          </div>
        )}
      </div>

      <form
        className="flex shrink-0 gap-2 border-t border-neutral-800/90 bg-[#171719] p-3"
        onSubmit={(e) => {
          e.preventDefault()
          handleSend()
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          rows={1}
          placeholder="输入你的问题..."
          className="min-h-10 flex-1 resize-none rounded-lg border border-neutral-800 bg-[#0F0F11] px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-500 outline-none transition-colors focus:border-primary/70 focus:ring-2 focus:ring-primary/20"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
        </button>
      </form>
    </div>
  )
}
