"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { BotHealth } from "@/lib/analytics";
import { botApiUrl, botWsUrl } from "@/lib/format";
import {
  BotDashboardState,
  BotTradeMessage,
  BotWsMessage,
  ConnectionState,
  initialBotState,
} from "@/types/bot";

const MAX_TRADES = 200;
const RECONNECT_MS = 3000;
const HEALTH_POLL_MS = 15000;

export type BotContextValue = BotDashboardState & {
  lastUpdated: Date | null;
  health: BotHealth | null;
  reconnect: () => void;
};

const BotContext = createContext<BotContextValue | null>(null);

function applyMessage(prev: BotDashboardState, msg: BotWsMessage): BotDashboardState {
  switch (msg.type) {
    case "portfolio":
      return { ...prev, portfolio: msg };
    case "session_pnl":
      return { ...prev, sessionPnl: msg };
    case "bot_trade": {
      const trades = [msg as BotTradeMessage, ...prev.trades].slice(0, MAX_TRADES);
      return { ...prev, trades };
    }
    case "balance_history":
      return { ...prev, balanceHistory: msg.points };
    case "balance_point":
      return {
        ...prev,
        balanceHistory: [...prev.balanceHistory, { ts: msg.ts, balance: msg.balance }].slice(
          -2880,
        ),
      };
    case "resolution":
      return {
        ...prev,
        resolutions: { ...prev.resolutions, [msg.market_slug]: msg.winner },
      };
    default:
      return prev;
  }
}

export function BotProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BotDashboardState>(initialBotState);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [health, setHealth] = useState<BotHealth | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<(() => void) | null>(null);

  const touchUpdated = useCallback(() => setLastUpdated(new Date()), []);

  const fetchHealth = useCallback(async () => {
    try {
      const resp = await fetch(`${botApiUrl()}/health`);
      if (!resp.ok) return;
      const data = (await resp.json()) as BotHealth;
      setHealth(data);
    } catch {
      setHealth(null);
    }
  }, []);

  const hydrateFromRest = useCallback(async () => {
    try {
      const resp = await fetch(`${botApiUrl()}/api/status`);
      if (!resp.ok) return;
      const data = await resp.json();
      setState((prev) => {
        let next = { ...prev };
        if (data.portfolio) {
          next = applyMessage(next, { ...data.portfolio, type: "portfolio" });
        }
        if (data.session_pnl) {
          next = applyMessage(next, { ...data.session_pnl, type: "session_pnl" });
        }
        if (Array.isArray(data.balance_history) && data.balance_history.length) {
          next = applyMessage(next, {
            type: "balance_history",
            points: data.balance_history,
          });
        }
        if (Array.isArray(data.trades)) {
          next.trades = data.trades.slice(0, MAX_TRADES);
        }
        if (Array.isArray(data.resolutions)) {
          const resolutions: Record<string, string> = {};
          for (const r of data.resolutions) {
            resolutions[r.market_slug] = r.winner;
          }
          next.resolutions = resolutions;
        }
        return next;
      });
      touchUpdated();
    } catch {
      // REST fallback when WS is down
    }
  }, [touchUpdated]);

  const connect = useCallback(() => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    wsRef.current?.close();
    setState((s) => ({ ...s, connection: "connecting" as ConnectionState }));

    const ws = new WebSocket(botWsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      setState((s) => ({ ...s, connection: "connected" }));
      void fetchHealth();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as BotWsMessage;
        if (!msg?.type) return;
        setState((prev) => applyMessage(prev, msg));
        touchUpdated();
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      setState((s) => ({ ...s, connection: "disconnected" }));
      wsRef.current = null;
      reconnectRef.current = setTimeout(() => connectRef.current?.(), RECONNECT_MS);
    };

    ws.onerror = () => ws.close();
  }, [fetchHealth, touchUpdated]);

  connectRef.current = connect;

  const reconnect = useCallback(() => {
    wsRef.current?.close();
    void hydrateFromRest();
    connect();
  }, [connect, hydrateFromRest]);

  useEffect(() => {
    void hydrateFromRest();
    void fetchHealth();
    connect();

    const healthTimer = setInterval(() => void fetchHealth(), HEALTH_POLL_MS);

    return () => {
      clearInterval(healthTimer);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect, fetchHealth, hydrateFromRest]);

  const value: BotContextValue = {
    ...state,
    lastUpdated,
    health,
    reconnect,
  };

  return <BotContext.Provider value={value}>{children}</BotContext.Provider>;
}

export function useBot(): BotContextValue {
  const ctx = useContext(BotContext);
  if (!ctx) {
    throw new Error("useBot must be used within BotProvider");
  }
  return ctx;
}
