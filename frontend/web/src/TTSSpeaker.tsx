import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { apiClient } from "./api/client";

interface TTSSpeakerProps {
  text: string;
  autoPlay?: boolean;
}

export function TTSSpeaker({ text, autoPlay = false }: TTSSpeakerProps) {
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (autoPlay && text) {
      handlePlay();
    }
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, [text, autoPlay]);

  const handlePlay = async () => {
    if (!text || !text.trim()) {
      setError("Aucun texte à lire");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.post("/tts/speak", {
        text: text,
      }, {
        responseType: "blob",
      });

      const audioBlob = new Blob([response.data], { type: "audio/mpeg" });
      const audioUrl = URL.createObjectURL(audioBlob);

      if (audioRef.current) {
        audioRef.current.pause();
      }

      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onended = () => {
        setPlaying(false);
        setPaused(false);
        URL.revokeObjectURL(audioUrl);
      };

      audio.onerror = () => {
        setPlaying(false);
        setPaused(false);
        setError("Erreur lors de la lecture audio");
        setLoading(false);
        URL.revokeObjectURL(audioUrl);
      };

      await audio.play();
      setPlaying(true);
      setPaused(false);
      setLoading(false);
    } catch (err) {
      setLoading(false);
      setPlaying(false);
      setPaused(false);
      if (axios.isAxiosError(err) && err.response?.status === 400) {
        setError("Le texte est vide");
      } else {
        setError("Erreur de synthèse vocale");
      }
    }
  };

  const handleStop = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setPlaying(false);
    setPaused(false);
  };

  return (
    <div className="tts-speaker">
      <button
        onClick={handlePlay}
        disabled={loading || playing}
        className="tts-button"
        title="Écouter"
      >
        {loading ? "⏳" : playing ? "🔊" : "🔈"} Écouter
      </button>
      {(playing || paused) && (
        <button onClick={handleStop} className="tts-button" title="Arrêter">
          ⏹️ Arrêter
        </button>
      )}
      {error && <span className="tts-error">{error}</span>}
    </div>
  );
}