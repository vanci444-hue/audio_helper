import { MAX_DURATION_MS, formatDuration } from "../audio/recording.js";

export default function RecordButton({
  phase,
  elapsedMs,
  unsupported,
  onBeginHold,
  onEndHold,
  onCancelHold,
}) {
  function handlePointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    onBeginHold();
  }

  function handlePointerUp(event) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    onEndHold();
  }

  function handlePointerCancel() {
    onCancelHold();
  }

  const recording = phase === "recording";
  const busy = phase === "starting" || phase === "processing";
  let label = "按住说话";
  if (unsupported) label = "当前浏览器无法录音";
  else if (phase === "starting") label = "正在打开麦克风…";
  else if (recording) label = `录音中 ${formatDuration(elapsedMs)}，松开结束`;
  else if (phase === "processing") label = "正在整理录音…";

  return (
    <button
      type="button"
      className={`record-button${recording ? " is-recording" : ""}`}
      disabled={unsupported}
      aria-pressed={recording}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onContextMenu={(event) => event.preventDefault()}
      onKeyDown={(event) => {
        if (event.key === "Escape") onCancelHold();
      }}
      onClick={(event) => event.preventDefault()}
    >
      {label}
      {recording ? (
        <span className="record-limit">最长 {MAX_DURATION_MS / 1000} 秒</span>
      ) : null}
    </button>
  );
}
