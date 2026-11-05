import { WebSocketServer, WebSocket } from "ws";
import { z } from "zod";
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import { uuid } from "./validation.mjs";
import { assert } from "./errors.mjs";
const update = z
  .object({
    type: z.literal("update"),
    operation_id: uuid,
    generation: z.number().int().positive(),
    update: z.string().max(6000000),
  })
  .strict();
export function attachRealtime({ server, pool, store, documents, origins }) {
  const wss = new WebSocketServer({
      server,
      path: "/workspace-ws",
      maxPayload: 6500000,
      perMessageDeflate: false,
      verifyClient: (info) => origins.includes(info.origin),
    }),
    sessions = new Set(),
    timers = new Map();
  let listener,
    closed = false;
  const send = (socket, value) => {
    if (socket.readyState === WebSocket.OPEN && socket.bufferedAmount < 8388608)
      socket.send(JSON.stringify(value));
  };
  async function authorized(session) {
    if (Date.now() >= session.user.expiresAt) {
      session.socket.close(4401, "Session expired");
      return null;
    }
    try {
      const page = await store.page(pool, session.pageId, session.user);
      return page;
    } catch {
      session.socket.close(4403, "Access changed");
      return null;
    }
  }
  async function refresh(event) {
    for (const session of sessions) {
      const page = await authorized(session);
      if (!page) continue;
      if (
        event.action === "document.updated" &&
        session.pageId === event.page_id
      ) {
        const state = await documents.read(session.user, session.pageId);
        if (state.generation !== session.generation) {
          session.socket.close(4409, "Document restored");
          continue;
        }
        send(session.socket, { type: "state", ...state, access: page.access });
      } else if (
        event.action === "document.restored" &&
        session.pageId === event.page_id
      )
        session.socket.close(4409, "Document restored");
      else if (page.space_id === event.space_id)
        send(session.socket, { type: "refresh" });
    }
  }
  async function listen() {
    if (closed) return;
    try {
      listener = await pool.connect();
      listener.on("notification", (notice) => {
        try {
          const event = JSON.parse(notice.payload);
          const key =
            event.action === "document.updated" ? event.page_id : "metadata";
          clearTimeout(timers.get(key));
          timers.set(
            key,
            setTimeout(() => {
              timers.delete(key);
              void refresh(event).catch(() => {});
            }, 80),
          );
        } catch {}
      });
      listener.on("error", () => {
        listener.release(true);
        listener = null;
        if (!closed) setTimeout(() => void listen(), 1000).unref();
      });
      await listener.query("LISTEN workspace_changes");
    } catch {
      if (listener) {
        listener.release(true);
        listener = null;
      }
      if (!closed) setTimeout(() => void listen(), 1000).unref();
    }
  }
  void listen();
  wss.on("connection", (socket) => {
    if (sessions.size >= 200) {
      socket.close(4429, "Server busy");
      return;
    }
    let session,
      queue = Promise.resolve(),
      queuedBytes = 0,
      count = 0,
      start = Date.now();
    const timeout = setTimeout(
      () => socket.close(4401, "Authentication required"),
      5000,
    );
    socket.on("message", (bytes) => {
      queuedBytes += bytes.length;
      if (queuedBytes > 8388608) {
        socket.close(4429, "Too much pending data");
        return;
      }
      queue = queue
        .then(async () => {
          if (socket.readyState !== WebSocket.OPEN) return;
          if (Date.now() - start > 10000) {
            start = Date.now();
            count = 0;
          }
          assert(++count <= 150, 429, "Bạn thao tác quá nhanh.");
          const message = JSON.parse(bytes.toString());
          if (!session) {
            const auth = z
              .object({
                type: z.literal("auth"),
                ticket: z.string().max(100),
                client_id: z.number().int().positive().max(4294967295),
              })
              .strict()
              .parse(message);
            const result = await documents.consumeTicket(auth.ticket);
            assert(
              [...sessions].filter((s) => s.user.id === result.user.id).length <
                12,
              429,
              "Quá nhiều tab đang mở.",
            );
            const page = await store.page(pool, result.pageId, result.user);
            const state = await documents.read(result.user, result.pageId);
            session = {
              user: result.user,
              pageId: result.pageId,
              generation: state.generation,
              socket,
              clientId: auth.client_id,
            };
            sessions.add(session);
            clearTimeout(timeout);
            send(socket, {
              type: "ready",
              ...state,
              access: page.access,
              user: result.user,
            });
            return;
          }
          const page = await authorized(session);
          if (!page) return;
          if (message.type === "update") {
            assert(
              page.access >= 3,
              403,
              "Bạn chỉ có quyền xem hoặc bình luận.",
            );
            const result = await documents.write(
              session.user,
              session.pageId,
              update.parse(message),
            );
            send(socket, { type: "ack", ...result });
          } else if (message.type === "sync") {
            const state = await documents.read(session.user, session.pageId);
            if (state.generation !== session.generation)
              socket.close(4409, "Document restored");
            else send(socket, { type: "state", ...state, access: page.access });
          } else if (message.type === "awareness") {
            assert(
              typeof message.data === "string" && message.data.length < 16000,
              400,
              "Presence không hợp lệ.",
            );
            const decoder = decoding.createDecoder(
                Buffer.from(message.data, "base64"),
              ),
              encoder = encoding.createEncoder();
            const size = decoding.readVarUint(decoder);
            assert(size === 1, 400, "Presence không hợp lệ.");
            const clientId = decoding.readVarUint(decoder),
              clock = decoding.readVarUint(decoder),
              raw = decoding.readVarString(decoder);
            assert(
              clientId === session.clientId,
              403,
              "Presence không thuộc phiên này.",
            );
            const state = JSON.parse(raw);
            if (state) {
              state.user = {
                name: session.user.name,
                color: ["#2563eb", "#059669", "#9333ea", "#d97706", "#e11d48"][
                  Number(session.user.id) % 5
                ],
              };
            }
            encoding.writeVarUint(encoder, 1);
            encoding.writeVarUint(encoder, clientId);
            encoding.writeVarUint(encoder, clock);
            encoding.writeVarString(encoder, JSON.stringify(state));
            const data = Buffer.from(encoding.toUint8Array(encoder)).toString(
              "base64",
            );
            session.awarenessData = data;
            for (const peer of sessions)
              if (
                peer !== session &&
                peer.pageId === session.pageId &&
                (await authorized(peer))
              ) {
                send(peer.socket, { type: "awareness", data });
                if (peer.awarenessData)
                  send(socket, { type: "awareness", data: peer.awarenessData });
              }
          }
        })
        .catch((error) => {
          send(socket, {
            type: "error",
            code: error.code || "update_failed",
            message:
              error.status && error.status < 500
                ? error.message
                : "Chưa lưu được thay đổi. Bản nháp vẫn được giữ.",
          });
          if (!session || error.status === 403)
            socket.close(4403, "Access denied");
          else if (error.code === "generation_changed")
            socket.close(4409, "Document restored");
        })
        .finally(() => {
          queuedBytes -= bytes.length;
        });
    });
    socket.on("close", () => {
      clearTimeout(timeout);
      if (session) {
        sessions.delete(session);
        for (const peer of sessions)
          if (peer.pageId === session.pageId)
            send(peer.socket, {
              type: "peer_left",
              client_id: session.clientId,
            });
      }
    });
    socket.on("error", () => {});
  });
  const heartbeat = setInterval(() => {
    for (const session of sessions)
      void authorized(session).then((page) => {
        if (page)
          send(session.socket, { type: "permission", access: page.access });
      });
  }, 3000);
  heartbeat.unref();
  return async () => {
    closed = true;
    clearInterval(heartbeat);
    for (const timer of timers.values()) clearTimeout(timer);
    for (const session of sessions)
      session.socket.close(1001, "Server closing");
    wss.close();
    if (listener) {
      await listener.query("UNLISTEN workspace_changes").catch(() => {});
      listener.release();
    }
  };
}
