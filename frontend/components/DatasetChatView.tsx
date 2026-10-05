'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Send,
  Trash2,
  Database,
  Code2,
  Table as TableIcon,
  HelpCircle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  Clock,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Lightbulb,
  X,
  GripHorizontal,
} from 'lucide-react';
import { sendChatMessage, clearChatConversation } from '../lib/api';
import { ChatMessageUI, ChatResponseUI, SemanticProfile, DatasetMetadata } from '../lib/types';
import { Button } from './Button';
import { Badge } from './Badge';

interface DatasetChatViewProps {
  datasetId: string;
  metadata?: DatasetMetadata | null;
  semanticProfile?: SemanticProfile | null;
  isOpen: boolean;
  onClose?: () => void;
}

export const DatasetChatView: React.FC<DatasetChatViewProps> = ({
  datasetId,
  metadata,
  semanticProfile,
  isOpen,
  onClose,
}) => {
  const [messages, setMessages] = useState<ChatMessageUI[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string>('');
  const [expandedSqlMsgId, setExpandedSqlMsgId] = useState<string | null>(null);
  const [expandedTableMsgId, setExpandedTableMsgId] = useState<string | null>(null);
  const [expandedEvidenceMsgId, setExpandedEvidenceMsgId] = useState<string | null>(null);
  
  // Dragging and positioning state
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);
  const isDraggingRef = useRef<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Keyboard Escape listener to close chat
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Window resize handler to clamp position within viewport bounds
  useEffect(() => {
    const handleResize = () => {
      if (!position || !modalRef.current) return;
      const rect = modalRef.current.getBoundingClientRect();
      const minLeft = 10;
      const maxLeft = Math.max(minLeft, window.innerWidth - rect.width - 10);
      const minTop = 10;
      const maxTop = Math.max(minTop, window.innerHeight - rect.height - 10);
      setPosition((prev) =>
        prev
          ? {
              x: Math.max(minLeft, Math.min(maxLeft, prev.x)),
              y: Math.max(minTop, Math.min(maxTop, prev.y)),
            }
          : null
      );
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [position]);

  // Pointer drag start handler on header
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return; // Only primary mouse button
    // Do not drag if user clicked an interactive button/input/etc.
    if ((e.target as HTMLElement).closest('button, input, select, a, textarea')) return;
    if (typeof window !== 'undefined' && window.innerWidth < 640) return; // Disable drag on mobile

    const el = modalRef.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const startLeft = rect.left;
    const startTop = rect.top;
    isDraggingRef.current = true;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      if (!isDraggingRef.current) return;
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      const modalWidth = rect.width;
      const modalHeight = rect.height;

      // Ensure window stays within visible viewport bounds
      const minLeft = 10;
      const maxLeft = Math.max(minLeft, window.innerWidth - modalWidth - 10);
      const minTop = 10;
      const maxTop = Math.max(minTop, window.innerHeight - modalHeight - 10);

      const newLeft = Math.max(minLeft, Math.min(maxLeft, startLeft + deltaX));
      const newTop = Math.max(minTop, Math.min(maxTop, startTop + deltaY));

      setPosition({ x: newLeft, y: newTop });
    };

    const handlePointerUp = () => {
      isDraggingRef.current = false;
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  };

  // Generate dynamic suggestion chips based on dataset columns
  const suggestionChips = React.useMemo(() => {
    const chips: string[] = [
      'What does this dataset contain?',
      'What are the key insights?',
    ];

    if (semanticProfile && semanticProfile.column_evidences) {
      const measures = Object.entries(semanticProfile.column_evidences)
        .filter(([_, ev]) => ev.candidate_role === 'MEASURE')
        .map(([col]) => col);
      const dimensions = Object.entries(semanticProfile.column_evidences)
        .filter(([_, ev]) => ev.candidate_role === 'DIMENSION')
        .map(([col]) => col);

      if (measures.length > 0 && dimensions.length > 0) {
        chips.push(`What is the average ${measures[0]} by ${dimensions[0]}?`);
        chips.push(`Which ${dimensions[0]} has the highest ${measures[0]}?`);
      } else if (measures.length > 0) {
        chips.push(`What is the average ${measures[0]}?`);
      }
    }
    return chips;
  }, [semanticProfile]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Initial welcome message if conversation is empty
  useEffect(() => {
    if (messages.length === 0 && datasetId) {
      setMessages([
        {
          message_id: 'welcome',
          role: 'assistant',
          content: `Hello! I'm your Evidence-Grounded Dataset Assistant. Ask me anything about **${
            metadata?.filename || 'the active dataset'
          }**—from aggregate metrics and group breakdowns to ranking, top findings, or DuckDB SQL provenance.`,
          timestamp: new Date().toISOString(),
          intent_type: 'GENERAL_HELP',
        },
      ]);
    }
  }, [datasetId, metadata]);

  const handleSend = async (textToSend?: string) => {
    const query = (textToSend || inputText).trim();
    if (!query || isLoading || !datasetId) return;

    setInputText('');
    const userMsgId = `user-${Date.now()}`;
    const userMsg: ChatMessageUI = {
      message_id: userMsgId,
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const resp: ChatResponseUI = await sendChatMessage(
        datasetId,
        query,
        conversationId || undefined,
        true
      );

      if (resp.conversation_id && !conversationId) {
        setConversationId(resp.conversation_id);
      }

      const assistantMsg: ChatMessageUI = {
        message_id: resp.message_id || `asst-${Date.now()}`,
        role: 'assistant',
        content: resp.answer,
        timestamp: new Date().toISOString(),
        intent_type: resp.intent_type,
        query_plan: resp.query_plan,
        compiled_sql: resp.compiled_sql,
        data: resp.data,
        columns: resp.columns,
        row_count: resp.row_count,
        evidence: resp.evidence,
        confidence: resp.confidence,
        warnings: resp.warnings,
        clarification_needed: resp.clarification_needed,
        clarification_options: resp.clarification_options,
        provenance: resp.provenance,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessageUI = {
        message_id: `err-${Date.now()}`,
        role: 'assistant',
        content: `Error processing query: ${err.message || 'Connection failure'}`,
        timestamp: new Date().toISOString(),
        warnings: [err.message],
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearHistory = async () => {
    if (conversationId && datasetId) {
      try {
        await clearChatConversation(datasetId, conversationId);
      } catch (e) {
        console.error('Failed to clear conversation on server:', e);
      }
    }
    setMessages([
      {
        message_id: 'welcome-reset',
        role: 'assistant',
        content: 'Conversation history cleared. How can I help you analyze the dataset?',
        timestamp: new Date().toISOString(),
      },
    ]);
  };

  if (!isOpen) return null;

  return (
    <div
      ref={modalRef}
      id="dataset-chat-view"
      style={
        position
          ? {
              position: 'fixed',
              left: `${position.x}px`,
              top: `${position.y}px`,
              bottom: 'auto',
              right: 'auto',
            }
          : undefined
      }
      className={`${
        position ? '' : 'fixed bottom-5 right-5'
      } w-[92vw] sm:w-[500px] h-[600px] max-h-[85vh] z-50 flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden font-sans text-slate-100 transition-shadow`}
    >
      {/* 1. Draggable Header Bar */}
      <div
        onPointerDown={handlePointerDown}
        className="flex items-center justify-between px-4 py-3 bg-slate-950 border-b border-slate-800 backdrop-blur-md cursor-grab active:cursor-grabbing select-none"
      >
        <div className="flex items-center space-x-2.5 min-w-0">
          <GripHorizontal className="w-4 h-4 text-slate-500 hover:text-slate-300 transition shrink-0" />
          <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold text-slate-100 flex items-center gap-1.5 truncate">
              <span>Evidence-Grounded Dataset Chat</span>
              <Badge variant="blue" size="xs">
                Grounded
              </Badge>
            </div>
            <div className="text-[10px] text-slate-400 font-mono truncate">
              DuckDB Provenance • Hallucination-Guarded
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2 shrink-0 ml-2">
          {metadata && (
            <Badge variant="slate" className="text-xs bg-slate-900 border-slate-700 text-slate-300 hidden md:inline-flex">
              <Database className="w-3 h-3 mr-1 text-indigo-400" />
              {metadata.filename}
            </Badge>
          )}

          {/* Clear History Button */}
          <button
            onClick={handleClearHistory}
            title="Clear Chat History"
            aria-label="Clear Chat History"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
          >
            <Trash2 className="w-4 h-4" />
          </button>

          {/* Cancel / Close Button */}
          {onClose && (
            <button
              id="chat-close-btn"
              onClick={onClose}
              aria-label="Close Chat"
              title="Close (Esc)"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 transition text-xs font-medium shadow-xs active:scale-95"
            >
              <X className="w-3.5 h-3.5" />
              <span>Close</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Messages List */}
      <div
        id="chat-messages"
        className="flex-1 overflow-y-auto p-4 space-y-4 text-sm scrollbar-thin scrollbar-thumb-slate-700"
      >
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isSqlExpanded = expandedSqlMsgId === msg.message_id;
          const isTableExpanded = expandedTableMsgId === msg.message_id;
          const isEvidenceExpanded = expandedEvidenceMsgId === msg.message_id;

          return (
            <div
              key={msg.message_id}
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} max-w-full`}
            >
              {/* Message Bubble */}
              <div
                className={`rounded-2xl px-4 py-3 max-w-[85%] leading-relaxed ${
                  isUser
                    ? 'bg-indigo-600 text-white rounded-br-sm shadow-md'
                    : 'chat-bubble-assistant bg-slate-800/90 text-slate-200 rounded-bl-sm border border-slate-700/80 shadow-sm'
                }`}
              >
                {/* Assistant Label & Intent Badge */}
                {!isUser && msg.intent_type && (
                  <div className="flex items-center space-x-2 mb-2">
                    <span className="flex items-center text-[10px] font-medium tracking-wide uppercase px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                      <Sparkles className="w-2.5 h-2.5 mr-1 text-indigo-400" />
                      {msg.intent_type.replace('_', ' ')}
                    </span>
                    {msg.confidence !== undefined && (
                      <span className="text-[10px] text-slate-400">
                        {Math.round(msg.confidence * 100)}% Confidence
                      </span>
                    )}
                  </div>
                )}

                {/* Content */}
                <div className="whitespace-pre-wrap font-normal">{msg.content}</div>

                {/* Clarification Options */}
                {msg.clarification_needed && msg.clarification_options && (
                  <div className="mt-3 pt-3 border-t border-slate-700/60">
                    <p className="text-xs text-amber-300 font-medium mb-2 flex items-center">
                      <HelpCircle className="w-3.5 h-3.5 mr-1" />
                      Select a clarification option:
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.clarification_options.map((opt, i) => (
                        <button
                          key={i}
                          onClick={() => handleSend(opt)}
                          className="text-xs bg-amber-500/10 hover:bg-amber-500/20 text-amber-200 border border-amber-500/30 px-2.5 py-1 rounded-full transition text-left"
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Interactive Expandable Controls (SQL, Data Table, Evidence) */}
                {!isUser && (msg.compiled_sql || (msg.data && msg.data.length > 0) || msg.evidence) && (
                  <div className="mt-3 pt-2.5 border-t border-slate-700/50 flex flex-wrap gap-2 text-xs">
                    {/* SQL Button */}
                    {msg.compiled_sql && (
                      <button
                        onClick={() =>
                          setExpandedSqlMsgId(isSqlExpanded ? null : msg.message_id)
                        }
                        className="inline-flex items-center px-2 py-1 rounded bg-slate-900/80 hover:bg-slate-900 text-slate-300 border border-slate-700 transition"
                      >
                        <Code2 className="w-3.5 h-3.5 mr-1 text-indigo-400" />
                        {isSqlExpanded ? 'Hide SQL' : 'View SQL'}
                        {isSqlExpanded ? (
                          <ChevronUp className="w-3 h-3 ml-1" />
                        ) : (
                          <ChevronDown className="w-3 h-3 ml-1" />
                        )}
                      </button>
                    )}

                    {/* Data Table Button */}
                    {msg.data && msg.data.length > 0 && (
                      <button
                        onClick={() =>
                          setExpandedTableMsgId(isTableExpanded ? null : msg.message_id)
                        }
                        className="inline-flex items-center px-2 py-1 rounded bg-slate-900/80 hover:bg-slate-900 text-slate-300 border border-slate-700 transition"
                      >
                        <TableIcon className="w-3.5 h-3.5 mr-1 text-emerald-400" />
                        {isTableExpanded ? 'Hide Table' : `View Data (${msg.row_count || msg.data.length})`}
                        {isTableExpanded ? (
                          <ChevronUp className="w-3 h-3 ml-1" />
                        ) : (
                          <ChevronDown className="w-3 h-3 ml-1" />
                        )}
                      </button>
                    )}

                    {/* Evidence Button */}
                    {msg.evidence && Object.keys(msg.evidence).length > 0 && (
                      <button
                        onClick={() =>
                          setExpandedEvidenceMsgId(isEvidenceExpanded ? null : msg.message_id)
                        }
                        className="inline-flex items-center px-2 py-1 rounded bg-slate-900/80 hover:bg-slate-900 text-slate-300 border border-slate-700 transition"
                      >
                        <ShieldCheck className="w-3.5 h-3.5 mr-1 text-blue-400" />
                        {isEvidenceExpanded ? 'Hide Evidence' : 'Evidence'}
                      </button>
                    )}
                  </div>
                )}

                {/* Expanded SQL Block */}
                {isSqlExpanded && msg.compiled_sql && (
                  <div className="mt-2.5 p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-indigo-300 overflow-x-auto">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 font-sans">
                      Compiled DuckDB SQL:
                    </div>
                    <code>{msg.compiled_sql}</code>
                  </div>
                )}

                {/* Expanded Data Table */}
                {isTableExpanded && msg.data && msg.data.length > 0 && (
                  <div className="mt-2.5 max-h-60 overflow-auto rounded bg-slate-950 border border-slate-800 text-xs">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="bg-slate-900/90 text-slate-400 border-b border-slate-800">
                          {Object.keys(msg.data[0]).map((k) => (
                            <th key={k} className="px-3 py-2 font-medium">
                              {k}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-900 text-slate-300">
                        {msg.data.slice(0, 15).map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-900/50">
                            {Object.values(row).map((val: any, cidx) => (
                              <td key={cidx} className="px-3 py-1.5 font-mono text-[11px]">
                                {val !== null && val !== undefined ? String(val) : 'null'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Expanded Evidence Block */}
                {isEvidenceExpanded && msg.evidence && (
                  <div className="mt-2.5 p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-400 overflow-x-auto">
                    <pre>{JSON.stringify(msg.evidence, null, 2)}</pre>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex items-center space-x-2 text-slate-400 text-xs py-2">
            <div className="flex space-x-1">
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span>Analyzing dataset & compiling SQL...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 3. Suggestion Chips */}
      {messages.length <= 2 && (
        <div className="px-4 py-2 border-t border-slate-800/60 bg-slate-950/40">
          <div className="text-[11px] text-slate-400 mb-1.5 flex items-center">
            <Lightbulb className="w-3 h-3 mr-1 text-amber-400" /> Suggested prompts:
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestionChips.map((chip, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(chip)}
                className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700/60 px-2.5 py-1 rounded-full transition flex items-center"
              >
                <span>{chip}</span>
                <ArrowRight className="w-3 h-3 ml-1 text-indigo-400" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 4. Input Bar */}
      <div className="p-3 bg-slate-950 border-t border-slate-800">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center space-x-2"
        >
          <input
            id="chat-input"
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Ask anything about this dataset..."
            disabled={isLoading || !datasetId}
            className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 transition"
          />
          <Button
            id="chat-send-btn"
            type="submit"
            variant="primary"
            disabled={isLoading || !inputText.trim() || !datasetId}
            className="px-3.5 py-2.5"
          >
            <Send className="w-4 h-4" />
          </Button>
        </form>
      </div>
    </div>
  );
};
