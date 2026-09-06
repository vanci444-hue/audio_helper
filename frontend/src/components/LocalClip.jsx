import { formatBytes, formatDuration } from "../audio/recording.js";

export default function LocalClip({ clip }) {
  if (!clip) return null;

  return (
    <section className="local-clip" aria-label="本地试听">
      <h2>本地试听</h2>
      <audio controls src={clip.url} />
      <p className="clip-meta">
        格式 {clip.mimeType} · 大小 {formatBytes(clip.size)} · 时长{" "}
        {formatDuration(clip.durationMs)}
      </p>
      <a className="download-link" href={clip.url} download={clip.filename}>
        下载录音文件（供后续上传测试）
      </a>
    </section>
  );
}
