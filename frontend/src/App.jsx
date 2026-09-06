import { useEffect, useState } from "react";
import CityField from "./components/CityField.jsx";
import LocalClip from "./components/LocalClip.jsx";
import RecordButton from "./components/RecordButton.jsx";
import { useHoldRecorder } from "./hooks/useHoldRecorder.js";

export default function App() {
  const [city, setCity] = useState("杭州");
  const recorder = useHoldRecorder();

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape") recorder.cancelHold();
    }
    function onVisibilityChange() {
      if (document.visibilityState === "hidden") recorder.cancelHold();
    }
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [recorder.cancelHold]);

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p>按住按钮说出两人所在位置。本轮只做本地录音，不会上传或找店。</p>

      <CityField value={city} onChange={setCity} />

      <RecordButton
        phase={recorder.phase}
        elapsedMs={recorder.elapsedMs}
        unsupported={recorder.unsupported}
        onBeginHold={recorder.beginHold}
        onEndHold={recorder.endHold}
        onCancelHold={recorder.cancelHold}
      />

      {recorder.error ? (
        <p className="status status-error" role="alert">
          {recorder.error.message}
        </p>
      ) : (
        <p className="status">松开结束录音。移出按钮再松开、按 Esc 取消或录满 60 秒也会关闭麦克风。</p>
      )}

      <LocalClip clip={recorder.clip} />
    </main>
  );
}
