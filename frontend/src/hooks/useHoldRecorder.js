import { useCallback, useEffect, useRef, useState } from "react";
import {
  MAX_DURATION_MS,
  MAX_FILE_BYTES,
  MIN_DURATION_MS,
  RecordingError,
  detectRecordingMimeType,
  stopMediaStream,
} from "../audio/recording.js";

function recordingErrorFromGetUserMedia(err) {
  const name = err?.name ?? "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return new RecordingError(
      "PERMISSION",
      "未获得麦克风权限，请在浏览器设置中允许后重试。",
    );
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return new RecordingError("NO_DEVICE", "没有找到可用的麦克风，请接好设备后重试。");
  }
  return new RecordingError("START_FAILED", "无法开始录音，请检查麦克风后重试。");
}

export function useHoldRecorder() {
  const sessionRef = useRef(null);
  const startTokenRef = useRef(0);
  const clipUrlRef = useRef(null);

  const [phase, setPhase] = useState("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [clip, setClip] = useState(null);
  const [error, setError] = useState(null);
  const [mimeType, setMimeType] = useState(null);

  const clearClipUrl = useCallback(() => {
    if (clipUrlRef.current) {
      URL.revokeObjectURL(clipUrlRef.current);
      clipUrlRef.current = null;
    }
  }, []);

  const teardownSession = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    window.clearTimeout(session.maxTimer);
    window.clearInterval(session.tick);
    try {
      if (session.recorder && session.recorder.state !== "inactive") {
        session.recorder.stop();
      }
    } catch {
      // Already inactive.
    }
    stopMediaStream(session.stream);
    sessionRef.current = null;
  }, []);

  const finishRecording = useCallback(
    (session) => {
      if (session.finished) return;
      session.finished = true;
      window.clearTimeout(session.maxTimer);
      window.clearInterval(session.tick);
      stopMediaStream(session.stream);
      if (sessionRef.current === session) {
        sessionRef.current = null;
      }

      if (session.stopReason === "cancel" || session.stopReason === "error") {
        setClip(null);
        clearClipUrl();
        setPhase("idle");
        setElapsedMs(0);
        if (session.stopReason === "cancel") {
          setError(new RecordingError("CANCELLED", "已取消录音，麦克风已关闭。"));
        }
        return;
      }

      const blob = new Blob(session.chunks, { type: session.mimeType });
      const durationMs = session.elapsedMs;

      if (blob.size === 0) {
        setClip(null);
        clearClipUrl();
        setPhase("idle");
        setError(new RecordingError("EMPTY", "没有录到有效音频，请按住按钮重新录音。"));
        return;
      }
      if (durationMs < MIN_DURATION_MS) {
        setClip(null);
        clearClipUrl();
        setPhase("idle");
        setError(
          new RecordingError("TOO_SHORT", "录音不足 1 秒，请按住按钮说完后再松开。"),
        );
        return;
      }
      if (blob.size > MAX_FILE_BYTES) {
        setClip(null);
        clearClipUrl();
        setPhase("idle");
        setError(new RecordingError("TOO_LARGE", "录音文件超过 5MB，请缩短录音后重试。"));
        return;
      }

      clearClipUrl();
      const url = URL.createObjectURL(blob);
      clipUrlRef.current = url;
      const extension = session.mimeType.includes("webm") ? "webm" : "dat";
      setClip({
        url,
        blob,
        mimeType: session.mimeType,
        size: blob.size,
        durationMs: Math.min(durationMs, MAX_DURATION_MS),
        filename: `meetup-recording.${extension}`,
      });
      setError(null);
      setPhase("idle");
    },
    [clearClipUrl],
  );

  const requestStop = useCallback(
    (reason) => {
      startTokenRef.current += 1;
      const session = sessionRef.current;
      if (!session) {
        setPhase("idle");
        return;
      }
      if (session.stopping) return;
      session.stopping = true;
      session.stopReason = reason;
      session.elapsedMs = Date.now() - session.startedAt;
      window.clearTimeout(session.maxTimer);
      window.clearInterval(session.tick);
      setElapsedMs(session.elapsedMs);
      setPhase("processing");

      const recorder = session.recorder;
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          stopMediaStream(session.stream);
          finishRecording(session);
          return;
        }
      }
      stopMediaStream(session.stream);
      if (!recorder || recorder.state === "inactive") {
        finishRecording(session);
      }
    },
    [finishRecording],
  );

  const beginHold = useCallback(async () => {
    const detected = detectRecordingMimeType();
    setMimeType(detected);
    if (!detected) {
      setError(
        new RecordingError(
          "UNSUPPORTED",
          "当前浏览器不支持 WebM/Opus 录音，请更换 Chrome 或 Edge 后再试。",
        ),
      );
      return;
    }
    if (sessionRef.current) return;

    const token = startTokenRef.current + 1;
    startTokenRef.current = token;
    setError(null);
    setElapsedMs(0);
    setPhase("starting");

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      if (startTokenRef.current !== token) return;
      setPhase("idle");
      setError(recordingErrorFromGetUserMedia(err));
      return;
    }

    if (startTokenRef.current !== token) {
      stopMediaStream(stream);
      return;
    }

    const chunks = [];
    let recorder;
    try {
      recorder = new MediaRecorder(stream, { mimeType: detected });
    } catch {
      stopMediaStream(stream);
      setPhase("idle");
      setError(new RecordingError("START_FAILED", "无法开始录音，请检查麦克风后重试。"));
      return;
    }

    const session = {
      stream,
      recorder,
      chunks,
      mimeType: recorder.mimeType || detected,
      startedAt: Date.now(),
      elapsedMs: 0,
      stopping: false,
      finished: false,
      stopReason: "complete",
      maxTimer: 0,
      tick: 0,
    };
    sessionRef.current = session;

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunks.push(event.data);
      }
    };
    recorder.onerror = () => {
      session.stopReason = "error";
      stopMediaStream(stream);
      setError(new RecordingError("RECORD_FAILED", "录音过程出错，请重试。"));
      finishRecording(session);
    };
    recorder.onstop = () => {
      finishRecording(session);
    };

    try {
      recorder.start(250);
    } catch {
      stopMediaStream(stream);
      sessionRef.current = null;
      setPhase("idle");
      setError(new RecordingError("START_FAILED", "无法开始录音，请检查麦克风后重试。"));
      return;
    }

    session.startedAt = Date.now();
    session.maxTimer = window.setTimeout(() => {
      requestStop("limit");
    }, MAX_DURATION_MS);
    session.tick = window.setInterval(() => {
      if (!sessionRef.current) return;
      setElapsedMs(Date.now() - session.startedAt);
    }, 200);
    setPhase("recording");
  }, [finishRecording, requestStop]);

  const endHold = useCallback(() => {
    if (sessionRef.current) {
      requestStop("complete");
      return;
    }
    startTokenRef.current += 1;
    setPhase((current) => (current === "starting" ? "idle" : current));
  }, [requestStop]);

  const cancelHold = useCallback(() => {
    if (sessionRef.current) {
      requestStop("cancel");
      return;
    }
    startTokenRef.current += 1;
    setPhase((current) => (current === "starting" ? "idle" : current));
  }, [requestStop]);

  useEffect(() => {
    const detected = detectRecordingMimeType();
    setMimeType(detected);
    if (!detected) {
      setError(
        new RecordingError(
          "UNSUPPORTED",
          "当前浏览器不支持 WebM/Opus 录音，请更换 Chrome 或 Edge 后再试。",
        ),
      );
    }
    return () => {
      startTokenRef.current += 1;
      teardownSession();
      clearClipUrl();
    };
  }, [clearClipUrl, teardownSession]);

  useEffect(() => {
    if (phase !== "starting" && phase !== "recording") return undefined;
    function onPointerUp() {
      endHold();
    }
    function onPointerCancel() {
      cancelHold();
    }
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);
    return () => {
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
    };
  }, [phase, endHold, cancelHold]);

  return {
    phase,
    elapsedMs,
    clip,
    error,
    mimeType,
    unsupported: !mimeType,
    beginHold,
    endHold,
    cancelHold,
  };
}
