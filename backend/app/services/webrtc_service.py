"""WebRTC streaming service using aiortc and GStreamer.

This service provides low-latency WebRTC streaming as an alternative to HLS.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, Optional
import subprocess
import json

from flask import current_app

from .. import constants as C

logger = logging.getLogger(__name__)


class WebRTCService:
    """Service for WebRTC streaming with GStreamer pipeline."""

    def __init__(self):
        self.peers: Dict[str, 'WebRTCPeer'] = {}
        self.pipeline_process: Optional[subprocess.Popen] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._config = {}

    def _load_config(self) -> None:
        """Load configuration from database settings."""
        from ..models import Setting

        settings = {}
        for setting in Setting.query.all():
            settings[setting.key] = setting.value

        self._config = {
            C.VIDEO_SOURCE: settings.get(C.VIDEO_SOURCE) or current_app.config.get(C.VIDEO_SOURCE),
            C.AUDIO_SOURCE: settings.get(C.AUDIO_SOURCE) or current_app.config.get(C.AUDIO_SOURCE),
            C.STREAM_RES: settings.get(C.STREAM_RES) or current_app.config.get(C.STREAM_RES, "1280x720"),
            C.STREAM_FPS: settings.get(C.STREAM_FPS) or current_app.config.get(C.STREAM_FPS, "30"),
            C.VIDEO_ROTATION: settings.get(C.VIDEO_ROTATION) or current_app.config.get(C.VIDEO_ROTATION, "0"),
        }

    async def create_peer_connection(self, session_id: str) -> dict:
        """Create a new WebRTC peer connection.

        Args:
            session_id: Unique session identifier

        Returns:
            dict with peer connection info
        """
        try:
            from aiortc import RTCPeerConnection
            from aiortc.contrib.media import MediaPlayer
        except ImportError as e:
            logger.error(f"aiortc not installed: {e}. Install with: pip install aiortc av")
            return {"error": "aiortc not installed. Run: pip install aiortc av"}

        self._load_config()

        logger.info(f"Creating peer connection for session {session_id}")

        pc = RTCPeerConnection()
        peer = WebRTCPeer(session_id, pc)
        self.peers[session_id] = peer

        # Use UDP stream as source (shared with HLS, motion, timelapse)
        udp_url = self._config.get(C.STREAM_UDP_URL, "udp://127.0.0.1:5004?pkt_size=1316&reuse=1&overrun_nonfatal=1&fifo_size=5000000")
        logger.info(f"Using UDP source: {udp_url}")

        # Create media player from UDP stream
        try:
            options = {"fflags": "+genpts", "probesize": "32", "analyzeduration": "0"}
            logger.info(f"Creating MediaPlayer with format=mpegts, options={options}")
            player = MediaPlayer(udp_url, format='mpegts', options=options)

            if player.video:
                logger.info("Adding video track to peer connection")
                pc.addTrack(player.video)
                peer.player = player
            else:
                logger.error("MediaPlayer has no video track")
                return {"error": "No video track in UDP stream"}

            if player.audio:
                logger.info("Adding audio track to peer connection")
                pc.addTrack(player.audio)

        except Exception as e:
            logger.exception(f"Failed to create media player from UDP stream")
            return {"error": f"Failed to create media player: {str(e)}"}

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"[{session_id}] Connection state: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await self.close_peer(session_id)

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"[{session_id}] ICE connection state: {pc.iceConnectionState}")

        logger.info(f"Created peer connection for session {session_id}")
        return {"ok": True, "session_id": session_id}

    async def handle_offer(self, session_id: str, offer_sdp: str, offer_type: str) -> dict:
        """Handle WebRTC offer from client.

        Args:
            session_id: Session identifier
            offer_sdp: SDP offer from client
            offer_type: Offer type (usually "offer")

        Returns:
            dict with answer SDP
        """
        try:
            from aiortc import RTCSessionDescription
        except ImportError:
            return {"error": "aiortc not installed"}

        peer = self.peers.get(session_id)
        if not peer:
            return {"error": "Session not found"}

        try:
            offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
            await peer.pc.setRemoteDescription(offer)

            answer = await peer.pc.createAnswer()
            await peer.pc.setLocalDescription(answer)

            return {
                "ok": True,
                "sdp": peer.pc.localDescription.sdp,
                "type": peer.pc.localDescription.type
            }
        except Exception as e:
            logger.error(f"Failed to handle offer: {e}")
            return {"error": str(e)}

    async def handle_ice_candidate(self, session_id: str, candidate: dict) -> dict:
        """Handle ICE candidate from client.

        Args:
            session_id: Session identifier
            candidate: ICE candidate data

        Returns:
            dict with result
        """
        try:
            from aiortc import RTCIceCandidate
        except ImportError:
            return {"error": "aiortc not installed"}

        peer = self.peers.get(session_id)
        if not peer:
            return {"error": "Session not found"}

        try:
            if candidate:
                ice_candidate = RTCIceCandidate(
                    sdpMid=candidate.get("sdpMid"),
                    sdpMLineIndex=candidate.get("sdpMLineIndex"),
                    candidate=candidate.get("candidate")
                )
                await peer.pc.addIceCandidate(ice_candidate)

            return {"ok": True}
        except Exception as e:
            logger.error(f"Failed to handle ICE candidate: {e}")
            return {"error": str(e)}

    async def close_peer(self, session_id: str) -> dict:
        """Close a peer connection.

        Args:
            session_id: Session identifier

        Returns:
            dict with result
        """
        peer = self.peers.pop(session_id, None)
        if not peer:
            return {"error": "Session not found"}

        try:
            await peer.pc.close()
            if peer.player:
                peer.player = None
            logger.info(f"Closed peer connection for session {session_id}")
            return {"ok": True}
        except Exception as e:
            logger.error(f"Failed to close peer: {e}")
            return {"error": str(e)}

    def get_active_sessions(self) -> list[str]:
        """Get list of active session IDs."""
        return list(self.peers.keys())


class WebRTCPeer:
    """Represents a single WebRTC peer connection."""

    def __init__(self, session_id: str, pc):
        self.session_id = session_id
        self.pc = pc
        self.player = None


# Global service instance
webrtc_service = WebRTCService()
