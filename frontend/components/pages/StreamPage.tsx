import React, { useEffect, useRef, useState } from 'react';
import { Clapperboard, Rss, Play, Square, Circle, Moon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Hls from 'hls.js';
import { api } from '../../lib/api';
import { ToggleSwitch } from '../ToggleSwitch';

const StreamPage: React.FC = () => {
  const { t } = useTranslation();
  const [streamMode, setStreamMode] = useState<'HLS' | 'WebRTC'>('HLS');
  const [running, setRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState<boolean>(false);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [irMode, setIrMode] = useState<boolean>(false);
  const [irLoading, setIrLoading] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const attachHls = () => {
    const video = videoRef.current;
    if (!video) return;

    const src = '/hls/index.m3u8';

    if (Hls.isSupported()) {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      const hls = new Hls({ lowLatencyMode: true });
      hls.loadSource(src);
      hls.attachMedia(video);
      hlsRef.current = hls;
    } else {
      // Safari/iOS fallback
      video.src = src;
    }
  };

  const startWebRTC = async () => {
    const video = videoRef.current;
    if (!video) return;

    try {
      // Create peer connection
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
      });

      pcRef.current = pc;

      // Store ICE candidates until we have session ID
      const iceCandidates: RTCIceCandidate[] = [];
      let currentSessionId: string | null = null;

      // Handle incoming tracks
      pc.ontrack = (event) => {
        console.log('Received remote track:', event.track.kind);
        if (video.srcObject !== event.streams[0]) {
          video.srcObject = event.streams[0];
          video.play().catch(e => console.error('Play failed:', e));
        }
      };

      // Handle ICE candidates
      pc.onicecandidate = async (event) => {
        if (event.candidate) {
          if (currentSessionId) {
            // We have session ID, send immediately
            try {
              await api.webrtcIce(currentSessionId, event.candidate);
            } catch (e) {
              console.error('Failed to send ICE candidate:', e);
            }
          } else {
            // Queue candidates until we have session ID
            iceCandidates.push(event.candidate);
          }
        }
      };

      pc.onconnectionstatechange = () => {
        console.log('Connection state:', pc.connectionState);
      };

      pc.oniceconnectionstatechange = () => {
        console.log('ICE connection state:', pc.iceConnectionState);
      };

      // Create offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      console.log('Sending offer to server...');

      // Send offer to server
      const response = await api.webrtcOffer({
        sdp: offer.sdp!,
        type: offer.type
      });

      console.log('Received answer from server, session:', response.session_id);

      currentSessionId = response.session_id;
      setSessionId(response.session_id);

      // Set remote description (answer)
      await pc.setRemoteDescription({
        type: 'answer',
        sdp: response.sdp
      });

      // Send queued ICE candidates
      for (const candidate of iceCandidates) {
        try {
          await api.webrtcIce(currentSessionId, candidate);
        } catch (e) {
          console.error('Failed to send queued ICE candidate:', e);
        }
      }

    } catch (e: any) {
      console.error('WebRTC error:', e);
      setError(e?.message || 'WebRTC connection failed');
      stopWebRTC();
    }
  };

  const stopWebRTC = async () => {
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }

    if (sessionId) {
      try {
        await api.webrtcClose(sessionId);
      } catch (e) {
        console.error('Failed to close session:', e);
      }
      setSessionId(null);
    }

    const video = videoRef.current;
    if (video) {
      video.srcObject = null;
    }
  };

  const refreshStatus = async () => {
    try {
      const status = await api.status();
      setRunning(Boolean(status?.stream?.running ?? false));
    } catch {
      // ignore
    }
  };

  const refreshRecordingStatus = async () => {
    try {
      const status = await api.getRecordingStatus();
      setRecording(status.recording);
      setRecordingDuration(status.duration || 0);
    } catch {
      // ignore
    }
  };

  const startRecording = async () => {
    setRecordingLoading(true);
    try {
      const result = await api.startRecording();
      if (result.ok) {
        setRecording(true);
        setRecordingDuration(0);
        // Start interval to update duration
        if (recordingIntervalRef.current) {
          clearInterval(recordingIntervalRef.current);
        }
        recordingIntervalRef.current = setInterval(() => {
          setRecordingDuration(prev => prev + 0.1);
        }, 100);
      } else {
        setError(result.error || 'Failed to start recording');
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to start recording');
    } finally {
      setRecordingLoading(false);
    }
  };

  const stopRecording = async () => {
    setRecordingLoading(true);
    try {
      const result = await api.stopRecording();
      if (result.ok) {
        setRecording(false);
        setRecordingDuration(0);
        // Clear interval
        if (recordingIntervalRef.current) {
          clearInterval(recordingIntervalRef.current);
          recordingIntervalRef.current = null;
        }
      } else {
        setError(result.error || 'Failed to stop recording');
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to stop recording');
    } finally {
      setRecordingLoading(false);
    }
  };

  const formatDuration = (seconds: number): string => {
    return `${seconds.toFixed(1)}s`;
  };

  const toggleIrMode = async (enable: boolean) => {
    setIrLoading(true);
    setError(null);
    try {
      // Call day/night API endpoint
      if (enable) {
        await api.setDayNightMode('night');
      } else {
        await api.setDayNightMode('day');
      }
      setIrMode(enable);
    } catch (e: any) {
      setError(e?.message || 'Failed to toggle IR mode');
      // Revert state on error
      setIrMode(!enable);
    } finally {
      setIrLoading(false);
    }
  };

  useEffect(() => {
    refreshStatus();
    refreshRecordingStatus();

    // Load initial IR mode status
    const loadIrStatus = async () => {
      try {
        const status = await api.getDayNightStatus();
        setIrMode(status.mode === 'night');
      } catch {
        // ignore error, keep default
      }
    };
    loadIrStatus();

    // Poll recording status every 5 seconds
    const interval = setInterval(refreshRecordingStatus, 5000);

    return () => {
      clearInterval(interval);
      if (recordingIntervalRef.current) {
        clearInterval(recordingIntervalRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (streamMode === 'HLS' && running) {
      attachHls();
    }
    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      if (pcRef.current) {
        stopWebRTC();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamMode, running]);

  const start = async () => {
    setError(null);
    setLoading(true);
    try {
      await api.startStream();
      await refreshStatus();

      if (streamMode === 'HLS') {
        attachHls();
      } else {
        await startWebRTC();
      }
    } catch (e: any) {
      setError(e?.message || 'Start failed');
    } finally {
      setLoading(false);
    }
  };

  const stop = async () => {
    setError(null);
    setLoading(true);
    try {
      if (streamMode === 'WebRTC') {
        await stopWebRTC();
      }

      await api.stopStream();
      await refreshStatus();
    } catch (e: any) {
      setError(e?.message || 'Stop failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex flex-col md:flex-row md:justify-between md:items-center mb-6 gap-4">
        <h2 className="text-3xl font-bold text-gray-800 dark:text-white">{t('stream.title')}</h2>

        <div className="flex items-center gap-3">
          {/* IR Mode Toggle */}
          <div className="flex items-center gap-2 bg-gray-100 dark:bg-gray-700 px-3 py-2 rounded-lg">
            <Moon size={18} className="text-gray-600 dark:text-gray-300" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('stream.ir')}</span>
            <ToggleSwitch
              enabled={irMode}
              onChange={toggleIrMode}
              disabled={irLoading}
              loading={irLoading}
            />
          </div>

          <div className="flex items-center space-x-2 bg-gray-200 dark:bg-gray-700 p-1 rounded-lg">
            <button
              className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${streamMode === 'HLS' ? 'bg-emerald-600 text-white' : 'text-gray-700 dark:text-gray-300'}`}
            >
              <div className="flex items-center">
                <Rss size={16} className="mr-2" /> {t('stream.hls')}
              </div>
            </button>
          </div>

        </div>
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-300 p-3 rounded-lg">
          {error}
        </div>
      )}

      <div className="bg-black aspect-video rounded-lg shadow-lg overflow-hidden relative">
        <video ref={videoRef} controls autoPlay muted playsInline className="w-full h-full object-contain" />

        <div className="absolute top-4 left-4 flex items-center space-x-2">
          <div className={`w-3 h-3 rounded-full ${running ? 'bg-red-500 animate-pulse' : 'bg-gray-500'}`}></div>
          <span className="text-white font-semibold text-sm">{running ? t('stream.live') : t('stream.offline')}</span>
        </div>

        {recording && (
          <div className="absolute top-4 right-4 flex items-center space-x-2 bg-red-600 bg-opacity-90 px-3 py-1 rounded-full">
            <Circle size={12} className="text-white fill-white animate-pulse" />
            <span className="text-white font-semibold text-sm">{t('stream.recording.rec')} {formatDuration(recordingDuration)}</span>
          </div>
        )}

        <div className="absolute bottom-4 right-4 text-white text-xs bg-black bg-opacity-50 px-2 py-1 rounded">
          {streamMode} Mode
        </div>
      </div>

      {/* Recording Controls */}
      <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">{t('stream.recording.title')}</h3>
        <div className="flex items-center gap-4">
          {!recording ? (
            <button
              onClick={startRecording}
              disabled={recordingLoading || !running}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Circle size={20} />
              {recordingLoading ? t('stream.recording.starting') : t('stream.recording.start')}
            </button>
          ) : (
            <button
              onClick={stopRecording}
              disabled={recordingLoading}
              className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Square size={20} />
              {recordingLoading ? t('stream.recording.stopping') : t('stream.recording.stop')}
            </button>
          )}

          {recording && (
            <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
              <span className="font-mono text-sm">{formatDuration(recordingDuration)}</span>
            </div>
          )}

          {!running && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('stream.recording.needStream')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default StreamPage;
