export const MIN_DURATION_MS = 1000;
export const MAX_DURATION_MS = 60_000;
export const MAX_FILE_BYTES = 5 * 1024 * 1024;

export const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm"];

export class RecordingError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "RecordingError";
    this.code = code;
  }
}

export function detectRecordingMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return null;
  }
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDuration(ms) {
  return `${(ms / 1000).toFixed(1)} 秒`;
}

export function stopMediaStream(stream) {
  if (!stream) return;
  for (const track of stream.getTracks()) {
    track.stop();
  }
}
